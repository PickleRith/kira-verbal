"""Developer tool: print a session's evidence and suggested levels (teacher-only data).

    python -m app.inspect_session <session_id>

Reads the local database directly. It exists until the teacher dashboard (Day 5) and is
not exposed over HTTP, so it needs no authorization of its own.
"""

from __future__ import annotations

import sys
import uuid

from sqlalchemy import select

from app.config import get_settings
from app.db.models import EvidenceRow, SessionRow, TurnRow
from app.db.session import make_engine, make_session_factory
from app.domain.models import Lesson
from app.domain.scoring import EvidenceRecord, EvidenceStatus, summarize
from app.services.lessons import LessonStore


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    session_id = uuid.UUID(argv[0])
    engine = make_engine(get_settings().database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            session = db.get(SessionRow, session_id)
            if session is None:
                print("no such session", file=sys.stderr)
                return 1
            lesson: Lesson | None = LessonStore(factory).get(
                session.lesson_id, session.lesson_version
            )
            assert lesson is not None
            rows = db.execute(
                select(EvidenceRow, TurnRow.sequence, TurnRow.transcript)
                .join(TurnRow, TurnRow.id == EvidenceRow.turn_id)
                .where(EvidenceRow.session_id == session_id)
                .order_by(TurnRow.sequence, EvidenceRow.criterion_id)
            ).all()
    finally:
        engine.dispose()

    print(f"{lesson.title} v{lesson.version} - status {session.status}\n")
    for evidence, sequence, transcript in rows:
        level = "-" if evidence.proposed_level is None else evidence.proposed_level
        kind = "assisted" if evidence.assisted else "independent"
        print(
            f"turn {sequence} [{evidence.validation_status:9}] {evidence.criterion_id} "
            f"level={level} {kind}"
        )
        print(f"   answer: {transcript!r}")
        print(f"   quote:  {evidence.evidence_quote!r}")
        if evidence.misconception_tag:
            print(f"   misconception: {evidence.misconception_tag}")
        if evidence.rejection_reason:
            print(f"   REJECTED: {evidence.rejection_reason}")
        print(f"   reason: {evidence.reason}  ({evidence.evaluator_version})")

    summary = summarize(
        lesson,
        [
            EvidenceRecord(
                criterion_id=e.criterion_id,
                level=e.proposed_level,
                status=EvidenceStatus(e.validation_status),
                assisted=e.assisted,
                misconception_tag=e.misconception_tag,
                sequence=sequence,
            )
            for e, sequence, _ in rows
        ],
    )
    print("\nSuggested levels (latest accepted independent evidence; '?' = unknown):")
    for c in summary.criteria:
        level = "?" if c.suggested_level is None else c.suggested_level
        flags = ", ".join(
            f
            for f in (
                "CONFLICT" if c.conflicting else "",
                f"{c.rejected} rejected" if c.rejected else "",
            )
            if f
        )
        print(
            f"  {c.criterion_id:20} {level}  independent={list(c.independent_levels)} "
            f"assisted={list(c.assisted_levels)} tags={list(c.misconception_tags)} {flags}"
        )
    print(
        f"\nCoverage: {summary.criteria_with_evidence} of {summary.criteria_total} criteria"
        f"{' - needs review' if summary.needs_review else ''}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
