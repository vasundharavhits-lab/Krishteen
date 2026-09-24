import os
import base64
import requests

OLLAMA_URL_GENERATE = "http://localhost:11434/api/generate"
VISION_MODEL = "moondream" 


def save_base64_file(filename, base64_data):
    """
    Decode a base64 (optionally data-URL-prefixed) string and save it to
    an 'uploads' folder in the project root. Returns the saved file path.
    """
    uploads_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    safe_name = os.path.basename(filename)
    path = os.path.join(uploads_dir, safe_name)

    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]

    with open(path, "wb") as f:
        f.write(base64.b64decode(base64_data))

    return path


def extract_pdf_text(path, max_chars=8000):
    """Returns (text, error). Only one will be non-None."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, "PDF support isn't installed yet. Run: pip install pypdf"

    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
            if len(text) > max_chars:
                break
        text = text[:max_chars].strip()

        if not text:
            return None, "I couldn't find any readable text in that PDF — it might be a scanned image."

        return text, None
    except Exception as e:
        return None, f"Error reading PDF: {str(e)}"


def describe_image(path, question=None):
    """Returns (answer, error). Only one will be non-None."""
    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        prompt = question if question else "Describe this image in detail."

        response = requests.post(
            OLLAMA_URL_GENERATE,
            json={
                "model": VISION_MODEL, #moondrean img
                "prompt": prompt,
                "images": [img_b64],
                "stream": False
            },
            timeout=180
        )

        if response.status_code != 200:
            return None, (
                f"Vision model error (status {response.status_code}). "
                f"Make sure you've run: ollama pull {VISION_MODEL}"
            )

        data = response.json()
        answer = data.get("response", "").strip()
        return (answer or "I couldn't generate a description."), None

    except requests.exceptions.ConnectionError:
        return None, "Ollama is not running. Please start Ollama."
    except requests.exceptions.Timeout:
        return None, "Analyzing the image is taking too long."
    except Exception as e:
        return None, (
            f"Error analyzing image: {str(e)}. "
            f"Make sure you've run: ollama pull {VISION_MODEL}"
        )


def transcribe_video(path, max_chars=6000):
    """Returns (transcript, error). Only one will be non-None."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None, (
            "Video transcription isn't installed yet. Run: "
            "pip install faster-whisper  (and make sure ffmpeg is installed and on PATH)"
        )

    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(path)

        text = ""
        for segment in segments:
            text += segment.text + " "
            if len(text) > max_chars:
                break
        text = text.strip()[:max_chars]

        if not text:
            return None, "I couldn't detect any speech in that video."

        return text, None
    except Exception as e:
        return None, f"Error transcribing video: {str(e)}. Make sure ffmpeg is installed and on PATH."