"""
Hands-free 'Hey Krishteen' wake-word listener — makes Krishteen behave like
Siri/Alexa instead of a push-to-talk assistant.

100% free:
- No Picovoice/openWakeWord account, no API key, no per-call cost.
- Reuses the exact same Google Web Speech recognizer already used by
  command.py and call.py, just run in short repeated bursts.

How it behaves:
- Runs as a daemon thread started once at app launch (see main.py).
- Calibrates once for your room's background noise at startup (same as
  command.py/call.py do), so it isn't sitting at a volume threshold that
  never gets triggered.
- Every few seconds it listens for a short phrase. If something close to
  "krishteen" is heard (fuzzy-matched, since Google's free recognizer often
  mishears uncommon names as "Christine", "Kristen", etc.), that's the wake.
  Two supported patterns, just like Alexa:
    "Hey Krishteen, what's the weather" -> handled in one breath
    "Hey Krishteen" ... (pause) ... "what's the weather" -> it says a short
        acknowledgement ("Yes?") and then listens once more for the request
- Whatever is asked is routed through the exact same logic as typed chat
  (alarms/reminders/appointments, "open ...", "play ... on youtube", or the
  local Ollama model) via command.route_and_respond().
- Cooperates over the mic with command.py/call.py via engine.mic_guard so
  nothing ever records at the same time.
- Automatically pauses itself while a live Call is active (no point
  listening for a wake word while you're already mid-conversation), and
  resumes right after the call ends.
- This is a Python background thread, not something tied to the browser
  tab — it keeps running even if you minimize the window. It only stops if
  you close the app / stop the Python process, or turn it off in Settings.
- Prints every phrase it successfully hears to the terminal (prefixed
  "[wakeword] heard:") so you can see exactly what Google transcribed —
  useful for debugging if it's not responding.

Known limitation: it's built on Google's free web speech API rather than a
dedicated offline wake-word model, so it needs an internet connection (same
requirement the rest of the app's voice recognition already has), and heavy
continuous use could occasionally get rate-limited since it's a free public
endpoint, not a paid quota. For a fully offline wake word you'd swap this
for something like openWakeWord — ask if you want that upgrade later.
"""

import re
import threading
import time
import difflib

import pyttsx3
import speech_recognition as sr
import eel

from engine.mic_guard import try_acquire_mic, release_mic
from engine import call as call_module

# Exact phrases we look for first (fast path).
WAKE_PHRASES = ["hey krishteen", "ok krishteen", "hi krishteen", "okay krishteen", "krishteen"]

# Google's free recognizer frequently mishears "Krishteen" (not a common
# word) as one of these — used for fuzzy matching so the wake word is more
# forgiving than an exact substring check.
WAKE_WORD_VARIANTS = [
    "krishteen", "kristeen", "christine", "kristen", "christina", "cristina",
    "christeen", "krishtin", "krishten", "kristina", "christin", "krishtine",
]

ACK_PHRASES = ["Yes?", "I'm listening.", "Go ahead.", "Yes, how can I help?"]

_enabled = True
_ack_index = 0


def set_enabled(value: bool):
    global _enabled
    _enabled = bool(value)
    try:
        eel.WakeWordState("off" if not _enabled else "idle")
    except Exception:
        pass


def is_enabled():
    return _enabled


def _speak(text):
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
        print("[wakeword] TTS error:", e)


def _calibrate(recognizer, mic):
    """One-time ambient noise calibration so the energy threshold actually
    matches this microphone/room instead of sitting at a generic default."""
    if not try_acquire_mic(timeout=10):
        print("[wakeword] Couldn't get the mic to calibrate — will use defaults.")
        return
    try:
        with mic as source:
            print("[wakeword] Calibrating for background noise...")
            recognizer.adjust_for_ambient_noise(source, duration=1.5)
            print(f"[wakeword] Calibrated. Energy threshold: {recognizer.energy_threshold:.0f}")
    except Exception as e:
        print("[wakeword] Calibration error:", e)
    finally:
        release_mic()


def _listen(recognizer, mic, timeout, phrase_time_limit):
    """One listen+recognize cycle, guarded by mic_guard. Returns '' on
    silence/timeout/unclear audio/mic-busy."""
    if not try_acquire_mic(timeout=0):
        return ""
    try:
        with mic as source:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        text = recognizer.recognize_google(audio, language='en').strip()
        if text:
            print(f"[wakeword] heard: \"{text}\"")
        return text
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print("[wakeword] listen error:", e)
        return ""
    finally:
        release_mic()


def _contains_wake_word(text):
    """True if `text` contains the exact wake phrase OR a word that closely
    resembles 'krishteen' (handles common mishearings)."""
    lowered = text.lower()

    if any(p in lowered for p in WAKE_PHRASES):
        return True

    words = re.findall(r"[a-z']+", lowered)
    for w in words:
        if len(w) < 4:
            continue
        if difflib.get_close_matches(w, WAKE_WORD_VARIANTS, n=1, cutoff=0.72):
            return True
    return False


def _extract_after_wake(text):
    lowered = text.lower()
    for phrase in WAKE_PHRASES:
        idx = lowered.find(phrase)
        if idx != -1:
            return text[idx + len(phrase):].strip(" ,.")

    # Fuzzy path: find the mishearing-variant word and cut everything after it
    words = re.findall(r"[a-z']+", lowered)
    for w in words:
        if len(w) >= 4 and difflib.get_close_matches(w, WAKE_WORD_VARIANTS, n=1, cutoff=0.72):
            idx = lowered.find(w)
            return text[idx + len(w):].strip(" ,.")
    return ""


def _set_ui_state(state):
    try:
        eel.WakeWordState(state)
    except Exception:
        pass


def _watch_loop():
    from engine.command import route_and_respond  # local import avoids a circular import

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.0  # was 0.8 - too short, was cutting off "hey krishteen" after just "hey"
    recognizer.dynamic_energy_threshold = True
    mic = sr.Microphone()

    _calibrate(recognizer, mic)
    print('[wakeword] "Hey een" listener is active.')

    global _ack_index
    
    while True:
        
        if not _enabled or call_module.isCallActive():
            
            time.sleep(0.5)
            continue
        _set_ui_state("listening")
        heard = _listen(recognizer, mic, timeout=4, phrase_time_limit=4)
        

        if not heard:
            
            _set_ui_state("idle")
            continue
        
        if not _contains_wake_word(heard):
            
            _set_ui_state("idle")
            continue

        print("[wakeword] Wake word detected!")
        _set_ui_state("awake")
        immediate_command = _extract_after_wake(heard)

        if immediate_command:
            query = immediate_command
        else:
            ack = ACK_PHRASES[_ack_index % len(ACK_PHRASES)]
            _ack_index += 1
            _speak(ack)
            _set_ui_state("listening")
            query = _listen(recognizer, mic, timeout=6, phrase_time_limit=10)

        if not query:
            _set_ui_state("idle")
            continue

        try:
            eel.LogUserMessage(query)
        except Exception:
            pass

        route_and_respond(query)
        _set_ui_state("idle")


def start_wake_word_listener():
    """Call once at app startup (from main.py)."""
    t = threading.Thread(target=_watch_loop, daemon=True)
    t.start()


# --- eel-exposed endpoints (Settings toggle) ------------------------------

@eel.expose
def setWakeWordEnabled(enabled):
    set_enabled(enabled)
    return is_enabled()


@eel.expose
def getWakeWordEnabled():
    return is_enabled()