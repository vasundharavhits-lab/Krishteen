"""
engine/tts.py — Speech OUTPUT, 100% open-source and local via pyttsx3
(uses your OS's built-in speech engine — SAPI5 on Windows, NSSpeechSynthesizer
on macOS, espeak on Linux). No cloud API, no API key, no internet required
at all, no per-request cost or quota.

Two ways to use this:
- speak(text)                 -> plays immediately through THIS computer's
                                  speakers. Used by call.py, wakeword.py,
                                  scheduler.py — things that only make sense
                                  for whoever is physically at this machine.
- synthesize_to_wav_bytes(text) -> returns the audio as raw WAV bytes
                                  instead of playing it, so command.py can
                                  send it to the BROWSER to play — this is
                                  what makes the mic button work correctly
                                  for someone else's system, not just yours.
"""

import os
import tempfile

import pyttsx3


def speak(text):
    """Synthesizes `text` with the local system TTS engine and plays it
    immediately on THIS computer's speakers. Safe to call even if the
    engine hiccups — it just logs and returns without raising, so a TTS
    failure never crashes the calling voice/call loop."""
    if not text:
        return

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
        print("[tts] Speech generation error:", e)


def synthesize_to_wav_bytes(text):
    """Synthesizes `text` to a temporary .wav file and returns the raw
    bytes, WITHOUT playing it here. The caller (command.py) sends these
    bytes to whichever browser made the request, so playback happens on
    THEIR device — this is what makes voice replies work correctly for
    someone testing your app remotely, not just for you at your own PC.
    Returns None on failure."""
    if not text:
        return None

    tmp_path = None
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        if len(voices) > 1:
            engine.setProperty('voice', voices[1].id)
        engine.setProperty('rate', 170)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        engine.save_to_file(text, tmp_path)
        engine.runAndWait()
        engine.stop()

        with open(tmp_path, "rb") as f:
            return f.read()

    except Exception as e:
        print("[tts] Speech synthesis (to bytes) error:", e)
        return None
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass