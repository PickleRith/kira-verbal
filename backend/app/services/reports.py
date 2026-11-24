"""Teacher workspaces, report construction, review and export.

Report lifecycle (PROJECT_PLAN.md §5): pending -> ready_for_review -> approved | rejected.

* pending: the session is still running. Nothing is stored; GET shows a live preview.
* ready_for_review: revision 1, created (once) the first time a teacher opens or lists a
  finished session. It holds the system's suggestions. Evidence can't change after the
  session ends, so creating it lazily gives the same result as creating it at the end.
* Each review creates a NEW revision (approved or rejected) and a review row that links
  the revision the teacher saw to the one they produced. Nothing is edited in place;
  migration 0005 makes these tables append-only.
* Only the latest revision can be reviewed or exported. Acting on an older one is a 409
  stale_revision, so two teachers (or two tabs) can't silently overwrite each other.
  The session row lock serializes the check, and unique(session_id, revision) backs it up.
* Export: only the latest approved revision, at most once (unique report_id and a
  deterministic idempotency key). A repeat returns the stored event.

Authorization: a teacher token opens only its own workspace. Sessions outside it, and
anonymous home-page sessions, answer 404 exactly like an unknown id.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    EvidenceRow,
    ExportEventRow,
    ReportRow,
    ReviewRow,
    SessionRow,
    TurnRow,
    WorkspaceRow,
)
from app.domain.models import Lesson
from app.domain.scoring import EvidenceRecord, EvidenceStatus, ScoreSummary, summarize
from app.domain.state import SessionStatus, is_terminal
from app.providers import kira_mock
from app.schemas.reports import (
    Coverage,
    CriterionReport,
    EvidenceItem,
    ExportEntry,
    ExportResponse,
    MisconceptionRef,
    ReportView,
    ReviewEntry,
    ReviewRequest,
    RevisionEntry,
    ScoreView,
    TeacherSessionItem,
    TranscriptTurn,
)
from app.schemas.sessions import LessonRef, StudentSessionView
from app.services.accounts import USER_TOKEN_PREFIX, AccountService
from app.services.assessment import AssessmentService
from app.services.errors import (
    InvalidReviewError,
    LessonNotFoundError,
    NoClassError,
    NotSignedInError,
    ReportNotApprovedError,
    ReportNotFoundError,
    SessionNotFoundError,
    StaleRevisionError,
    TeacherNotFoundError,
    WrongRoleError,
)

TEACHER_TOKEN_PREFIX = "kvt_"
SYSTEM_AUTHOR = "system"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ReportService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        assessment: AssessmentService,
        kira: kira_mock.MockKiraClient | None = None,
        clock: Callable[[], datetime] | None = None,
        accounts: AccountService | None = None,
    ) -> None:
        self._db = session_factory
        self._assessment = assessment
        self._accounts = accounts
        self.kira = kira or kira_mock.MockKiraClient()
        self._clock = clock

    @property
    def clock(self) -> Callable[[], datetime]:
        # Share the assessment clock so tests that move time move both.
        return self._clock or self._assessment.clock

    # --- workspace --------------------------------------------------------------------

    def create_workspace(self) -> tuple[uuid.UUID, str]:
        token = TEACHER_TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = WorkspaceRow(
            id=uuid.uuid4(), teacher_token_sha256=_sha256(token), created_at=self.clock()
        )
        with self._db.begin() as db:
            db.add(row)
        return row.id, token

    def workspace(self, token: str) -> WorkspaceRow:
        """The class a teacher route acts on: a signed-in teacher's class, or a demo
        classroom opened with its teacher token."""
        if self._accounts is not None and token.startswith(USER_TOKEN_PREFIX):
            try:
                return self._accounts.teacher_workspace(token)
            except (NotSignedInError, WrongRoleError, NoClassError) as exc:
                raise TeacherNotFoundError(str(exc)) from None
        if not token.startswith(TEACHER_TOKEN_PREFIX):
            raise TeacherNotFoundError("teacher token required")
        digest = _sha256(token)
        with self._db.begin() as db:
            row = db.scalar(select(WorkspaceRow).where(WorkspaceRow.teacher_token_sha256 == digest))
            if row is None:  # only the hash is stored; lookup is by exact hash
                raise TeacherNotFoundError("unknown teacher token")
            db.expunge(row)
            return row

    # --- sessions ---------------------------------------------------------------------

    def create_session(
        self, token: str, lesson_id: str, synthetic_learner_id: str
    ) -> tuple[StudentSessionView, str]:
        workspace = self.workspace(token)
        return self._assessment.create_session(
            lesson_id, None, synthetic_learner_id, workspace_id=workspace.id
        )

    def list_sessions(self, token: str) -> list[TeacherSessionItem]:
        workspace = self.workspace(token)
        with self._db.begin() as db:
            ids = list(
                db.scalars(
                    select(SessionRow.id)
                    .where(SessionRow.workspace_id == workspace.id)
                    .order_by(SessionRow.created_at.desc())
                )
            )
        for session_id in ids:  # apply deadlines so abandoned sessions show as finished
            self._assessment.apply_timers(session_id)
        items: list[TeacherSessionItem] = []
        with self._db.begin() as db:
            rows = [db.get(SessionRow, session_id) for session_id in ids]
            names = self._names({r.learner_user_id for r in rows if r and r.learner_user_id})
            for row in rows:
                assert row is not None
                session_id = row.id
                latest = _latest_report(db, session_id)
                turns = _committed_turns(db, session_id)
                items.append(
                    TeacherSessionItem(
                        session_id=row.id,
                        lesson=self._lesson_ref(row),
                        synthetic_learner_id=row.synthetic_learner_id,
                        learner_name=names.get(row.learner_user_id),  # type: ignore[arg-type]
                        session_status=row.status,
                        finish_reason=row.finish_reason,  # type: ignore[arg-type]
                        created_at=row.created_at,
                        report_status=_report_status(row, latest),  # type: ignore[arg-type]
                        report_revision=latest.revision if latest else None,
                        answer_turns=sum(t.signal != "conversation" for t in turns),
                        wellbeing_flags=sum(t.intent == "wellbeing_concern" for t in turns),
                        score=self._board_score(db, row, latest, turns),
                    )
                )
        return items

    # --- report -----------------------------------------------------------------------

    def get_report(self, token: str, session_id: uuid.UUID) -> ReportView:
        workspace = self.workspace(token)
        self._assessment.apply_timers(session_id)
        with self._db.begin() as db:
            row = self._owned_session(db, workspace.id, session_id)
            terminal = is_terminal(SessionStatus(row.status))
        if terminal:
            self._ensure_first_revision(session_id)
        with self._db.begin() as db:
            row = self._owned_session(db, workspace.id, session_id)
            return self._view(db, row, self._lesson(row))

    def review(self, token: str, report_id: uuid.UUID, body: ReviewRequest) -> ReportView:
        workspace = self.workspace(token)
        try:
            with self._db.begin() as db:
                report, row = self._owned_report(db, workspace.id, report_id, lock=True)
                lesson = self._lesson(row)
                latest = _latest_report(db, row.id)
                assert latest is not None
                if latest.id != report.id:
                    raise StaleRevisionError(
                        f"revision {report.revision} is not the latest "
                        f"(latest is {latest.revision}); refetch the report"
                    )
                levels, reason = _validate_review(lesson, report, body)
                now = self.clock()
                status = "approved" if body.decision == "approve" else "rejected"
                criteria = [
                    {**c, "level": levels[c["criterion_id"]]} if levels is not None else dict(c)
                    for c in report.criteria
                ]
                new = ReportRow(
                    id=uuid.uuid4(),
                    session_id=row.id,
                    revision=report.revision + 1,
                    status=status,
                    criteria=criteria,
                    summary=report.summary,
                    created_by=body.reviewer_id,
                    created_at=now,
                )
                db.add(new)
                db.flush()
                db.add(
                    ReviewRow(
                        id=uuid.uuid4(),
                        report_id=report.id,
                        result_report_id=new.id,
                        reviewer_id=body.reviewer_id,
                        decision=body.decision,
                        approved_levels=levels,
                        reason=reason,
                        created_at=now,
                    )
                )
                session_id = row.id
        except IntegrityError:
            # Another review created the next revision first (the lock makes this rare).
            raise StaleRevisionError("another review was saved first; refetch") from None
        with self._db.begin() as db:
            row = self._owned_session(db, workspace.id, session_id)
            return self._view(db, row, lesson)

    def export(self, token: str, report_id: uuid.UUID) -> ExportResponse:
        workspace = self.workspace(token)
        with self._db.begin() as db:
            report, row = self._owned_report(db, workspace.id, report_id, lock=True)
            existing = db.scalar(
                select(ExportEventRow).where(ExportEventRow.report_id == report.id)
            )
            if existing is not None:  # same revision exported before: replay, no new event
                event, replayed = existing, True
            else:
                latest = _latest_report(db, row.id)
                assert latest is not None
                if latest.id != report.id:
                    raise StaleRevisionError(
                        f"revision {report.revision} is not the latest; refetch the report"
                    )
                if report.status != "approved":
                    raise ReportNotApprovedError("only an approved report can be exported")
                payload = kira_mock.build_payload(
                    self._export_input(db, row, self._lesson(row), report)
                )
                event = ExportEventRow(
                    id=uuid.uuid4(),
                    report_id=report.id,
                    schema_version=kira_mock.SCHEMA_VERSION,
                    idempotency_key=payload["idempotency_key"],
                    payload=payload,
                    created_at=self.clock(),
                )
                db.add(event)
                replayed = False
            response = ExportResponse(
                **_export_entry(event, report.revision).model_dump(), replayed=replayed
            )
        # Deliver after the event is committed (outbox order). The key is deterministic, so
        # re-delivering a replay can never apply the update twice downstream.
        self.kira.deliver(response.payload)
        return response

    # --- internals --------------------------------------------------------------------

    def _ensure_first_revision(self, session_id: uuid.UUID) -> None:
        try:
            with self._db.begin() as db:
                if _latest_report(db, session_id) is not None:
                    return
                row = db.get(SessionRow, session_id)
                assert row is not None
                lesson = self._lesson(row)
                evidence = _evidence(db, session_id)
                turns = _committed_turns(db, session_id)
                summary = _score(lesson, evidence, turns)
                db.add(
                    ReportRow(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        revision=1,
                        status="ready_for_review",
                        criteria=_criteria_json(summary, evidence, turns),
                        summary=_summary_json(row, summary, turns, evidence),
                        created_by=SYSTEM_AUTHOR,
                        created_at=self.clock(),
                    )
                )
        except IntegrityError:
            pass  # a concurrent request created revision 1; theirs is identical

    def _owned_session(
        self, db: Session, workspace_id: uuid.UUID, session_id: uuid.UUID, *, lock: bool = False
    ) -> SessionRow:
        row = db.get(SessionRow, session_id, with_for_update=lock, populate_existing=lock)
        if row is None or row.workspace_id != workspace_id:
            raise SessionNotFoundError("session not found")
        return row

    def _owned_report(
        self, db: Session, workspace_id: uuid.UUID, report_id: uuid.UUID, *, lock: bool
    ) -> tuple[ReportRow, SessionRow]:
        report = db.get(ReportRow, report_id)
        if report is None:
            raise ReportNotFoundError("report not found")
        try:
            row = self._owned_session(db, workspace_id, report.session_id, lock=lock)
        except SessionNotFoundError:
            raise ReportNotFoundError("report not found") from None
        return report, row

    def _board_score(
        self, db: Session, row: SessionRow, latest: ReportRow | None, turns: list[TurnRow]
    ) -> ScoreView | None:
        """The latest revision's score; for a finished check-in nobody has opened yet, the
        suggested score (what revision 1 will hold). None while the student is answering."""
        if latest is not None:
            return _score_view(latest.criteria, "level")
        if not is_terminal(SessionStatus(row.status)):
            return None
        summary = _score(self._lesson(row), _evidence(db, row.id), turns)
        return ScoreView.from_levels({c.criterion_id: c.suggested_level for c in summary.criteria})

    def _names(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        return self._accounts.display_names(user_ids) if self._accounts else {}

    def _lesson(self, row: SessionRow) -> Lesson:
        lesson = self._assessment.lessons.get(row.lesson_id, row.lesson_version)
        if lesson is None:
            raise LessonNotFoundError(f"{row.lesson_id} v{row.lesson_version} missing")
        return lesson

    def _lesson_ref(self, row: SessionRow) -> LessonRef:
        lesson = self._lesson(row)
        return LessonRef(id=lesson.id, version=lesson.version, title=lesson.title)

    def _view(self, db: Session, row: SessionRow, lesson: Lesson) -> ReportView:
        evidence = _evidence(db, row.id)
        turns = _committed_turns(db, row.id)
        sequences = {t.id: t.sequence for t in turns}
        latest = _latest_report(db, row.id)
        if latest is None:  # pending: live preview, not stored
            summary = _score(lesson, evidence, turns)
            criteria_json = _criteria_json(summary, evidence, turns)
            summary_json = _summary_json(row, summary, turns, evidence)
        else:
            criteria_json, summary_json = latest.criteria, latest.summary

        by_criterion: dict[str, list[EvidenceItem]] = {}
        for item in evidence:
            by_criterion.setdefault(item.criterion_id, []).append(
                _evidence_item(item, sequences[item.turn_id])
            )
        criteria = []
        for c in criteria_json:
            criterion = next(x for x in lesson.criteria if x.id == c["criterion_id"])
            objective = next(o for o in lesson.objectives if o.id == criterion.objective)
            criteria.append(
                CriterionReport(
                    criterion_id=criterion.id,
                    objective=objective.id,
                    objective_description=objective.description,
                    level_descriptors=dict(criterion.levels),
                    suggested_level=c["suggested_level"],
                    level=c["level"],
                    independent_levels=c["independent_levels"],
                    assisted_levels=c["assisted_levels"],
                    misconceptions=[
                        MisconceptionRef(tag=tag, description=m.description)
                        for tag in c["misconception_tags"]
                        if (m := lesson.misconception(tag)) is not None
                    ],
                    conflicting=c["conflicting"],
                    abstentions=c["abstentions"],
                    rejected=c["rejected"],
                    evidence=by_criterion.get(criterion.id, []),
                )
            )

        revisions = list(
            db.scalars(
                select(ReportRow).where(ReportRow.session_id == row.id).order_by(ReportRow.revision)
            )
        )
        revision_of = {r.id: r.revision for r in revisions}
        reviews = list(
            db.scalars(
                select(ReviewRow)
                .where(ReviewRow.report_id.in_(revision_of))
                .order_by(ReviewRow.created_at, ReviewRow.id)
            )
        )
        exports = list(
            db.scalars(
                select(ExportEventRow)
                .where(ExportEventRow.report_id.in_(revision_of))
                .order_by(ExportEventRow.created_at)
            )
        )
        return ReportView(
            session_id=row.id,
            report_id=latest.id if latest else None,
            revision=latest.revision if latest else None,
            status=_report_status(row, latest),  # type: ignore[arg-type]
            lesson=LessonRef(id=lesson.id, version=lesson.version, title=lesson.title),
            synthetic_learner_id=row.synthetic_learner_id,
            learner_name=(
                self._names({row.learner_user_id}).get(row.learner_user_id)
                if row.learner_user_id
                else None
            ),
            session_status=row.status,
            finish_reason=row.finish_reason,  # type: ignore[arg-type]
            session_created_at=row.created_at,
            coverage=Coverage(**summary_json["coverage"]),
            needs_review=summary_json["needs_review"],
            wellbeing_turns=summary_json["wellbeing_turns"],
            hints_used=summary_json["hints_used"],
            side_turns=summary_json["side_turns"],
            criteria=criteria,
            score=_score_view(criteria_json, "level"),  # type: ignore[arg-type]
            suggested_score=_score_view(criteria_json, "suggested_level"),  # type: ignore[arg-type]
            transcript=[
                TranscriptTurn(
                    sequence=t.sequence,
                    question_id=t.question_id,
                    question_text=lesson.question(t.question_id).prompt,
                    answer=t.transcript,
                    modality=t.modality,  # type: ignore[arg-type]
                    assisted=t.assisted,
                    intent=t.intent,
                    signal=t.signal,
                    reply=((t.response or {}).get("prompt") or {}).get("lead_in"),
                )
                for t in turns
            ],
            revisions=[
                RevisionEntry(
                    report_id=r.id,
                    revision=r.revision,
                    status=r.status,  # type: ignore[arg-type]
                    created_by=r.created_by,
                    created_at=r.created_at,
                )
                for r in revisions
            ],
            reviews=[
                ReviewEntry(
                    id=v.id,
                    from_revision=revision_of[v.report_id],
                    to_revision=revision_of[v.result_report_id],
                    reviewer_id=v.reviewer_id,
                    decision=v.decision,  # type: ignore[arg-type]
                    approved_levels=v.approved_levels,
                    reason=v.reason,
                    created_at=v.created_at,
                )
                for v in reviews
            ],
            exports=[_export_entry(e, revision_of[e.report_id]) for e in exports],
        )

    def _export_input(
        self, db: Session, row: SessionRow, lesson: Lesson, report: ReportRow
    ) -> kira_mock.ExportInput:
        review = db.scalar(select(ReviewRow).where(ReviewRow.result_report_id == report.id))
        assert review is not None  # an approved revision is always created by a review
        evidence = {str(e.id): e for e in _evidence(db, row.id)}
        turns = _committed_turns(db, row.id)
        sequences = {t.id: t.sequence for t in turns}
        criteria = []
        for c in report.criteria:
            items = [evidence[i] for i in c["evidence_ids"] if i in evidence]
            criteria.append(
                kira_mock.ExportCriterion(
                    criterion_id=c["criterion_id"],
                    objective_id=c["objective"],
                    level=c["level"],
                    suggested_level=c["suggested_level"],
                    misconception_tags=tuple(c["misconception_tags"]),
                    evidence=tuple(
                        kira_mock.ExportEvidence(
                            turn_sequence=sequences[e.turn_id],
                            quote=e.evidence_quote,
                            assisted=e.assisted,
                            misconception_tag=e.misconception_tag,
                        )
                        for e in items
                    ),
                )
            )
        return kira_mock.ExportInput(
            session_id=row.id,
            synthetic_learner_id=row.synthetic_learner_id,
            lesson_id=lesson.id,
            lesson_version=lesson.version,
            lesson_title=lesson.title,
            session_status=row.status,
            finish_reason=row.finish_reason,
            session_started_at=row.created_at,
            modalities=tuple(sorted({t.modality for t in turns})),
            report_revision=report.revision,
            reviewer_id=review.reviewer_id,
            reviewed_at=review.created_at,
            review_reason=review.reason,
            criteria=tuple(criteria),
            evaluator_versions=tuple(report.summary.get("evaluator_versions", [])),
        )


# --- pure helpers -----------------------------------------------------------------------


def _latest_report(db: Session, session_id: uuid.UUID) -> ReportRow | None:
    return db.scalar(
        select(ReportRow)
        .where(ReportRow.session_id == session_id)
        .order_by(ReportRow.revision.desc())
        .limit(1)
    )


def _committed_turns(db: Session, session_id: uuid.UUID) -> list[TurnRow]:
    return list(
        db.scalars(
            select(TurnRow)
            .where(TurnRow.session_id == session_id, TurnRow.status == "committed")
            .order_by(TurnRow.sequence)
        )
    )


def _evidence(db: Session, session_id: uuid.UUID) -> list[EvidenceRow]:
    return list(
        db.scalars(
            select(EvidenceRow)
            .join(TurnRow, TurnRow.id == EvidenceRow.turn_id)
            .where(EvidenceRow.session_id == session_id, TurnRow.status == "committed")
            .order_by(TurnRow.sequence, EvidenceRow.criterion_id, EvidenceRow.id)
        )
    )


def _score_view(criteria: list[dict[str, Any]] | None, key: str) -> ScoreView | None:
    if criteria is None:
        return None
    return ScoreView.from_levels({c["criterion_id"]: c[key] for c in criteria})


def _report_status(row: SessionRow, latest: ReportRow | None) -> str:
    if latest is not None:
        return latest.status
    return "ready_for_review" if is_terminal(SessionStatus(row.status)) else "pending"


def _score(lesson: Lesson, evidence: list[EvidenceRow], turns: list[TurnRow]) -> ScoreSummary:
    sequences = {t.id: t.sequence for t in turns}
    return summarize(
        lesson,
        [
            EvidenceRecord(
                criterion_id=e.criterion_id,
                level=e.proposed_level,
                status=EvidenceStatus(e.validation_status),
                assisted=e.assisted,
                misconception_tag=e.misconception_tag,
                sequence=sequences[e.turn_id],
            )
            for e in evidence
        ],
    )


def _criteria_json(
    summary: ScoreSummary, evidence: list[EvidenceRow], turns: list[TurnRow]
) -> list[dict[str, Any]]:
    return [
        {
            "criterion_id": c.criterion_id,
            "objective": c.objective,
            "suggested_level": c.suggested_level,
            "level": c.suggested_level,  # revision 1: the suggestion, until a teacher decides
            "independent_levels": list(c.independent_levels),
            "assisted_levels": list(c.assisted_levels),
            "misconception_tags": list(c.misconception_tags),
            "conflicting": c.conflicting,
            "abstentions": c.abstentions,
            "rejected": c.rejected,
            "evidence_ids": [
                str(e.id)
                for e in evidence
                if e.criterion_id == c.criterion_id and e.validation_status == "accepted"
            ],
        }
        for c in summary.criteria
    ]


def _summary_json(
    row: SessionRow, summary: ScoreSummary, turns: list[TurnRow], evidence: list[EvidenceRow]
) -> dict[str, Any]:
    return {
        "coverage": {
            "with_evidence": summary.criteria_with_evidence,
            "total": summary.criteria_total,
        },
        "needs_review": summary.needs_review,
        "session_status": row.status,
        "finish_reason": row.finish_reason,
        "wellbeing_turns": [t.sequence for t in turns if t.intent == "wellbeing_concern"],
        "hints_used": sum(t.signal == "help_requested" for t in turns),
        "side_turns": sum(t.signal == "conversation" for t in turns),
        "evaluator_versions": sorted({e.evaluator_version for e in evidence}),
    }


def _validate_review(
    lesson: Lesson, report: ReportRow, body: ReviewRequest
) -> tuple[dict[str, int | None] | None, str]:
    reason = body.reason.strip()
    if body.decision == "reject":
        if not reason:
            raise InvalidReviewError("a reason is required to reject a report")
        return None, reason
    if body.levels is None:
        raise InvalidReviewError("levels are required to approve (use null for unknown)")
    expected = {c.id for c in lesson.criteria}
    if set(body.levels) != expected:
        missing, extra = sorted(expected - set(body.levels)), sorted(set(body.levels) - expected)
        raise InvalidReviewError(
            f"levels must cover exactly the criteria; missing={missing} extra={extra}"
        )
    current = {c["criterion_id"]: c["level"] for c in report.criteria}
    changed = sorted(k for k, v in body.levels.items() if v != current[k])
    if changed and not reason:
        raise InvalidReviewError(f"a reason is required when changing levels: {changed}")
    return dict(body.levels), reason


def _evidence_item(e: EvidenceRow, sequence: int) -> EvidenceItem:
    return EvidenceItem(
        id=e.id,
        turn_sequence=sequence,
        criterion_id=e.criterion_id,
        quote=e.evidence_quote,
        proposed_level=e.proposed_level,
        status=e.validation_status,  # type: ignore[arg-type]
        assisted=e.assisted,
        misconception_tag=e.misconception_tag,
        reason=e.reason,
        rejection_reason=e.rejection_reason,
        evaluator_version=e.evaluator_version,
    )


def _export_entry(e: ExportEventRow, revision: int) -> ExportEntry:
    return ExportEntry(
        id=e.id,
        report_id=e.report_id,
        report_revision=revision,
        schema_version=e.schema_version,
        idempotency_key=e.idempotency_key,
        payload=e.payload,
        created_at=e.created_at,
    )
