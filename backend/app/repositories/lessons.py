"""Publish lesson versions idempotently.

Publishing the same content twice is a no-op. Publishing different content
under an existing (id, version) is an error: to change a lesson, bump its
version. Existing sessions keep pointing at the version they started with.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.orm import Session

from app.db.models import LessonVersionRecord
from app.domain.models import Lesson
from app.lesson_catalog import content_hash


class LessonVersionConflictError(Exception):
    """Published content for this (id, version) differs from the fixture."""


class PublishResult(StrEnum):
    INSERTED = "inserted"
    UNCHANGED = "unchanged"


def publish_lesson(session: Session, lesson: Lesson) -> PublishResult:
    digest = content_hash(lesson)
    existing = session.get(LessonVersionRecord, (lesson.id, lesson.version))
    if existing is not None:
        if existing.content_sha256 != digest:
            raise LessonVersionConflictError(
                f"{lesson.id} v{lesson.version} is already published with different content; "
                f"create v{lesson.version + 1} instead of editing a published version"
            )
        return PublishResult.UNCHANGED

    session.add(
        LessonVersionRecord(
            lesson_id=lesson.id,
            version=lesson.version,
            title=lesson.title,
            content=lesson.model_dump(mode="json"),
            content_sha256=digest,
        )
    )
    session.flush()
    return PublishResult.INSERTED
