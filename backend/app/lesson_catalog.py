"""Load and validate versioned lesson fixtures from disk.

Files are named `<lesson_id>.v<version>.json`. The name must agree with the
content so a reviewer can tell from a directory listing which versions exist,
and so a typo cannot silently publish the wrong version. The API calls
`load_catalog` at startup and refuses to start on any invalid fixture.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pydantic import ValidationError

from app.domain.models import Lesson


class LessonFixtureError(Exception):
    """A lesson file is unreadable, invalid, misnamed or duplicated."""


@dataclass(frozen=True)
class LessonCatalog:
    lessons: Mapping[tuple[str, int], Lesson]

    def get(self, lesson_id: str, version: int) -> Lesson | None:
        return self.lessons.get((lesson_id, version))

    def latest(self, lesson_id: str) -> Lesson | None:
        versions = [v for (lid, v) in self.lessons if lid == lesson_id]
        return self.lessons[(lesson_id, max(versions))] if versions else None

    def __iter__(self) -> Iterator[Lesson]:
        return iter(self.lessons[key] for key in sorted(self.lessons))

    def __len__(self) -> int:
        return len(self.lessons)


def content_hash(lesson: Lesson) -> str:
    """SHA-256 of canonical JSON. Used to detect edits to a published version."""
    canonical = json.dumps(
        lesson.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_lesson_file(path: Path) -> Lesson:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LessonFixtureError(f"{path.name}: cannot read JSON: {exc}") from exc
    try:
        lesson = Lesson.model_validate(raw)
    except ValidationError as exc:
        raise LessonFixtureError(f"{path.name}: invalid lesson: {exc}") from exc

    expected_name = f"{lesson.id}.v{lesson.version}.json"
    if path.name != expected_name:
        raise LessonFixtureError(f"{path.name}: content says it should be named {expected_name}")
    return lesson


def load_catalog(directory: Path) -> LessonCatalog:
    files = sorted(directory.glob("*.json"))
    if not files:
        raise LessonFixtureError(f"no lesson fixtures found in {directory}")

    lessons: dict[tuple[str, int], Lesson] = {}
    for path in files:
        lesson = load_lesson_file(path)
        key = (lesson.id, lesson.version)
        if key in lessons:
            raise LessonFixtureError(f"{path.name}: duplicate lesson {key}")
        lessons[key] = lesson
    return LessonCatalog(MappingProxyType(lessons))
