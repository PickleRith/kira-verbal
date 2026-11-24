"""Retention purge and log redaction."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker
from test_reports import GOOD_Q1, Teacher, finished_report, levels  # same folder

from app.db.models import ExportEventRow, ReportRow, SessionRow, TurnRow, WorkspaceRow
from app.purge import purge

pytestmark = pytest.mark.integration

SECRET_WORDS = "zebra-quartz-umbrella"


def counts(engine):
    with engine.connect() as c:
        return tuple(
            c.scalar(select(func.count()).select_from(model))
            for model in (SessionRow, TurnRow, ReportRow, ExportEventRow, WorkspaceRow)
        )


def test_purge_deletes_old_sessions_and_everything_attached(api, seeded_engine, clock):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    approved = teacher.review(report["report_id"], decision="approve", levels=levels(report)).json()
    teacher.export(approved["report_id"])
    assert counts(seeded_engine) == (1, 1, 2, 1, 1)
    factory = sessionmaker(bind=seeded_engine)

    # Not old enough yet: nothing happens. A dry run later reports but changes nothing.
    assert purge(factory, older_than_days=7, now=clock() + timedelta(days=6)) == (0, 0)
    later = clock() + timedelta(days=8)
    assert purge(factory, older_than_days=7, now=later, dry_run=True) == (1, 1)
    assert counts(seeded_engine) == (1, 1, 2, 1, 1)

    assert purge(factory, older_than_days=7, now=later) == (1, 1)
    assert counts(seeded_engine) == (0, 0, 0, 0, 0)
    with seeded_engine.connect() as c:  # lessons are never purged
        assert c.scalar(text("SELECT count(*) FROM lesson_versions")) == 3


def test_purge_keeps_a_classroom_that_still_has_recent_sessions(api, seeded_engine, clock):
    teacher = Teacher(api)
    finished_report(teacher, GOOD_Q1)  # old session
    clock.advance(8 * 86400)
    teacher.start(learner="demo-new")  # recent session in the same classroom
    factory = sessionmaker(bind=seeded_engine)
    assert purge(factory, older_than_days=7, now=clock()) == (1, 0)
    assert counts(seeded_engine)[0] == 1 and counts(seeded_engine)[4] == 1


def test_logs_never_contain_what_the_learner_said(api, caplog):
    """Transcripts are learner data: they belong in the database, not in log files."""
    caplog.set_level(logging.DEBUG)
    teacher = Teacher(api)
    learner = teacher.start()
    learner.say(f"Plants make sugar from light and {SECRET_WORDS} in their leaves.")
    learner.say(f"What is {SECRET_WORDS}?")
    learner.finish()
    report = teacher.report(learner.id)
    teacher.review(report["report_id"], decision="reject", reason=f"mentions {SECRET_WORDS}")
    assert any("turn_timing" in record.getMessage() for record in caplog.records)  # logs exist
    for record in caplog.records:
        assert SECRET_WORDS not in record.getMessage()
        assert learner.token not in record.getMessage()
        assert teacher.token not in record.getMessage()
