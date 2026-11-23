"""Session and turn queries. Callers own the transaction and any row locks."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import SessionRow, TurnRow


def get_session(db: Session, session_id: uuid.UUID, *, lock: bool) -> SessionRow | None:
    """Load a session; with lock=True, hold a row lock (SELECT ... FOR UPDATE) until commit."""
    return db.get(SessionRow, session_id, with_for_update=lock, populate_existing=lock)


def get_turn_for_update(db: Session, turn_id: uuid.UUID) -> TurnRow | None:
    return db.get(TurnRow, turn_id, with_for_update=True, populate_existing=True)


def find_live_turn(db: Session, session_id: uuid.UUID, client_turn_id: str) -> TurnRow | None:
    return db.scalar(
        select(TurnRow).where(
            TurnRow.session_id == session_id,
            TurnRow.client_turn_id == client_turn_id,
            TurnRow.status != "failed",
        )
    )


def processing_turns(db: Session, session_id: uuid.UUID) -> list[TurnRow]:
    return list(
        db.scalars(
            select(TurnRow).where(TurnRow.session_id == session_id, TurnRow.status == "processing")
        )
    )


def committed_turns(db: Session, session_id: uuid.UUID) -> list[TurnRow]:
    return list(
        db.scalars(
            select(TurnRow)
            .where(TurnRow.session_id == session_id, TurnRow.status == "committed")
            .order_by(TurnRow.sequence)
        )
    )


def next_sequence(db: Session, session_id: uuid.UUID) -> int:
    highest = db.scalar(
        select(func.max(TurnRow.sequence)).where(
            TurnRow.session_id == session_id, TurnRow.status != "failed"
        )
    )
    return (highest or 0) + 1


def question_was_assisted(db: Session, session_id: uuid.UUID, question_id: str) -> bool:
    """True if an earlier committed answer to this question was already assisted."""
    return bool(
        db.scalar(
            select(func.count())
            .select_from(TurnRow)
            .where(
                TurnRow.session_id == session_id,
                TurnRow.question_id == question_id,
                TurnRow.status == "committed",
                TurnRow.assisted.is_(True),
            )
        )
    )
