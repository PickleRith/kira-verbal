"""Published lessons, read from Postgres.

The database (not the JSON files) is the source of truth at runtime, because sessions
reference lesson_versions by foreign key. Parsed lessons are cached in memory forever:
safe because a published version can never change.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import LessonVersionRecord
from app.domain.models import Lesson


class LessonStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._cache: dict[tuple[str, int], Lesson] = {}

    def get(self, lesson_id: str, version: int) -> Lesson | None:
        key = (lesson_id, version)
        if key not in self._cache:
            with self._session_factory() as db:
                record = db.get(LessonVersionRecord, key)
            if record is None:
                return None
            self._cache[key] = Lesson.model_validate(record.content)
        return self._cache[key]

    def latest(self, lesson_id: str) -> Lesson | None:
        with self._session_factory() as db:
            version = db.scalar(
                select(func.max(LessonVersionRecord.version)).where(
                    LessonVersionRecord.lesson_id == lesson_id
                )
            )
        return None if version is None else self.get(lesson_id, version)

    def list_latest(self) -> list[Lesson]:
        latest = (
            select(LessonVersionRecord.lesson_id, func.max(LessonVersionRecord.version))
            .group_by(LessonVersionRecord.lesson_id)
            .order_by(LessonVersionRecord.lesson_id)
        )
        with self._session_factory() as db:
            keys = [(lesson_id, version) for lesson_id, version in db.execute(latest).all()]
        return [lesson for key in keys if (lesson := self.get(*key)) is not None]
