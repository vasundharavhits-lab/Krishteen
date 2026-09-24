"""
FastAPI server with three jobs:

1. POST /incoming-call    - Twilio hits this when someone calls YOUR number
                             (inbound). Replies with TwiML to open a media
                             stream back to us.
2. POST /outbound-answer  - Twilio hits this when a call WE placed (via
                             outbound.py) is answered. Same idea as
                             /incoming-call, but also attaches a "purpose"
                             custom parameter so bot.py knows why it's calling.
3. WS   /ws               - Twilio streams the caller's audio to us here in
                             real time, and we stream the agent's audio back
                             over the same socket. This is where bot.py's
                             pipeline actually runs.
4. POST /call-status      - Optional status callback Twilio hits when an
                             outbound call completes (for logging).

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream

from bot import run_bot

load_dotenv()

app = FastAPI()


@app.post("/incoming-call")
async def incoming_call():
    """Twilio calls this webhook when someone dials your number (inbound)."""
    public_ws_url = os.getenv("PUBLIC_WS_URL")

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=public_ws_url)
    response.append(connect)

    return PlainTextResponse(content=str(response), media_type="application/xml")


@app.post("/outbound-answer")
async def outbound_answer(request: Request):
    """Twilio calls this when a call WE placed (outbound.py) is answered.
    Attaches the call's purpose as a custom stream parameter so bot.py can
    build a purpose-specific system prompt (e.g. booking an appointment)."""
    purpose = request.query_params.get("purpose", "a general call")
    public_ws_url = os.getenv("PUBLIC_WS_URL")

    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=public_ws_url)
    stream.parameter(name="purpose", value=purpose)
    stream.parameter(name="call_direction", value="outbound")
    connect.append(stream)
    response.append(connect)

    return PlainTextResponse(content=str(response), media_type="application/xml")


@app.post("/call-status")
async def call_status(request: Request):
    """Optional: Twilio posts call-completion events here. Just logs for now
    — hook this up to your n8n workflow or DB if you want call history."""
    form = await request.form()
    print(f"Call {form.get('CallSid')} status: {form.get('CallStatus')}")
    return ("", 204)


@app.websocket("/ws")
async def media_stream(websocket: WebSocket):
    """Twilio opens this socket right after the webhook responds."""
    await websocket.accept()

    stream_sid = None
    call_sid = None
    purpose = "a general conversation"
    call_direction = "inbound"

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)

            if data["event"] == "start":
                stream_sid = data["start"]["streamSid"]
                call_sid = data["start"]["callSid"]
                custom_params = data["start"].get("customParameters", {}) or {}
                purpose = custom_params.get("purpose", purpose)
                call_direction = custom_params.get("call_direction", call_direction)
                break

        await run_bot(
            websocket,
            stream_sid,
            call_sid,
            purpose=purpose,
            call_direction=call_direction,
        )

    except WebSocketDisconnect:
        print(f"Call ended: {call_sid}")


@app.get("/")
async def health_check():
    return {"status": "ok"}