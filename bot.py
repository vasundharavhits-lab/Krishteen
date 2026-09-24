"""
Defines the Pipecat pipeline that powers one live voice session:

  caller audio -> Gemini Live (STT + LLM + TTS, one service) -> caller audio

100% Gemini: Gemini Live handles STT, the language model, AND TTS in one
speech-to-speech service — no local models, no VAD analyzer to configure
(Gemini Live does its own turn-taking).

No telephony provider: this pipeline talks to whatever client connects to
server.py's /ws WebSocket (browser mic/speaker client, or any other audio
client you build) using pipecat's generic protobuf frame format — nothing
here is tied to a specific carrier.

Purpose-aware: the system prompt is built per-session around why the
session started (e.g. booking an appointment), and the session ends itself
once a closing phrase appears in the agent's own reply.
"""

import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from pipecat.frames.frames import EndFrame, LLMMessagesAppendFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from prompts import GREETING, SYSTEM_PROMPT, OUTBOUND_APPOINTMENT_PROMPT

load_dotenv()

CLOSING_PHRASES = [
    "goodbye", "have a great day", "thanks for your time", "talk soon",
    "that's all booked", "that's confirmed", "see you then",
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore")


async def send_transcript_to_n8n(session_id: str, messages: list, purpose: str = "", call_direction: str = "inbound"):
    """POST the full conversation to the n8n webhook once a session ends."""
    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if not webhook_url:
        print("N8N_WEBHOOK_URL not set — skipping transcript send.")
        return

    payload = {
        "session_id": session_id,
        "call_direction": call_direction,
        "purpose": purpose,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "transcript": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        print(f"Sent transcript for session {session_id} to n8n.")
    except httpx.HTTPError as exc:
        print(f"Failed to send transcript for session {session_id} to n8n: {exc}")


class HangupWatcher(FrameProcessor):
    """Watches the agent's outgoing text for a closing phrase and ends the
    pipeline task when it sees one — no external call-control API needed;
    ending the task naturally closes the WebSocket connection to the client.

    With Gemini Live, there's no separate llm -> tts handoff (one service
    does speech-in -> speech-out directly), so this sits right after the
    llm stage and watches whatever text frames it emits alongside the
    audio (Gemini Live still surfaces the spoken text as TextFrame-family
    frames for transcript/logging purposes, even though audio is what
    actually reaches the client)."""

    def __init__(self, task_ref, session_id: str):
        super().__init__()
        self._task_ref = task_ref
        self._session_id = session_id
        self._done = False

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if not self._done and isinstance(frame, TextFrame):
            lowered = (frame.text or "").lower()
            if any(phrase in lowered for phrase in CLOSING_PHRASES):
                self._done = True
                await self.push_frame(frame, direction)
                await self._task_ref.queue_frame(EndFrame())
                return

        await self.push_frame(frame, direction)


def _build_system_prompt(purpose: str, call_direction: str) -> str:
    if call_direction == "outbound":
        return OUTBOUND_APPOINTMENT_PROMPT.format(purpose=purpose)
    return SYSTEM_PROMPT


async def run_bot(websocket, session_id: str, purpose: str = "", call_direction: str = "inbound"):
    """Build and run one Pipecat pipeline for a single live session."""

    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not set — can't run the session.")
        return

    # Generic protobuf frame format instead of a carrier-specific one — any
    # client that speaks pipecat's protobuf protocol can connect, no
    # telephony provider involved.
    serializer = ProtobufFrameSerializer()
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            # No local VAD analyzer: Gemini Live does its own server-side
            # voice-activity detection as part of the speech-to-speech stream.
            serializer=serializer,
        ),
    )

    system_prompt = _build_system_prompt(purpose, call_direction)

    llm = GeminiLiveLLMService(
        api_key=GEMINI_API_KEY,
        model=GEMINI_LIVE_MODEL,
        voice_id=GEMINI_TTS_VOICE,
        system_instruction=system_prompt,
    )

    messages = [{"role": "system", "content": system_prompt}]
    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)

    hangup_watcher = HangupWatcher(None, session_id)

    # No separate stt/tts stages: Gemini Live consumes and produces raw
    # audio directly, so the watcher sits right after llm.
    pipeline = Pipeline(
        [
            transport.input(),
            context_aggregator.user(),
            llm,
            hangup_watcher,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )
    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
    hangup_watcher._task_ref = task

    opening_line = GREETING if call_direction == "inbound" else _outbound_opening_line(purpose)

    await task.queue_frame(
        LLMMessagesAppendFrame(
            messages=[{"role": "assistant", "content": opening_line}],
            run_llm=True,
        )
    )

    runner = PipelineRunner()
    await runner.run(task)

    # Session has ended — send the full transcript to n8n for appointment
    # extraction / booking.
    await send_transcript_to_n8n(session_id, context.messages, purpose=purpose, call_direction=call_direction)


def _outbound_opening_line(purpose: str) -> str:
    return (
        f"Hi, this is Krishteen, an AI assistant reaching out to help with: {purpose}. "
        "Do you have a moment to talk?"
    )