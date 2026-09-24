# krishteen — AI Desktop Voice Assistant

Krishteen is a locally-run, privacy-friendly AI voice and chat assistant for desktop. It combines speech recognition, text-to-speech, and a local LLM (via [Ollama](https://ollama.com)) to answer questions, hold multi-turn conversations, run system commands, and process uploaded files — all without sending data to an external cloud API.

# Features

- **Voice interaction** — listens via microphone (`speech_recognition`) and replies with synthesized speech (`pyttsx3`)
- **Text chat** — type questions directly into the chatbox for a silent, no-mic workflow
- **Local LLM backend** — powered by Ollama (`qwen2.5:1.5b`) so all reasoning happens on-device
- **Conversation memory** — keeps the last few turns of chat history for contextual follow-up answers
- **Configurable answer style** — switch between Concise, Detailed, Bullet Points, Formal, Casual, Simple, and Friendly response styles from the Settings panel
- **File understanding**
  - **PDF** — extracts and summarizes/answers questions about document text
  - **Images** — describes or answers questions about an image using a local vision model (`moondream`)
  - **Audio** — transcribes and summarizes spoken content
  - **Video** — transcribes and summarizes spoken content
- **System & web commands** — "open [app/site]" launches local apps or websites; "play [song] on YouTube" plays it directly
- **Chat history panel** — full conversation log viewable in a scrollable side panel

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, [Eel](https://github.com/python-eel/Eel) (Python ↔ JS bridge) |
| AI / LLM | Ollama (`qwen2.5:1.5b` text, `moondream` vision) |
| Speech | `speech_recognition`, `pyttsx3` |
| Transcription | `faster-whisper` |
| Document parsing | `pypdf` |
| Frontend | HTML, CSS, Bootstrap 5, jQuery, SiriWave, Textillate |
| Storage | SQLite (`krishteen.db`) |

## Project Structure

```
project-root/
├── main.py                # App entry point — starts Eel and opens the UI
├── requirements.txt
├── preferences.json        # Stores selected answer style (auto-created)
├── krishteen.db             # SQLite DB for system/web open commands
├── engine/
│   ├── ai.py                # Prompt construction + Ollama chat calls
│   ├── command.py           # Voice/text command routing, speech output, file-upload handling
│   ├── config.py            # Assistant name & DB name constants
│   ├── db.py                 # DB connection bootstrap
│   ├── features.py          # "open ..." and YouTube playback commands
│   ├── file_processor.py    # PDF/image/audio/video processing helpers
│   └── preferences.py       # Answer-style get/set logic
└── www/
    ├── index.html            # Main UI layout
    ├── main.js                # UI interactions, mic/file/chat handling
    ├── controller.js         # Eel-exposed functions for backend → UI updates
    └── style.css
```

## Prerequisites

1. **Python 3.10+**
2. **[Ollama](https://ollama.com/download)** installed and running locally
3. Required models pulled:
   ```
   ollama pull qwen2.5:1.5b
   ollama pull moondream
   ```
4. **ffmpeg** installed and available on your system PATH (required for audio/video transcription)

## Installation

```bash
# Clone or copy the project, then from the project root:
pip install -r requirements.txt
```

> **Windows note:** `PyAudio` sometimes fails to install via pip. If it does, install a prebuilt wheel or run `pipwin install pyaudio`.

## Running the App

```bash
python main.py
```

This starts the Eel server and opens the assistant UI at `http://localhost:8000/index.html`. Click the mic icon to speak a command, or type into the chatbox and press Enter.

## Configuration

- **Answer style** — accessible via the gear (⚙) icon in the UI; persisted to `preferences.json`
- **Assistant name / DB name** — set in `engine/config.py`
- **Ollama endpoint / model names** — set at the top of `engine/ai.py` and `engine/file_processor.py`

## Known Limitations

- Requires Ollama running locally; the assistant will report a friendly error if it isn't reachable
- PDF/audio/video support depends on optional packages (`pypdf`, `faster-whisper`) — if not installed, those features return an instructional error message instead of crashing
- Voice recognition uses Google's speech-to-text API, which requires an internet connection even though the LLM itself runs locally

## License

Add your preferred license here (e.g., MIT).