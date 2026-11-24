"""Teacher-facing contracts: workspaces, sessions list, reports, reviews and exports.

These DO include evaluator output (levels, evidence, misconception tags, intents). They are
served only to the teacher token of the workspace that owns the session, never to a
learner's session token.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.sessions import FinishReasonOut, LessonRef

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
ReviewerId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]
ReportStatus = Literal["pending", "ready_for_review", "approved", "rejected"]
EvidenceStatusOut = Literal["accepted", "abstained", "rejected"]
Level = Annotated[int, Field(ge=0, le=3)]
MAX_REASON_CHARS = 2000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- score ----------------------------------------------------------------------------


GradeBand = Literal["mastered", "proficient", "developing", "beginning", "incomplete"]


class ScoreView(BaseModel):
    """Rubric levels as a score (app/domain/grading.py). Unknown criteria are left out of
    the points, never counted as zero, and make the band "incomplete"."""

    points: int
    max_points: int
    percent: int | None
    assessed: int
    total: int
    band: GradeBand

    @classmethod
    def from_levels(cls, levels: dict[str, int | None]) -> ScoreView:
        from app.domain.grading import grade

        g = grade(levels)
        return cls(
            points=g.points,
            max_points=g.max_points,
            percent=g.percent,
            assessed=g.assessed,
            total=g.total,
            band=g.band,  # type: ignore[arg-type]
        )


# --- workspace and sessions ---------------------------------------------------------


class WorkspaceCreated(BaseModel):
    workspace_id: uuid.UUID
    teacher_token: str = Field(description="Bearer token for this demo classroom. Shown once.")


class WorkspaceView(BaseModel):
    workspace_id: uuid.UUID
    created_at: datetime


class TeacherCreateSession(_Strict):
    lesson_id: Identifier
    synthetic_learner_id: Annotated[str, StringConstraints(pattern=r"^demo-[a-z0-9-]{1,40}$")] = (
        "demo-learner"
    )


class TeacherSessionCreated(BaseModel):
    session_id: uuid.UUID
    session_token: str = Field(description="The learner's token for this session. Shown once.")
    lesson: LessonRef
    synthetic_learner_id: str


class TeacherSessionItem(BaseModel):
    session_id: uuid.UUID
    lesson: LessonRef
    synthetic_learner_id: str
    learner_name: str | None = None  # the student account's display name, if any
    session_status: str
    finish_reason: FinishReasonOut | None
    created_at: datetime
    report_status: ReportStatus
    report_revision: int | None
    answer_turns: int
    wellbeing_flags: int
    score: ScoreView | None = None  # latest revision's levels; None while in progress


# --- report -------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    id: uuid.UUID
    turn_sequence: int
    criterion_id: str
    quote: str
    proposed_level: int | None
    status: EvidenceStatusOut
    assisted: bool
    misconception_tag: str | None
    reason: str
    rejection_reason: str | None
    evaluator_version: str


class MisconceptionRef(BaseModel):
    tag: str
    description: str


class CriterionReport(BaseModel):
    criterion_id: str
    objective: str
    objective_description: str
    level_descriptors: dict[str, str]
    suggested_level: int | None  # system suggestion; None = unknown
    level: int | None  # this revision's level (suggestion in revision 1, teacher's after)
    independent_levels: list[int]
    assisted_levels: list[int]
    misconceptions: list[MisconceptionRef]
    conflicting: bool
    abstentions: int
    rejected: int
    evidence: list[EvidenceItem]  # every item for this criterion, all statuses


class TranscriptTurn(BaseModel):
    sequence: int
    question_id: str
    question_text: str
    answer: str
    modality: Literal["text", "voice"]
    assisted: bool
    intent: str | None
    signal: str | None
    reply: str | None


class RevisionEntry(BaseModel):
    report_id: uuid.UUID
    revision: int
    status: ReportStatus
    created_by: str
    created_at: datetime


class ReviewEntry(BaseModel):
    id: uuid.UUID
    from_revision: int
    to_revision: int
    reviewer_id: str
    decision: Literal["approve", "reject"]
    approved_levels: dict[str, int | None] | None
    reason: str
    created_at: datetime


class ExportEntry(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    report_revision: int
    schema_version: str
    idempotency_key: str
    payload: dict[str, Any]
    created_at: datetime


class Coverage(BaseModel):
    with_evidence: int
    total: int


class ReportView(BaseModel):
    session_id: uuid.UUID
    report_id: uuid.UUID | None  # None while pending (the session is still running)
    revision: int | None
    status: ReportStatus
    lesson: LessonRef
    synthetic_learner_id: str
    learner_name: str | None = None
    session_status: str
    finish_reason: FinishReasonOut | None
    session_created_at: datetime
    coverage: Coverage
    needs_review: bool
    wellbeing_turns: list[int]  # turn sequences where the learner may need follow-up
    hints_used: int
    side_turns: int
    criteria: list[CriterionReport]
    score: ScoreView  # this revision's levels (live suggestion while pending)
    suggested_score: ScoreView  # the system's suggested levels
    transcript: list[TranscriptTurn]
    revisions: list[RevisionEntry]
    reviews: list[ReviewEntry]  # the audit trail, oldest first
    exports: list[ExportEntry]


# --- review and export --------------------------------------------------------------


class ReviewRequest(_Strict):
    decision: Literal["approve", "reject"]
    # Required to approve: every criterion, a level 0-3, or null for "insufficient evidence".
    levels: dict[str, Level | None] | None = None
    reason: str = Field(default="", max_length=MAX_REASON_CHARS)
    reviewer_id: ReviewerId = "demo-teacher"


class ExportResponse(ExportEntry):
    replayed: bool = Field(description="True if this revision was already exported.")
