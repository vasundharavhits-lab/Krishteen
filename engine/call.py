"""
Continuous voice-call loop for Krishteen.

Unlike command.py's takeCommand() (one-shot, button-triggered), this module
runs a background thread that keeps listening -> thinking -> speaking on a
loop once a "call" is started, like a real phone conversation, until the
user says an end phrase, goes quiet too long, or clicks "End Call" in the UI.
"""

import threading
import uuid
import pyttsx3
import speech_recognition as sr
import eel

from engine.ai import askAI, clear_session
from engine.scheduler import handle_scheduling_command
from engine.role_trigger import handle_role_command
from engine.mic_guard import try_acquire_mic, release_mic

_call_thread = None
_call_active = False
_lock = threading.Lock()

END_PHRASES = [
    "end call", "end the call", "hang up", "hangup",
    "stop call", "goodbye krishteen", "that's all for now",
]

MAX_SILENCE_STRIKES = 4  # ~4 timeouts in a row -> auto hang up


def _speak_for_call(text):
    """Blocking TTS for the call loop. Pushes the line to the UI first so the
    transcript updates immediately, even though speech takes a moment."""
    eel.CallAssistantMessage(text)
    eel.CallStatus("speaking")
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        if len(voices) > 1:
            engine.setProperty('voice', voices[1].id)
        engine.setProperty('rate', 170)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        print("TTS error:", e)


def _listen_once(recognizer, mic, timeout=8, phrase_time_limit=15):
    """One listen+recognize cycle. Returns '' on silence/timeout/unclear audio/mic-busy."""
    if not try_acquire_mic(timeout=3):
        return ""
    try:
        with mic as source:
            eel.CallStatus("listening")
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        eel.CallStatus("thinking")
        query = recognizer.recognize_google(audio, language='en')
        return query.strip()
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print("Listen error:", e)
        return ""
    finally:
        release_mic()


def _call_loop():
    global _call_active

    # Unique session id so this call's conversation memory never mixes
    # with the typed chatbox, a different call, or a Twilio phone caller.
    session_id = f"appcall-{uuid.uuid4().hex[:8]}"

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1
    mic = sr.Microphone()

    if not try_acquire_mic(timeout=5):
        eel.CallAssistantMessage("The microphone is busy right now (Hey Krishteen may be using it) — try again in a moment.")
        eel.CallStatus("ended")
        with _lock:
            _call_active = False
        return

    try:
        with mic as source:
            eel.CallStatus("connecting")
            recognizer.adjust_for_ambient_noise(source, duration=1)
    except Exception as e:
        eel.CallAssistantMessage(f"Couldn't access the microphone: {str(e)}")
        eel.CallStatus("ended")
        with _lock:
            _call_active = False
        return
    finally:
        release_mic()

    eel.CallStatus("connected")
    _speak_for_call("Hi, this is Krishteen. I'm listening, go ahead.")

    silence_strikes = 0

    while True:
        with _lock:
            if not _call_active:
                break

        query = _listen_once(recognizer, mic)

        with _lock:
            if not _call_active:
                break

        if query == "":
            silence_strikes += 1
            if silence_strikes >= MAX_SILENCE_STRIKES:
                _speak_for_call("I haven't heard anything in a while, so I'll end the call here. Goodbye!")
                break
            continue

        silence_strikes = 0
        lowered = query.lower()
        eel.CallUserMessage(query)

        if any(phrase in lowered for phrase in END_PHRASES):
            _speak_for_call("Okay, ending the call. Goodbye!")
            break

        eel.CallStatus("thinking")

        # Check role commands and alarm/reminder/appointment commands first
        # (local, instant, doesn't need the LLM at all), then fall back to
        # the normal AI reply (which applies the locked-in role, if any).
        scheduling_reply = handle_scheduling_command(query)
        role_reply = handle_role_command(query, session_id=session_id)
        if scheduling_reply is not None:
            response = scheduling_reply
        elif role_reply is not None:
            response = role_reply
        else:
            try:
                response = askAI(query, session_id=session_id)
            except Exception as e:
                response = f"Sorry, something went wrong: {str(e)}"

        _speak_for_call(response)

    with _lock:
        _call_active = False
    clear_session(session_id)  # this call's conversation memory ends with the call
    eel.CallStatus("ended")


@eel.expose
def startCall():
    """Called from call.html when the user presses 'Start Call'."""
    global _call_thread, _call_active
    with _lock:
        if _call_active:
            return {"status": "already_active"}
        _call_active = True

    _call_thread = threading.Thread(target=_call_loop, daemon=True)
    _call_thread.start()
    return {"status": "started"}


@eel.expose
def endCall():
    """Called from call.html when the user presses 'End Call'."""
    global _call_active
    with _lock:
        was_active = _call_active
        _call_active = False
    return {"status": "ending" if was_active else "not_active"}


@eel.expose
def isCallActive():
    with _lock:
        return _call_active