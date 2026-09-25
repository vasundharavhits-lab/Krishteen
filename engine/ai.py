import json
import os
import re
import threading
from collections import Counter
from datetime import datetime, timezone

import requests
from engine.preferences import get_style_instruction, get_role_instruction, get_style, get_role

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "krishteen-v15"

_MAX_TURNS = 5

# CANONICAL identity/rules sentence — this exact wording is also what the
# training dataset's default-persona examples use (krishteen_finetune_dataset_v15.jsonl)
# and what the v15 Modelfile bakes in as SYSTEM. Previously this file had its
# own hand-written version of these rules that didn't match any of the ~30
# different wordings the model was actually trained on, which meant the
# model was never trained on the prompt it was actually served with at
# inference time. If this sentence ever needs to change, change it in the
# training data and Modelfile too — don't let it drift again.
CANON_BASE_PROMPT = (
    "You are Krishteen, an AI assistant created by Virtual Height in Indore. "
    "Answer the question directly and specifically — never just acknowledge it. "
    "You have no friends, feelings, or private life — say so plainly if asked, don't invent one. "
    "You have no live internet, weather, or news access — say so plainly if asked for that, "
    "but answer normal factual questions (people, places, history, science) as usual."
)


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


# --- Broken-output detector -------------------------------------------------
#
# krishteen-v14 occasionally falls into a reproducible degenerate ramble on
# short, low-content inputs ("hey", "hi") — confirmed reproducible even at
# temperature 0, so it's not random bad luck, it's a real generation failure
# for that input. This catches the two shapes that failure has actually
# taken in testing: (1) a huge wall of text in response to a tiny input, and
# (2) one word/token dominating the answer (repetition loop). It does NOT
# try to judge whether an answer is *correct* — only whether it's clearly
# broken as text.
def _looks_broken(answer, query):
    words = answer.split()
    n = len(words)
    if n == 0:
        return True

    # A one-to-three word input (hey, hi, what's up) getting a 60+ word
    # reply is already a strong sign of a rambling loop, regardless of
    # content.
    if len(query.split()) <= 3 and n > 60:
        return True

    # One word/token making up a big share of a longish answer is the
    # repetition-loop signature we've seen ("...tasks,tasks,tasks...",
    # "...— no, — no, — no...").
    if n >= 20:
        counts = Counter(w.lower().strip(",.:;—-\"'") for w in words)
        _, top_count = counts.most_common(1)[0]
        if top_count / n > 0.12:
            return True

    # Excessive em-dash usage has been the other consistent marker of the
    # broken pattern in testing.
    if answer.count("—") >= 8:
        return True

    return False


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


def _call_ollama(messages, options):
    """One real request to Ollama. Returns (answer_text, error_message).
    error_message is None on success."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "stream": False,
                "options": options,
            },
            timeout=120,
        )
    except requests.exceptions.ConnectionError:
        return None, "Ollama is not running. Please start Ollama."
    except requests.exceptions.Timeout:
        return None, "The AI is taking too long to respond."
    except Exception as e:
        return None, f"Error: {str(e)}"

    if response.status_code != 200:
        print("Status Code:", response.status_code)
        print("Response:", response.text)
        return None, "Sorry, I couldn't process your request."

    data = response.json()
    answer = data.get("message", {}).get("content", "").strip()
    return answer, None


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

    system_prompt = f"{CANON_BASE_PROMPT} {get_style_instruction()}"

    # IMPORTANT: no more manually-typed "User: ... Assistant:" text labels.
    # Your model was fine-tuned with tokenizer.apply_chat_template() on a
    # real messages=[{"role": ..., "content": ...}] array — a structured
    # format with the chat template's own special tokens, not plain text
    # role labels. Sending a proper messages array through /api/chat
    # matches training exactly instead of approximating it.
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": query}
    ]

    base_options = {
        "repeat_penalty": 1.2,
        "repeat_last_n": 64,
        "temperature": 0.3,
        "top_p": 0.9,
        "num_predict": 220,
    }

    answer, error = _call_ollama(messages, base_options)
    if error:
        return error

    if not answer:
        answer = "Sorry, I couldn't generate a response."

    # Safety net: the model generates a REAL answer every time — this only
    # fires when that first real answer is clearly broken as text (wall of
    # repeated words/tokens on a tiny input). When that happens, ask the
    # model again once, with randomness turned off, using just this turn
    # (no history) to keep the retry as simple/clean as possible for it.
    if _looks_broken(answer, query):
        print("[ai] First answer looked broken, retrying once at temperature 0...")
        retry_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        retry_options = dict(base_options)
        retry_options["temperature"] = 0.0
        retry_answer, retry_error = _call_ollama(retry_messages, retry_options)

        if retry_answer and not retry_error and not _looks_broken(retry_answer, query):
            answer = retry_answer
        else:
            # Both real attempts came back broken — say so honestly instead
            # of returning garbled text OR faking a clean answer that wasn't
            # actually generated.
            print("[ai] Retry also looked broken. Returning an honest fallback.")
            answer = "Sorry, that one didn't come out right on my end — could you try asking again, maybe with a full question?"

    if not _is_meta_turn:
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": answer})
        max_messages = _MAX_TURNS * 2
        if len(history) > max_messages:
            del history[:len(history) - max_messages]

    _log_exchange(session_id, system_prompt, query, answer, handled_by="model")

    return answer
