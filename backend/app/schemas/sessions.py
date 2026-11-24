"""Student-facing session contracts.

Nothing here exposes evaluator output (signals, misconception tags, levels): those are
teacher-only and must never reach the learner's screen or the voice worker's speech.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.state import SessionStatus

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Purpose = Literal["open", "diagnostic", "clarify", "hint", "respond"]
FinishReasonOut = Literal[
    "learner_request", "budget", "objectives_exhausted", "timeout", "learner_exit"
]
MAX_TRANSCRIPT_CHARS = 2000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Prompt(BaseModel):
    question_id: str
    text: str
    purpose: Purpose
    # Said or shown before the question: the agent's reply to the last turn and/or a hint.
    lead_in: str | None = None
    hint: str | None = None


class TranscriptEntry(BaseModel):
    sequence: int
    question_id: str
    question_text: str
    answer: str
    modality: Literal["text", "voice"]
    assisted: bool
    reply: str | None = None  # what the agent said after this turn (lead-in of the next prompt)


class LessonRef(BaseModel):
    id: str
    version: int
    title: str


class StudentSessionView(BaseModel):
    id: uuid.UUID
    lesson: LessonRef
    status: SessionStatus
    state_version: int
    prompt: Prompt | None
    finish_reason: FinishReasonOut | None
    transcript: list[TranscriptEntry]
    deadline_at: datetime


class CreateSessionRequest(_Strict):
    lesson_id: Identifier
    lesson_version: int | None = Field(default=None, ge=1)  # None = latest published
    synthetic_learner_id: Annotated[str, StringConstraints(pattern=r"^demo-[a-z0-9-]{1,40}$")] = (
        "demo-learner"
    )


class CreateSessionResponse(StudentSessionView):
    session_token: str = Field(description="Bearer token for this session. Shown only once.")


class TurnInput(_Strict):
    client_turn_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    expected_state_version: int = Field(ge=0)
    transcript: str = Field(max_length=MAX_TRANSCRIPT_CHARS)
    modality: Literal["text", "voice"]
    question_id: Identifier


class TurnResponse(BaseModel):
    state_version: int
    status: SessionStatus
    prompt: Prompt | None
    finish_reason: FinishReasonOut | None


class FinishRequest(_Strict):
    expected_state_version: int = Field(ge=0)


class VoiceTokenResponse(BaseModel):
    server_url: str
    participant_token: str = Field(description="LiveKit room token; join before expires_at")
    room_name: str
    expires_at: datetime


class ErrorResponse(BaseModel):
    error: str
    message: str
    state_version: int | None = None
