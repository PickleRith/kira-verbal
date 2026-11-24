"""LiveKit voice worker entrypoint.

    pip install -e ".[voice]"
    python -m app.voice.worker dev      # connects to LIVEKIT_URL and waits for dispatches

Built from the LiveKit docs (checked 2026-11-23 against livekit-agents 1.8.13):
* STT-only agent with no LLM, replying from code: on_user_turn_completed + StopResponse,
  as in the official multi-user-transcriber example.
* session.say(text) for speech; interruptions are on by default (barge-in stops playback).
* LiveKit Inference for STT, TTS and turn detection: no separate speech-provider keys.
* user_away_timeout + "user_state_changed" for silent learners.
* Job metadata (ctx.job.metadata) carries the session id and the worker credential.

Not run against a live LiveKit project in this repository yet (no credentials configured).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterable

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    ModelSettings,
    StopResponse,
    TurnHandlingOptions,
    UserStateChangedEvent,
    inference,
    llm,
)

from app.config import REPO_ROOT, get_settings
from app.voice.client import KiraClient
from app.voice.transport import VoiceTurnBridge

load_dotenv(REPO_ROOT / ".env")  # LiveKit SDK reads LIVEKIT_URL / _API_KEY / _API_SECRET
logger = logging.getLogger("kira-verbal.voice")
settings = get_settings()
server = AgentServer()

FILLER_AFTER_SECONDS = 1.5
FILLER = "Thanks. One moment."


class AssessmentVoiceAgent(Agent):
    """Speaks prompts chosen by the API; forwards finalized learner turns to it."""

    def __init__(self, bridge: VoiceTurnBridge) -> None:
        super().__init__(instructions="Unused: no LLM. Prompts come from the Kira Verbal API.")
        self._bridge = bridge
        self._lock = asyncio.Lock()  # one turn in flight at a time
        self._generation = 0  # bumps on every learner turn; stale replies are dropped
        self._turn_ended_at: float | None = None  # for end-of-turn -> first-audio latency

    async def on_enter(self) -> None:
        self.session.say(await self._bridge.opening())

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        self._generation += 1
        generation = self._generation
        ended_at = time.perf_counter()
        transcript = new_message.text_content or ""

        async with self._lock:
            task = asyncio.create_task(self._bridge.handle_final_transcript(transcript))
            done, _ = await asyncio.wait({task}, timeout=FILLER_AFTER_SECONDS)
            if not done:  # evaluation is slow (e.g. LLM evaluator): acknowledge the learner
                self.session.say(FILLER, add_to_chat_ctx=False)
            speech = await task

        backend_ms = (time.perf_counter() - ended_at) * 1000
        logger.info(
            "voice_turn",
            extra={
                "backend_ms": round(backend_ms),
                "chars": len(transcript),
                "spoken": bool(speech),
            },
        )
        # If the learner spoke again while we waited, this reply is stale: the newer turn
        # will speak the current prompt instead.
        if speech and generation == self._generation:
            self._turn_ended_at = ended_at
            handle = self.session.say(speech)
            if self._bridge.finished:
                asyncio.create_task(self._close_after(handle))
        raise StopResponse()  # no LLM reply: the API decides what comes next

    async def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        started, self._turn_ended_at = self._turn_ended_at, None
        first = True
        async for frame in Agent.default.tts_node(self, text, model_settings):
            if first and started is not None:
                ms = (time.perf_counter() - started) * 1000
                logger.info("voice_latency", extra={"end_of_turn_to_first_audio_ms": round(ms)})
            first = False
            yield frame

    async def reprompt(self) -> None:
        speech = await self._bridge.reprompt()
        if speech:
            self.session.say(speech)

    async def _close_after(self, handle) -> None:  # noqa: ANN001 - SpeechHandle
        await handle.wait_for_playout()
        self.session.shutdown(drain=True)


@server.rtc_session(agent_name=settings.voice_agent_name)
async def entrypoint(ctx: JobContext) -> None:
    metadata = json.loads(ctx.job.metadata or "{}")
    session_id, credential = metadata["session_id"], metadata["credential"]
    ctx.log_context_fields = {"kira_session_id": session_id}  # never log transcripts

    client = KiraClient(settings.kira_api_url, credential)
    ctx.add_shutdown_callback(client.aclose)
    agent = AssessmentVoiceAgent(VoiceTurnBridge(client, session_id))

    session = AgentSession(
        stt=inference.STT(model=settings.voice_stt_model),
        tts=inference.TTS(model=settings.voice_tts_model, voice=settings.voice_tts_voice),
        turn_handling=TurnHandlingOptions(turn_detection=inference.TurnDetector()),
        user_away_timeout=settings.voice_user_away_seconds,
    )

    @session.on("user_state_changed")
    def on_user_state_changed(event: UserStateChangedEvent) -> None:
        if event.new_state == "away":
            asyncio.create_task(agent.reprompt())

    await session.start(room=ctx.room, agent=agent)


if __name__ == "__main__":
    agents.cli.run_app(server)
