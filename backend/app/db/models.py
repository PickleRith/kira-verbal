"""Database tables.

Constraints here are correctness guarantees, not just documentation:

* lesson_versions: (lesson_id, version) primary key; rows immutable (trigger, migration 0001).
* sessions: pinned to one lesson version by foreign key; status restricted to the state machine's
  values. `state_version` is the optimistic-concurrency counter clients echo back.
* turns: at most one *live* (not failed) turn per (session, client_turn_id) and per
  (session, sequence). Partial unique indexes let a failed attempt be retried with the same
  client_turn_id while still forbidding two committed copies of one turn.

Timestamps are written from the application clock (UTC) so tests can control time.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LessonVersionRecord(Base):
    """One immutable published version of a lesson.

    The composite primary key means (lesson_id, version) can exist only once.
    A database trigger (see migration 0001) rejects UPDATEs, so content cannot be
    changed after publication even by code that bypasses the repository.
    """

    __tablename__ = "lesson_versions"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_lesson_versions_version_positive"),)

    lesson_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


SESSION_STATUSES = "('created','awaiting_answer','evaluating','completed','incomplete')"
PROMPT_PURPOSES = "('open','diagnostic','clarify','hint')"
TURN_STATUSES = "('processing','committed','failed')"


class SessionRow(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["lesson_id", "lesson_version"],
            ["lesson_versions.lesson_id", "lesson_versions.version"],
            name="fk_sessions_lesson_version",
        ),
        CheckConstraint(f"status IN {SESSION_STATUSES}", name="ck_sessions_status"),
        CheckConstraint(
            f"current_purpose IS NULL OR current_purpose IN {PROMPT_PURPOSES}",
            name="ck_sessions_purpose",
        ),
        CheckConstraint("state_version >= 0", name="ck_sessions_state_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    synthetic_learner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lesson_id: Mapped[str] = mapped_column(String(64), nullable=False)
    lesson_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Only a hash is stored; the raw token is shown to the client once, at creation.
    access_token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_question_id: Mapped[str | None] = mapped_column(String(64))
    current_purpose: Mapped[str | None] = mapped_column(String(16))
    current_hint_index: Mapped[int | None] = mapped_column(Integer)
    finish_reason: Mapped[str | None] = mapped_column(String(32))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TurnRow(Base):
    __tablename__ = "turns"
    __table_args__ = (
        Index(
            "uq_turns_live_client_turn_id",
            "session_id",
            "client_turn_id",
            unique=True,
            postgresql_where=text("status <> 'failed'"),
        ),
        Index(
            "uq_turns_live_sequence",
            "session_id",
            "sequence",
            unique=True,
            postgresql_where=text("status <> 'failed'"),
        ),
        CheckConstraint(f"status IN {TURN_STATUSES}", name="ck_turns_status"),
        CheckConstraint("modality IN ('text','voice')", name="ck_turns_modality"),
        CheckConstraint("sequence >= 1", name="ck_turns_sequence"),
        CheckConstraint(
            "status <> 'committed' OR (signal IS NOT NULL AND response IS NOT NULL)",
            name="ck_turns_committed_complete",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_turn_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    modality: Mapped[str] = mapped_column(String(8), nullable=False)
    assisted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    signal: Mapped[str | None] = mapped_column(String(32))
    misconception_tag: Mapped[str | None] = mapped_column(String(64))
    evaluator_version: Mapped[str | None] = mapped_column(String(128))
    # The exact student-facing response, replayed verbatim for idempotent retries.
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


EVIDENCE_STATUSES = "('accepted','abstained','rejected')"


class EvidenceRow(Base):
    """One proposed evidence item for one committed turn, after validation.

    Teacher-only. Rejected items are kept for audit (e.g. to measure how often the model
    invents quotes) but never count toward a suggested level. Rows are written in the same
    transaction that commits their turn, so a turn's evidence exists exactly once.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_session", "session_id"),
        CheckConstraint(f"validation_status IN {EVIDENCE_STATUSES}", name="ck_evidence_status"),
        CheckConstraint(
            "proposed_level IS NULL OR proposed_level BETWEEN 0 AND 3", name="ck_evidence_level"
        ),
        CheckConstraint(
            "validation_status <> 'accepted' OR proposed_level IS NOT NULL",
            name="ck_evidence_accepted_has_level",
        ),
        CheckConstraint(
            "(validation_status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="ck_evidence_rejection_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )
    criterion_id: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str | None] = mapped_column(String(64))
    proposed_level: Mapped[int | None] = mapped_column(Integer)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    misconception_tag: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Independent vs assisted: copied from the turn so it can never be recomputed differently.
    assisted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
