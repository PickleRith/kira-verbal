import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import LessonVersionRecord
from app.lesson_catalog import load_catalog
from app.main import create_app
from app.repositories.lessons import LessonVersionConflictError, PublishResult, publish_lesson

pytestmark = pytest.mark.integration


def test_seed_publishes_each_version_once_and_is_idempotent(db_session: Session, lessons_dir):
    catalog = load_catalog(lessons_dir)
    first = [publish_lesson(db_session, lesson) for lesson in catalog]
    second = [publish_lesson(db_session, lesson) for lesson in catalog]
    assert first == [PublishResult.INSERTED] * len(catalog)
    assert second == [PublishResult.UNCHANGED] * len(catalog)
    count = db_session.scalar(select(func.count()).select_from(LessonVersionRecord))
    assert count == len(catalog)


def test_republishing_changed_content_under_same_version_conflicts(
    db_session: Session, photosynthesis
):
    publish_lesson(db_session, photosynthesis)
    edited = photosynthesis.model_copy(update={"title": "Photosynthesis (edited)"})
    with pytest.raises(LessonVersionConflictError, match="create v2"):
        publish_lesson(db_session, edited)


def test_bumped_version_publishes_alongside_old(db_session: Session, photosynthesis):
    publish_lesson(db_session, photosynthesis)
    v2 = photosynthesis.model_copy(update={"version": 2, "title": "Photosynthesis v2"})
    assert publish_lesson(db_session, v2) is PublishResult.INSERTED


def test_database_rejects_in_place_updates(db_session: Session, photosynthesis):
    publish_lesson(db_session, photosynthesis)
    with pytest.raises(DBAPIError, match="immutable"):
        db_session.execute(
            text("UPDATE lesson_versions SET title = 'x' WHERE lesson_id = 'photosynthesis'")
        )


def test_database_rejects_duplicate_primary_key(db_session: Session, photosynthesis):
    publish_lesson(db_session, photosynthesis)
    db_session.add(
        LessonVersionRecord(
            lesson_id="photosynthesis", version=1, title="dup", content={}, content_sha256="0" * 64
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_migrations_downgrade_and_reapply(alembic_cfg, migrated_engine):
    command.downgrade(alembic_cfg, "base")
    assert "lesson_versions" not in inspect(migrated_engine).get_table_names()
    command.upgrade(alembic_cfg, "head")
    assert "lesson_versions" in inspect(migrated_engine).get_table_names()


def test_ready_against_real_services(database_url: str, migrated_engine, redis_url: str):
    settings = Settings(database_url=database_url, redis_url=redis_url)
    with TestClient(create_app(settings)) as client:
        response = client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "ok", "redis": "ok", "lessons": "ok"}
