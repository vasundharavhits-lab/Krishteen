"""
engine/stt.py — Speech INPUT (mic audio -> text), 100% open-source and
local via faster-whisper (Whisper running on your own machine). No cloud
API, no API key, no per-request cost or quota — the only network use is a
one-time model download the first time you run it.

Keeps the same transcribe_audio_data(audio_data) contract this file had
before, so anything that imports engine.stt doesn't need to change — just
this file's internals swapped from Gemini to local Whisper.

Model size: "tiny" by default (fast, good enough for commands/wake word).
Override with WHISPER_MODEL_SIZE in .env (e.g. "base" or "small") for
better accuracy at the cost of speed — useful if you want higher quality
for the in-app Call feature specifically.
"""

import os
import tempfile

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")

# Audio clips shorter than this are almost certainly a cough, click, chair
# creak, or other noise blip crossing the mic's energy threshold — not
# actual speech. Skipping these locally avoids a wasted transcription pass.
MIN_AUDIO_SECONDS = 0.5

_model = None


def _get_model():
    """Loads the Whisper model once and reuses it across calls — loading
    it fresh every time would be slow."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe_audio_data(audio_data):
    """Takes a speech_recognition AudioData object (from recognizer.listen())
    and returns the transcribed text via local Whisper, or '' if nothing was
    understood / on any failure. Mirrors the old recognize_google()/Gemini
    contract (empty/exception -> caller treats it as silence)."""
    # Local, instant, free duration check — no model involved, just math on
    # the raw audio buffer. Skips a wasted transcription pass for noise blips.
    try:
        duration = len(audio_data.get_raw_data()) / (
            audio_data.sample_rate * audio_data.sample_width
        )
        if duration < MIN_AUDIO_SECONDS:
            return ""
    except Exception:
        pass  # if duration can't be computed for some reason, fall through and try anyway

    tmp_path = None
    try:
        model = _get_model()

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.write(audio_data.get_wav_data())
        tmp.close()

        segments, info = model.transcribe(tmp_path, language="en")
        text = "".join(segment.text for segment in segments).strip()
        return text

    except ImportError:
        print("[stt] faster-whisper isn't installed — run: pip install faster-whisper")
        return ""
    except Exception as e:
        print("[stt] Whisper transcription error:", e)
        return ""
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass