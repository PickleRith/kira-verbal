"""Turn forwarding for the voice worker: decide what to submit and what to say.

Rules:
* Only a finalized learner turn is submitted, as `modality="voice"`, to the same
  `/v1/sessions/{id}/turns` endpoint the text UI uses. Partial transcripts never reach the API.
* Only the learner's words are submitted. The agent's own speech never enters the
  transcript, because the worker never sends it.
* Every answer gets a fresh client_turn_id. A network error is retried with the SAME id, so a
  request that actually succeeded is not counted twice.
* The API's state_version is echoed back. If the learner also typed in the browser, the API
  answers 409 and the bridge refetches and speaks the current question; it never guesses.
* Speech is built only from the API's prompt text, lead-ins and fixed messages here. Nothing
  about evaluation (levels, misconceptions) is ever spoken.

No LiveKit imports, so this runs in plain unit tests against the real API.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx

from app.voice.client import ApiError, KiraClient

MAX_TRANSCRIPT_CHARS = 2000
MAX_REPROMPTS = 2
IN_PROGRESS_RETRY_SECONDS = 1.0

INTRO = (
    "Hi! This is a short spoken check-in about {title}. Answer in your own words; there are "
    "no trick questions. You can ask for a hint, or say stop to finish. "
)
CLOSING = {
    "timeout": (
        "Time's up, so the assessment is finished. "
        "Your teacher will review the answers you gave and decide your results."
    ),
    "learner_exit": (
        "You've finished early, so the assessment is over. "
        "Your teacher will review the answers you gave and decide your results."
    ),
}
DEFAULT_CLOSING = (
    "That was the last question, so the assessment is finished. "
    "Your teacher will review your answers and decide your results."
)
RETRY_ANSWER = "Sorry, I couldn't process that just now. Could you say your answer again?"
LOST_ANSWER = "Sorry, I lost that answer. Could you say it again?"
RESYNC = "Let's pick up from where we are. "
TROUBLE = (
    "I'm having trouble reaching the assessment right now. "
    "You can keep going by typing your answer on the screen."
)
REPROMPT = "Take your time. "
TERMINAL = {"completed", "incomplete"}


class VoiceTurnBridge:
    def __init__(self, client: KiraClient, session_id: str) -> None:
        self._client = client
        self._session_id = session_id
        self._state: dict[str, Any] | None = None  # latest view of status / version / prompt
        self._title = "this lesson"
        self._reprompts = 0

    # --- what the worker calls ------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self._state is not None and self._state["status"] in TERMINAL

    async def opening(self) -> str:
        await self._refresh()
        if self.finished:
            return self._speech()
        return INTRO.format(title=self._title) + self._speech()

    async def handle_final_transcript(self, transcript: str) -> str | None:
        """Submit one finalized learner turn; return what to say next (None = say nothing)."""
        text = transcript.strip()
        if not text:
            return None  # noise or an empty turn: don't spend a question on it
        try:
            if self._state is None:
                await self._refresh()
            if self.finished:
                return self._speech()
            prompt = self._state["prompt"]  # type: ignore[index]
            body = {
                "client_turn_id": f"voice-{uuid.uuid4().hex}",
                "expected_state_version": self._state["state_version"],  # type: ignore[index]
                "transcript": text[:MAX_TRANSCRIPT_CHARS],
                "modality": "voice",
                "question_id": prompt["question_id"],
            }
            result = await self._submit(body)
        except ApiError as error:
            return await self._recover(error)
        except httpx.HTTPError:
            return TROUBLE

        self._state = {**(self._state or {}), **result}
        self._reprompts = 0
        return self._speech()

    async def reprompt(self) -> str | None:
        """Called when the learner has been silent for a while. Bounded, never scored."""
        if self._state is None or self.finished or self._reprompts >= MAX_REPROMPTS:
            return None
        self._reprompts += 1
        return REPROMPT + self._speech()

    # --- internals ------------------------------------------------------------------

    async def _refresh(self) -> None:
        view = await self._client.get_session(self._session_id)
        self._title = view.get("lesson", {}).get("title", self._title)
        self._state = view

    async def _submit(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            try:
                return await self._client.submit_turn(self._session_id, body)
            except httpx.TransportError:
                if attempt == 2:
                    raise  # same body each time: safe to retry, never double-counted
            except ApiError as error:
                if error.code != "turn_in_progress" or attempt == 2:
                    raise
                await asyncio.sleep(IN_PROGRESS_RETRY_SECONDS)
        raise AssertionError("unreachable")

    async def _recover(self, error: ApiError) -> str:
        try:
            await self._refresh()
        except (ApiError, httpx.HTTPError):
            return TROUBLE
        if self.finished:
            return self._speech()
        if error.code == "evaluation_unavailable":
            return RETRY_ANSWER
        if error.code == "claim_lost":
            return LOST_ANSWER
        if error.code in {"stale_state_version", "question_mismatch", "turn_in_progress"}:
            return RESYNC + self._speech()
        return TROUBLE

    def _speech(self) -> str:
        assert self._state is not None
        if self._state["status"] in TERMINAL:
            return CLOSING.get(self._state.get("finish_reason") or "", DEFAULT_CLOSING)
        prompt = self._state.get("prompt")
        if not prompt:
            return TROUBLE
        lead_in = prompt.get("lead_in")
        return f"{lead_in} {prompt['text']}" if lead_in else prompt["text"]
