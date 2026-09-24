"""
Test your AI voice agent using your computer's microphone and speakers -
no phone number, no Twilio, no ngrok needed. Completely free.

Run with:
    python run_local.py

Then just talk into your microphone. Press Ctrl+C to stop.
"""
import asyncio
import os

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMMessagesAppendFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.piper.tts import PiperTTSService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from dotenv import load_dotenv
from bot import send_transcript_to_n8n
from prompts import GREETING, SYSTEM_PROMPT

load_dotenv()


async def main():
    print("Starting your AI voice agent (local mic/speaker mode)...")
    print("Talk into your microphone once you see 'Listening...' below.")
    print("Press Ctrl+C to stop.\n")

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            input_device_index=1,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )

    stt = WhisperSTTService(model="tiny")
    print("Using Ollama model:", os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    llm = OLLamaLLMService(model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    from pathlib import Path
    tts=PiperTTSService(
        voice_id="en_US-lessac-medium",
        download_dir=Path("models/piper"),
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

    await task.queue_frame(
        LLMMessagesAppendFrame(
            messages=[{"role": "assistant", "content": GREETING}],
            run_llm=True,
        )
    )

    runner = PipelineRunner()
    try:
        await runner.run(task)
    finally:
        # Send the transcript to n8n once this local test session ends
        # (Ctrl+C or idle timeout), same as a real call would.
        await send_transcript_to_n8n("local-test-session", context.messages)


if __name__ == "__main__":
    asyncio.run(main())