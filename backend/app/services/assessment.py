"""Assessment orchestrator: creates sessions and runs one learner turn end to end.

Transaction layout of `submit_turn` (PROJECT_PLAN.md §5 "Turn algorithm"):

  T0 refresh  apply timers: recover an expired processing lease; mark an idle session
              past its deadline incomplete.
  T1 claim    session row locked (SELECT ... FOR UPDATE), short:
              - idempotency lookup by (session, client_turn_id) FIRST, so a retry of a
                committed turn replays its stored response even though the version moved on
              - check status, expected_state_version, deadline, question_id
              - insert turn(processing); session -> evaluating; state_version += 1; set lease
  --          evaluator call: NO transaction or lock held; bounded by a timeout
  T2 commit   session and turn locked again, short:
              - verify the claim still stands (turn processing, version unchanged)
              - policy picks the next action from committed history + this turn
              - turn -> committed with cached response; session -> awaiting_answer or
                completed; state_version += 1

Failure paths:
  * evaluator raises or times out: the turn is marked failed and the session returns to
    awaiting_answer (recoverable_error). The client retries with the same client_turn_id.
  * the process dies between T1 and T2: the lease expires and the next request for the
    session (T0) marks the turn failed. If the original request resumes, T2 sees that its
    claim was lost and aborts without committing.

Correctness rests on the row lock, state_version and the partial unique indexes, not on
Redis. The evaluator may run twice for one turn after a crash; a turn can never commit twice.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import EvidenceRow, SessionRow, TurnRow
from app.domain.models import Lesson
from app.domain.policy import (
    Action,
    AskQuestion,
    Budget,
    Finish,
    GiveHint,
    Signal,
    TurnRecord,
    next_action,
)
from app.domain.state import SessionEvent, SessionStatus, is_terminal, transition
from app.providers.llm import EvaluationRequest, Evaluator, EvaluatorOutput
from app.repositories import sessions as repo
from app.schemas.sessions import (
    LessonRef,
    Prompt,
    StudentSessionView,
    TranscriptEntry,
    TurnInput,
    TurnResponse,
)
from app.services.errors import (
    ClaimLostError,
    EvaluationUnavailableError,
    IdempotencyMismatchError,
    LessonNotFoundError,
    QuestionMismatchError,
    SessionClosedError,
    SessionExpiredError,
    SessionNotFoundError,
    StaleStateVersionError,
    TurnInProgressError,
)
from app.services.evaluator import validate_output
from app.services.lessons import LessonStore

logger = logging.getLogger(__name__)

CLARIFY_LEAD_IN = "Could you say a bit more about that?"
HINT_LEAD_IN = "Here's a hint:"


def utcnow() -> datetime:
    return datetime.now(UTC)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_fingerprint(turn: TurnInput) -> str:
    """Everything except client_turn_id: same id + different payload is a conflict."""
    payload = turn.model_dump(exclude={"client_turn_id"})
    return hash_secret(json.dumps(payload, sort_keys=True, separators=(",", ":")))


@dataclass(frozen=True)
class AssessmentConfig:
    max_turns: int = 5
    session_max_seconds: int = 300
    deadline_grace_seconds: int = 60
    processing_lease_seconds: int = 60
    evaluator_timeout_seconds: float = 45.0

    def __post_init__(self) -> None:
        # If the lease could expire while a healthy evaluator call is still running, another
        # request would "recover" a turn that is not stuck, and every slow answer would fail.
        if self.processing_lease_seconds <= self.evaluator_timeout_seconds:
            raise ValueError("processing_lease_seconds must exceed evaluator_timeout_seconds")


class AssessmentService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        lessons: LessonStore,
        evaluator: Evaluator,
        executor: ThreadPoolExecutor,
        config: AssessmentConfig | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._db = session_factory
        self.lessons = lessons
        self.evaluator = evaluator
        self._executor = executor
        self.config = config or AssessmentConfig()
        self.clock = clock  # replaceable in tests

    # --- public operations ----------------------------------------------------------

    def create_session(
        self, lesson_id: str, lesson_version: int | None, synthetic_learner_id: str
    ) -> tuple[StudentSessionView, str]:
        lesson = (
            self.lessons.get(lesson_id, lesson_version)
            if lesson_version is not None
            else self.lessons.latest(lesson_id)
        )
        if lesson is None:
            raise LessonNotFoundError(f"lesson {lesson_id!r} is not published")

        first = next_action(lesson, [], elapsed_seconds=0.0, budget=self._budget())
        if not isinstance(first, AskQuestion):  # validated lessons always have an open question
            raise RuntimeError(f"policy returned {first!r} for an empty session")

        now = self.clock()
        token = secrets.token_urlsafe(32)
        row = SessionRow(
            id=uuid.uuid4(),
            synthetic_learner_id=synthetic_learner_id,
            lesson_id=lesson.id,
            lesson_version=lesson.version,
            access_token_sha256=hash_secret(token),
            status=transition(SessionStatus.CREATED, SessionEvent.START).value,
            state_version=1,
            current_question_id=first.question_id,
            current_purpose=first.purpose,
            created_at=now,
            updated_at=now,
            deadline_at=now
            + timedelta(
                seconds=self.config.session_max_seconds + self.config.deadline_grace_seconds
            ),
        )
        with self._db.begin() as db:
            db.add(row)
            db.flush()
            view = self._view(db, row, lesson)
        return view, token

    def get_session(self, session_id: uuid.UUID, token: str) -> StudentSessionView:
        self._refresh(session_id, token)
        with self._db.begin() as db:
            row = self._load(db, session_id, token, lock=False)
            return self._view(db, row, self._lesson_for(row))

    def finish(
        self, session_id: uuid.UUID, token: str, expected_state_version: int
    ) -> StudentSessionView:
        """Learner exits early -> incomplete. Idempotent once the session is terminal."""
        self._refresh(session_id, token)
        with self._db.begin() as db:
            row = self._load(db, session_id, token, lock=True)
            status = SessionStatus(row.status)
            if not is_terminal(status):
                if row.state_version != expected_state_version:
                    raise StaleStateVersionError(
                        "session changed; refetch", state_version=row.state_version
                    )
                if status is SessionStatus.EVALUATING:
                    raise TurnInProgressError(
                        "an answer is being processed", state_version=row.state_version
                    )
                self._close(row, SessionEvent.TIMEOUT_OR_EXIT, "learner_exit")
            return self._view(db, row, self._lesson_for(row))

    def submit_turn(self, session_id: uuid.UUID, token: str, turn_input: TurnInput) -> TurnResponse:
        fingerprint = request_fingerprint(turn_input)
        self._refresh(session_id, token)

        # T1: claim
        with self._db.begin() as db:
            row = self._load(db, session_id, token, lock=True)
            existing = repo.find_live_turn(db, session_id, turn_input.client_turn_id)
            if existing is not None:
                if not hmac.compare_digest(existing.request_sha256, fingerprint):
                    raise IdempotencyMismatchError(
                        "client_turn_id was already used with a different payload",
                        state_version=row.state_version,
                    )
                if existing.status == "committed" and existing.response is not None:
                    return TurnResponse.model_validate(existing.response)
                raise TurnInProgressError(
                    "this turn is still being processed", state_version=row.state_version
                )

            status = SessionStatus(row.status)
            if is_terminal(status):
                raise SessionClosedError(
                    f"session is {status.value}", state_version=row.state_version
                )
            if row.state_version != turn_input.expected_state_version or (
                status is not SessionStatus.AWAITING_ANSWER
            ):
                raise StaleStateVersionError(
                    "session changed; refetch", state_version=row.state_version
                )
            now = self.clock()
            if now > row.deadline_at:
                raise SessionExpiredError("session time is up", state_version=row.state_version)
            if turn_input.question_id != row.current_question_id:
                raise QuestionMismatchError(
                    f"current question is {row.current_question_id!r}",
                    state_version=row.state_version,
                )

            assisted = row.current_purpose == "hint" or repo.question_was_assisted(
                db, session_id, turn_input.question_id
            )
            turn = TurnRow(
                id=uuid.uuid4(),
                session_id=session_id,
                client_turn_id=turn_input.client_turn_id,
                sequence=repo.next_sequence(db, session_id),
                question_id=turn_input.question_id,
                transcript=turn_input.transcript,
                modality=turn_input.modality,
                assisted=assisted,
                request_sha256=fingerprint,
                status="processing",
                created_at=now,
            )
            db.add(turn)
            row.status = transition(status, SessionEvent.TURN_FINALIZED).value
            row.state_version += 1
            row.lease_expires_at = now + timedelta(seconds=self.config.processing_lease_seconds)
            row.updated_at = now
            claimed_version = row.state_version
            turn_id = turn.id
            lesson = self._lesson_for(row)

        # Evaluate with no transaction open.
        question = lesson.question(turn_input.question_id)
        try:
            result = self._evaluate(
                EvaluationRequest(lesson, question, turn_input.transcript, assisted)
            )
        except Exception:
            logger.warning("evaluation failed for session %s", session_id, exc_info=True)
            version = self._release_claim(session_id, turn_id, claimed_version)
            raise EvaluationUnavailableError(
                "could not process the answer; please retry", state_version=version
            ) from None
        # Validation is deterministic and checks quotes against the stored transcript, so a
        # fabricated quote or an undeclared tag can never reach the policy or the scores.
        assessment = validate_output(lesson, question, turn_input.transcript, result)
        signal, tag = assessment.signal, assessment.misconception_tag

        # T2: commit
        with self._db.begin() as db:
            row = repo.get_session(db, session_id, lock=True)
            turn = repo.get_turn_for_update(db, turn_id)
            assert row is not None and turn is not None  # rows are never deleted mid-session
            if turn.status != "processing" or row.state_version != claimed_version:
                raise ClaimLostError(
                    "this answer's processing expired; please retry",
                    state_version=row.state_version,
                )
            history = [
                TurnRecord(t.question_id, Signal(t.signal), t.misconception_tag)
                for t in repo.committed_turns(db, session_id)
                if t.signal is not None
            ]
            history.append(TurnRecord(turn.question_id, signal, tag))
            now = self.clock()
            action = next_action(
                lesson,
                history,
                elapsed_seconds=max(0.0, (now - row.created_at).total_seconds()),
                budget=self._budget(),
            )

            turn.signal = signal.value
            turn.misconception_tag = tag
            turn.evaluator_version = result.evaluator_version
            turn.status = "committed"
            turn.committed_at = now
            for item in assessment.evidence:  # same transaction as the turn: exactly once
                db.add(
                    EvidenceRow(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        turn_id=turn.id,
                        criterion_id=item.criterion_id,
                        objective=item.objective,
                        proposed_level=item.proposed_level,
                        evidence_quote=item.evidence_quote,
                        misconception_tag=item.misconception_tag,
                        reason=item.reason,
                        assisted=turn.assisted,
                        validation_status=item.status.value,
                        rejection_reason=item.rejection_reason,
                        evaluator_version=result.evaluator_version,
                        model=result.model,
                        created_at=now,
                    )
                )
            self._apply_action(row, action)
            row.state_version += 1
            row.lease_expires_at = None
            row.updated_at = now
            response = TurnResponse(
                state_version=row.state_version,
                status=SessionStatus(row.status),
                prompt=self._prompt(row, lesson),
                finish_reason=row.finish_reason,  # type: ignore[arg-type]
            )
            turn.response = response.model_dump(mode="json")
        return response

    # --- internals ------------------------------------------------------------------

    def _budget(self) -> Budget:
        return Budget(
            max_turns=self.config.max_turns, max_seconds=float(self.config.session_max_seconds)
        )

    def _load(self, db: Session, session_id: uuid.UUID, token: str, *, lock: bool) -> SessionRow:
        row = repo.get_session(db, session_id, lock=lock)
        if row is None or not hmac.compare_digest(row.access_token_sha256, hash_secret(token)):
            raise SessionNotFoundError("session not found")
        return row

    def _lesson_for(self, row: SessionRow) -> Lesson:
        lesson = self.lessons.get(row.lesson_id, row.lesson_version)
        if lesson is None:  # impossible while the foreign key holds
            raise LessonNotFoundError(f"{row.lesson_id} v{row.lesson_version} missing")
        return lesson

    def _refresh(self, session_id: uuid.UUID, token: str) -> None:
        """T0: apply lease expiry and deadline in their own committed transaction."""
        with self._db.begin() as db:
            row = self._load(db, session_id, token, lock=True)
            now = self.clock()
            status = SessionStatus(row.status)
            if (
                status is SessionStatus.EVALUATING
                and row.lease_expires_at is not None
                and row.lease_expires_at <= now
            ):
                for stuck in repo.processing_turns(db, session_id):
                    stuck.status = "failed"
                logger.warning("recovered expired processing lease for session %s", session_id)
                row.status = transition(status, SessionEvent.RECOVERABLE_ERROR).value
                row.state_version += 1
                row.lease_expires_at = None
                row.updated_at = now
                status = SessionStatus(row.status)
            if status is SessionStatus.AWAITING_ANSWER and now > row.deadline_at:
                self._close(row, SessionEvent.TIMEOUT_OR_EXIT, "timeout")

    def _release_claim(self, session_id: uuid.UUID, turn_id: uuid.UUID, claimed: int) -> int:
        with self._db.begin() as db:
            row = repo.get_session(db, session_id, lock=True)
            turn = repo.get_turn_for_update(db, turn_id)
            assert row is not None and turn is not None
            if turn.status == "processing" and row.state_version == claimed:
                turn.status = "failed"
                row.status = transition(
                    SessionStatus(row.status), SessionEvent.RECOVERABLE_ERROR
                ).value
                row.state_version += 1
                row.lease_expires_at = None
                row.updated_at = self.clock()
            return row.state_version

    def _close(self, row: SessionRow, event: SessionEvent, reason: str) -> None:
        row.status = transition(SessionStatus(row.status), event).value
        row.finish_reason = reason
        row.current_question_id = row.current_purpose = row.current_hint_index = None
        row.state_version += 1
        row.updated_at = self.clock()

    def _evaluate(self, request: EvaluationRequest) -> EvaluatorOutput:
        # The worker thread keeps running after a timeout; its result is simply ignored.
        future = self._executor.submit(self.evaluator.evaluate, request)
        return future.result(timeout=self.config.evaluator_timeout_seconds)

    @staticmethod
    def _apply_action(row: SessionRow, action: Action) -> None:
        status = SessionStatus(row.status)
        if isinstance(action, Finish):
            row.status = transition(status, SessionEvent.BUDGET_MET).value
            row.finish_reason = action.reason.value
            row.current_question_id = row.current_purpose = row.current_hint_index = None
            return
        row.status = transition(status, SessionEvent.EVALUATION_SUCCEEDED).value
        row.finish_reason = None
        row.current_question_id = action.question_id
        if isinstance(action, GiveHint):
            row.current_purpose, row.current_hint_index = "hint", action.hint_index
        else:
            row.current_purpose, row.current_hint_index = action.purpose, None

    @staticmethod
    def _prompt(row: SessionRow, lesson: Lesson) -> Prompt | None:
        if row.current_question_id is None or row.current_purpose is None:
            return None
        question = lesson.question(row.current_question_id)
        hint = lead_in = None
        if row.current_purpose == "hint" and row.current_hint_index is not None:
            hint = question.hints[row.current_hint_index]
            lead_in = f"{HINT_LEAD_IN} {hint}"
        elif row.current_purpose == "clarify":
            lead_in = CLARIFY_LEAD_IN
        return Prompt(
            question_id=question.id,
            text=question.prompt,
            purpose=row.current_purpose,  # type: ignore[arg-type]
            lead_in=lead_in,
            hint=hint,
        )

    def _view(self, db: Session, row: SessionRow, lesson: Lesson) -> StudentSessionView:
        transcript = [
            TranscriptEntry(
                sequence=t.sequence,
                question_id=t.question_id,
                question_text=lesson.question(t.question_id).prompt,
                answer=t.transcript,
                modality=t.modality,  # type: ignore[arg-type]
                assisted=t.assisted,
            )
            for t in repo.committed_turns(db, row.id)
        ]
        return StudentSessionView(
            id=row.id,
            lesson=LessonRef(id=lesson.id, version=lesson.version, title=lesson.title),
            status=SessionStatus(row.status),
            state_version=row.state_version,
            prompt=self._prompt(row, lesson),
            finish_reason=row.finish_reason,  # type: ignore[arg-type]
            transcript=transcript,
            deadline_at=row.deadline_at,
        )
