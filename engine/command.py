import time
import base64
import pyttsx3
import speech_recognition as sr
import eel

from engine.ai import askAI
from engine.ai import askAI, clear_session
from engine.preferences import set_style, get_style, get_all_styles
from engine.file_processor import save_base64_file, extract_pdf_text, describe_image, transcribe_video
from engine.scheduler import handle_scheduling_command
from engine.mic_guard import try_acquire_mic, release_mic
from engine.call_trigger import handle_call_command
from engine.role_trigger import handle_role_command
from engine.tts import synthesize_to_wav_bytes


def speak(text):
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    if len(voices) > 1:
        engine.setProperty('voice', voices[1].id)
    engine.setProperty('rate', 170)
    eel.DisplayMessage(text)
    engine.say(text)
    engine.runAndWait()

@eel.expose
def getTextResponse(query, session_id="chat"):
    """
    Text-only router for browser-based voice modes.
    Runs through the same command detection (alarms, roles, open, youtube, AI)
    but returns plain text — the browser will speak it locally.
    """
    return compute_response(query, session_id=session_id)


@eel.expose
def clearBrowserSession(session_id):
    clear_session(session_id)


@eel.expose
def takeCommand():
    if not try_acquire_mic(timeout=5):
        eel.DisplayMessage('Microphone is busy, try again in a moment.')
        return ""

    try:
        r = sr.Recognizer()
        r.pause_threshold = 1

        # FIX: Don't hardcode device_index. Try default, then 0, then 1.
        mic = None
        for idx in [None, 0, 1]:
            try:
                if idx is None:
                    mic = sr.Microphone()
                else:
                    mic = sr.Microphone(device_index=idx)
                with mic as source:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                break
            except Exception as e:
                print(f"[takeCommand] Mic index {idx} unavailable: {e}")
                mic = None

        if mic is None:
            eel.DisplayMessage("No working microphone found on this computer.")
            return ""

        try:
            with mic as source:
                print('Listening...')
                eel.DisplayMessage('Listening...')
                audio = r.listen(source, timeout=10, phrase_time_limit=6)
        except sr.WaitTimeoutError:
            print("No speech detected before timeout.")
            eel.DisplayMessage("I didn't hear anything.")
            return ""
        except Exception as e:
            print("Microphone error:", e)
            eel.DisplayMessage("Sorry, I couldn't access the microphone.")
            return ""

        try:
            print('Recognizing...')
            eel.DisplayMessage('Recognizing...')
            query = r.recognize_google(audio, language='en')
            print(f'User said: {query}')
            time.sleep(2)
            eel.DisplayMessage(query)

        except Exception:
            return ""

        return query.lower()
    finally:
        release_mic()


@eel.expose
def getResponseStyle():
    """Returns the currently selected style key and the full list of options."""
    return {"current": get_style(), "options": get_all_styles()}


@eel.expose
def setResponseStyle(style):
    """Called from the settings UI when the user picks a new answer style."""
    new_style = set_style(style)
    print("Response style changed to:", new_style)
    return new_style


@eel.expose
def handleFileUpload(filename, filetype, base64_data, question=None):
    """
    filetype: 'pdf' | 'image' | 'audio' | 'video'
    Saves the uploaded file, processes it appropriately (extract / describe /
    transcribe), then answers via Ollama, speaking and logging the result
    just like a normal chat message.
    """
    label = f"Uploaded: {filename}"
    if question:
        label += f" — {question}"
    eel.LogUserMessage(label)
    eel.DisplayMessage('Processing file...')

    try:
        path = save_base64_file(filename, base64_data)
    except Exception as e:
        error_msg = f"Sorry, I couldn't save that file: {str(e)}"
        eel.LogAssistantMessage(error_msg)
        speak(error_msg)
        eel.ShowHood()
        return

    if filetype == "pdf":
        text, error = extract_pdf_text(path)
        if error:
            eel.LogAssistantMessage(error)
            speak(error)
        else:
            q = question if question else "Summarize this document."
            combined_query = f"Here is the content of a PDF the user uploaded:\n\n{text}\n\nUser's request: {q}"
            print("Sending PDF content to Ollama...")
            eel.DisplayMessage('Thinking...')
            response = askAI(combined_query)
            eel.LogAssistantMessage(response)
            speak(response)

    elif filetype == "image":
        eel.DisplayMessage('Looking at the image...')
        answer, error = describe_image(path, question)
        if error:
            eel.LogAssistantMessage(error)
            speak(error)
        else:
            eel.LogAssistantMessage(answer)
            speak(answer)

    elif filetype == "audio":
        eel.DisplayMessage('Transcribing audio, this may take a moment...')
        text, error = transcribe_video(path)
        if error:
            eel.LogAssistantMessage(error)
            speak(error)
        else:
            q = question if question else "Summarize what was said in this audio."
            combined_query = f"Here is a transcript from an audio file the user uploaded:\n\n{text}\n\nUser's request: {q}"
            print("Sending audio transcript to Ollama...")
            eel.DisplayMessage('Thinking...')
            response = askAI(combined_query)
            eel.LogAssistantMessage(response)
            speak(response)

    elif filetype == "video":
        eel.DisplayMessage('Transcribing video, this may take a while...')
        text, error = transcribe_video(path)
        if error:
            eel.LogAssistantMessage(error)
            speak(error)
        else:
            q = question if question else "Summarize what was said in this video."
            combined_query = f"Here is a transcript from a video the user uploaded:\n\n{text}\n\nUser's request: {q}"
            print("Sending video transcript to Ollama...")
            eel.DisplayMessage('Thinking...')
            response = askAI(combined_query)
            eel.LogAssistantMessage(response)
            speak(response)

    else:
        error_msg = "I don't know how to handle that file type."
        eel.LogAssistantMessage(error_msg)
        speak(error_msg)

    eel.ShowHood()


def compute_response(query, session_id="chat"):
    """
    Given a recognized/typed request, decides what to do and returns the
    reply TEXT ONLY — no speaking, no eel logging. This is the shared logic
    behind route_and_respond() (typed chatbox / mic button / wake word,
    which speak locally on THIS machine) AND handleVoiceMessage() (browser
    mic recordings, which need the text to synthesize audio for the
    BROWSER to play instead).

    Order of checks, same as before:
      1. "call <number> ..." commands
      2. role set/clear/query commands
      3. alarm / reminder / appointment / schedule commands
      4. "open ..." commands (side effect happens locally on this machine
         regardless of who asked — opening a browser tab only makes sense
         on the computer running Krishteen)
      5. "play ... on youtube" commands (same local-only caveat as above)
      6. everything else falls through to the local Ollama model
    """
    query = query.strip()
    if query == "":
        return ""

    lowered = query.lower()

    call_reply = handle_call_command(query)
    if call_reply is not None:
        return call_reply

    role_reply = handle_role_command(query, session_id=session_id)
    if role_reply is not None:
        return role_reply

    scheduling_reply = handle_scheduling_command(query)
    if scheduling_reply is not None:
        return scheduling_reply

    if 'open' in lowered:
        from engine.features import openCommand
        openCommand(lowered)
        return f"Opening {lowered.replace('open', '').strip()} on the Krishteen computer now."

    if 'play' in lowered and 'on youtube' in lowered:
        from engine.features import PlayYoutube
        PlayYoutube(lowered)
        return "Playing that on YouTube now, on the Krishteen computer."

    return askAI(query, session_id=session_id)


def route_and_respond(query):
    """
    Speaks + logs the result of compute_response() LOCALLY (on this
    machine's own speakers) — this is what the typed chatbox, the mic
    button, and the wake-word listener use, all of which only make sense
    for whoever is physically at this computer.
    """
    query = query.strip()
    if query == "":
        return

    eel.DisplayMessage('Thinking...')
    response = compute_response(query, session_id="chat")
    eel.LogAssistantMessage(response)
    speak(response)


@eel.expose
def allCommands(message=None):
    """
    Main command router.
    - Called with no args -> listens for a voice command via the mic.
    - Called with `message` -> treats it as typed chat text (from the chatbox).
    """
    if message:
        query = message.strip().lower()
    else:
        query = takeCommand()

    print(query)

    if query == "":
        eel.ShowHood()
        return

    eel.LogUserMessage(query)
    route_and_respond(query)
    eel.ShowHood()


@eel.expose
def handleVoiceMessage(base64_audio_data, audio_format="webm"):
    """
    Voice input/output that works correctly for ANYONE viewing the page,
    not just whoever is at this computer.

    The BROWSER records audio as WebM/Opus and sends it here as base64.
    The reply is synthesized to WAV bytes and sent BACK to the browser
    to play — so both listening and speaking happen on the remote user's
    device, not your server microphone.
    """
    try:
        # FIX: Browser MediaRecorder sends WebM, not WAV. Save with the
        # right extension so ffmpeg (used by faster-whisper) decodes it.
        ext = "webm" if "webm" in audio_format.lower() else "wav"
        path = save_base64_file(f"browser-voice-message.{ext}", base64_audio_data)
    except Exception as e:
        return {"query": "", "response": f"Sorry, I couldn't process that recording: {str(e)}", "audio_base64": None}

    # Reuses Whisper transcription — ffmpeg handles webm automatically
    query, error = transcribe_video(path)
    if error or not query:
        response_text = error or "I didn't catch that — could you try again?"
        return {"query": "", "response": response_text, "audio_base64": None}

    response_text = compute_response(query, session_id="chat")

    audio_bytes = synthesize_to_wav_bytes(response_text)
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None

    return {"query": query, "response": response_text, "audio_base64": audio_base64}