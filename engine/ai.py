import json
import os
import re
import threading
from datetime import datetime, timezone

import requests
from engine.preferences import get_style_instruction, get_role_instruction, get_style, get_role

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "krishteen-v13"

_MAX_TURNS = 5


# --- Conversation logging (for future fine-tuning) ------------------------
#
# Appends every real exchange to a local JSONL file, in the exact
# {"messages": [...]} shape dataset_builder.py's training examples already
# use — so curating real corrections later is just: open the log, find a
# bad reply, fix the "assistant" content, paste the corrected entry into
# dataset_builder.py's `add(...)` calls.
#
# Set KRISHTEEN_LOG_CONVERSATIONS=0 in .env to turn this off entirely (e.g.
# if a given deployment shouldn't be persisting caller conversations to
# disk). On by default since this only ever writes locally — nothing is
# sent anywhere.
LOG_CONVERSATIONS = os.getenv("KRISHTEEN_LOG_CONVERSATIONS", "1") != "0"
CONVO_LOG_PATH = os.getenv(
    "KRISHTEEN_CONVO_LOG_PATH",
    os.path.join(os.getcwd(), "conversation_logs.jsonl"),
)
_log_lock = threading.Lock()

# --- Concurrent-request guard ---------------------------------------------
#
# The wake-word listener and the typed chatbox both route through askAI()
# using the same hardcoded session_id="chat". If they ever fire close
# together (e.g. you say "Hey Krishteen, what is X" while also typing the
# same question), both calls hit Ollama's /api/generate at once. Ollama
# processes one generate request at a time by default, so the second call
# just sits queued behind the first — which looks exactly like a permanent
# hang in the UI, with no error, nothing to click, nothing to retry.
#
# This tracks which sessions currently have a request in flight and, if a
# second one comes in for the SAME session while the first hasn't finished,
# returns immediately with a short "still working on it" message instead
# of silently queuing a second call to Ollama.
_sessions_in_flight = set()
_in_flight_lock = threading.Lock()
ALREADY_PROCESSING_REPLY = (
    "I'm still working on your last question — give me a moment before asking again."
)


def _log_exchange(session_id, system_prompt, query, answer, handled_by="model"):
    """Best-effort append of one real turn to the local conversation log.
    Never raises — a logging failure should never break a reply."""
    if not LOG_CONVERSATIONS:
        return

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "handled_by": handled_by,   # "model" (kept for backward-compatible log entries)
        "style": get_style(),
        "role": get_role(),
        "messages": [
            {"role": "system", "content": system_prompt} if system_prompt else None,
            {"role": "user", "content": query},
            {"role": "assistant", "content": answer},
        ],
    }
    entry["messages"] = [m for m in entry["messages"] if m is not None]

    try:
        with _log_lock:
            with open(CONVO_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("[ai] Couldn't write conversation log:", e)


# Conversation history, kept PER SESSION instead of one shared global list.
# Without this, a browser-chat test, the in-app Call button, and every
# separate Twilio phone caller were all reading/writing the same memory —
# so one caller's earlier question (e.g. "suggest me a diet") could leak
# into a totally different caller's reply later on.
#
# session_id examples:
#   "chat"                -> typed chatbox / mic button / wake word (command.py)
#   f"appcall-{uuid}"     -> one in-app Call session (call.py)
#   the Twilio CallSid    -> one real phone call (voice_server/server.py)
_chat_histories = {}


def _get_history(session_id):
    return _chat_histories.setdefault(session_id, [])


def clear_session(session_id):
    """Drops a session's conversation memory. Call this when a call/session
    ends so it can't leak into whatever reuses that session_id later."""
    _chat_histories.pop(session_id, None)


def askAI(query, session_id="chat"):
    """
    session_id scopes the conversation memory. Two different session_ids
    never see each other's history — pass a stable id per call/session
    (e.g. the Twilio CallSid for phone calls), and call clear_session()
    when that call/session ends.
    """
    # Refuse a second concurrent request for the same session instead of
    # letting it silently queue behind Ollama's in-progress one.
    with _in_flight_lock:
        if session_id in _sessions_in_flight:
            return ALREADY_PROCESSING_REPLY
        _sessions_in_flight.add(session_id)

    try:
        return _ask_ai_inner(query, session_id)
    finally:
        with _in_flight_lock:
            _sessions_in_flight.discard(session_id)


def _ask_ai_inner(query, session_id):
    history = _get_history(session_id)

    # Used ONLY below to decide whether this turn gets saved into memory —
    # never to skip the model or supply an answer. The model generates
    # every reply itself either way. This exists because storing a shaky
    # identity/greeting answer in history caused the model to compound its
    # own confusion turn over turn (each reply conditioned on the last
    # slightly-off one, getting progressively worse — see conversation
    # where "who are you" -> "who made you" -> "what's your name" degraded
    # each time). These are low-content, repeat-prone turns where nothing
    # is lost by answering each one fresh instead of building on the last.
    lowered_query = query.lower().strip()
    _is_meta_turn = bool(
        re.search(r"what(\'?s| is) your name", lowered_query)
        or re.match(r'^\s*(who|what) are you\s*[?!.]*\s*$', lowered_query)
        or re.search(r'\b(who (made|created|built|trained) you)\b', lowered_query)
        or re.search(r'\bare you (made|built|trained|created) by\b', lowered_query)
        or re.match(r'^\s*(hi+|hey+|hello+|heya|namaste|yo)\s*[!.,]*\s*$', lowered_query)
    )

    

    system_prompt = f"""
You are Krishteen, a helpful AI assistant created by Virtual Height in Indore.
Answer the user's question naturally, accurately, and clearly.
Use your own words instead of fixed or copied replies.
If you are uncertain, say so honestly.
Do not invent personal experiences, feelings, or a private life.
{get_style_instruction()}
""".strip()
     

    # IMPORTANT: no more manually-typed "User: ... Assistant:" text labels.
    # Your model was fine-tuned with tokenizer.apply_chat_template() on a
    # real messages=[{"role": ..., "content": ...}] array — a structured
    # format with the chat template's own special tokens, not plain text
    # role labels. Building "User: hey\nAssistant:" as a raw string and
    # sending it as "prompt" fed the model a format it never actually
    # trained on, which is why increasingly odd/novel questions kept
    # leaking unpredictable text (including literally echoing the word
    # "User:" back). Sending a proper messages array through /api/chat
    # matches training exactly instead of approximating it.
    #
    # This turn's user message is included in what's SENT to the model
    # below, but not yet appended to the persisted `history` list — that
    # only happens after the reply comes back and we know whether to
    # keep this exchange (see _is_meta_turn above).
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": query}
    ]

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "stream": False,
                # Fixes a separate bug from the earlier leak: on open-ended
                # questions (opinions, hallucination-refusal, fictional
                # entities) the model can get stuck repeating a short
                # filler phrase ("say clearly") over and over instead of
                # finishing a real answer — a classic small-model
                # degenerate-repetition loop. repeat_penalty actively
                # discourages reusing recent tokens; repeat_last_n sets
                # how far back it looks when checking for repeats.
                "options": {
                    # Was 1.4 — strong enough to also fight normal reuse of
                    # digits/formatting tokens on any answer, not just
                    # filler loops. 1.2 still breaks up repetition loops
                    # but leaves more headroom for legitimately repeated
                    # tokens (needed for multi-step arithmetic).
                    "repeat_penalty": 1.2,
                    "repeat_last_n": 64,
                    # Lower temperature/top_p = less "creative" sampling,
                    # which is exactly what arithmetic needs: the model
                    # should pick the most likely next digit, not an
                    # interesting one. Ollama's default temperature (0.8)
                    # is tuned for conversational variety, not correctness.
                    "temperature": 0.3,
                    "top_p": 0.9,
                    # Caps how far a single answer can run. The garbled
                    # tails in the screenshot happened well into long
                    # answers — cutting the ceiling means a wrong turn
                    # ends the reply instead of spiraling further.
                    "num_predict": 220
                }
            },
            timeout=120
        )

        if response.status_code != 200:
            print("Status Code:", response.status_code)
            print("Response:", response.text)
            return "Sorry, I couldn't process your request."

        data = response.json()

        answer = data.get("message", {}).get("content", "").strip()

        if not answer:
            answer = "Sorry, I couldn't generate a response."

        if not _is_meta_turn:
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": answer})
            max_messages = _MAX_TURNS * 2
            if len(history) > max_messages:
                del history[:len(history) - max_messages]

        _log_exchange(session_id, system_prompt, query, answer, handled_by="model")

        return answer

    except requests.exceptions.ConnectionError:
        return "Ollama is not running. Please start Ollama."

    except requests.exceptions.Timeout:
        return "The AI is taking too long to respond."

    except Exception as e:
        return f"Error: {str(e)}"