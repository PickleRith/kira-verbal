"""Database tables.

Day 1 only needs published lesson versions. Sessions, turns, evidence, reports,
reviews and export events arrive with the milestones that use them, each with
its own migration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
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
