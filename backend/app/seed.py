"""Publish the synthetic lesson fixtures into Postgres.

Usage (from backend/, venv active, after `alembic upgrade head`):

    python -m app.seed

Safe to rerun: unchanged versions are skipped. All lessons are published in one
transaction, so a conflict on any lesson leaves the database untouched.
"""

from __future__ import annotations

import sys

from app.config import get_settings
from app.db.session import make_engine, make_session_factory
from app.lesson_catalog import LessonFixtureError, load_catalog
from app.repositories.lessons import LessonVersionConflictError, publish_lesson


def main() -> int:
    settings = get_settings()
    try:
        catalog = load_catalog(settings.lessons_dir)
    except LessonFixtureError as exc:
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    try:
        with session_factory.begin() as session:
            for lesson in catalog:
                result = publish_lesson(session, lesson)
                print(f"{lesson.id} v{lesson.version}: {result.value}")
    except LessonVersionConflictError as exc:
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
