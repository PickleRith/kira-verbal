"""Orchestrator tests against real Postgres: flow, idempotency, concurrency, recovery."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, func, select

from app.db.models import SessionRow, TurnRow
from app.domain.policy import Signal
from app.domain.state import SessionStatus
from app.providers.llm import EvaluationResult
from app.schemas.sessions import TurnInput, TurnResponse
from app.services.assessment import AssessmentService
from app.services.errors import (
    ClaimLostError,
    EvaluationUnavailableError,
    IdempotencyMismatchError,
    QuestionMismatchError,
    SessionClosedError,
    SessionNotFoundError,
    StaleStateVersionError,
    TurnInProgressError,
)

pytestmark = pytest.mark.integration

GOOD_Q1 = "Plants use sunlight to make sugar from carbon dioxide and water, and release oxygen."
ROOTS_Q2 = "From the soil through its roots."
GOOD_Q3 = "Through tiny holes called stomata on the leaves."
GOOD_Q4 = "Light gives the energy the plant needs to make sugar."


class Learner:
    """Tracks the client-side state a real browser would keep."""

    def __init__(self, service: AssessmentService, lesson_id: str = "photosynthesis") -> None:
        view, self.token = service.create_session(lesson_id, None, "demo-learner")
        self.service, self.id = service, view.id
        self.version = view.state_version
        self.question_id = view.prompt.question_id if view.prompt else None
        self.count = 0

    def turn(
        self,
        text: str,
        *,
        cid: str | None = None,
        version: int | None = None,
        qid: str | None = None,
    ) -> TurnInput:
        self.count += 1
        return TurnInput(
            client_turn_id=cid or f"turn-{self.count}",
            expected_state_version=self.version if version is None else version,
            transcript=text,
            modality="text",
            question_id=qid or self.question_id or "q1",
        )

    def submit(self, turn: TurnInput) -> TurnResponse:
        response = self.service.submit_turn(self.id, self.token, turn)
        self.version = response.state_version
        self.question_id = response.prompt.question_id if response.prompt else None
        return response

    def say(self, text: str, **kwargs) -> TurnResponse:
        return self.submit(self.turn(text, **kwargs))

    def refresh(self) -> None:
        view = self.service.get_session(self.id, self.token)
        self.version = view.state_version
        self.question_id = view.prompt.question_id if view.prompt else None


def count_turns(engine: Engine, session_id: uuid.UUID, status: str) -> int:
    with engine.connect() as c:
        return c.scalar(
            select(func.count())
            .select_from(TurnRow)
            .where(TurnRow.session_id == session_id, TurnRow.status == status)
        )


def session_status(engine: Engine, session_id: uuid.UUID) -> str:
    with engine.connect() as c:
        return c.scalar(select(SessionRow.status).where(SessionRow.id == session_id))


# --- happy paths ---------------------------------------------------------------------


def test_full_photosynthesis_assessment_with_adaptive_follow_up(service, seeded_engine):
    learner = Learner(service)
    assert learner.question_id == "q1" and learner.version == 1

    r = learner.say(GOOD_Q1)
    assert (r.prompt.question_id, r.prompt.purpose) == ("q2", "open")

    r = learner.say(ROOTS_Q2)  # misconception -> approved diagnostic follow-up
    assert (r.prompt.question_id, r.prompt.purpose) == ("q3", "diagnostic")

    r = learner.say(GOOD_Q3)
    assert (r.prompt.question_id, r.prompt.purpose) == ("q4", "open")

    r = learner.say(GOOD_Q4)
    assert r.status is SessionStatus.COMPLETED
    assert r.prompt is None and r.finish_reason == "objectives_exhausted"

    view = service.get_session(learner.id, learner.token)
    assert [t.question_id for t in view.transcript] == ["q1", "q2", "q3", "q4"]
    assert count_turns(seeded_engine, learner.id, "committed") == 4
    with seeded_engine.connect() as c:
        signals = c.execute(
            select(TurnRow.signal, TurnRow.misconception_tag)
            .where(TurnRow.session_id == learner.id)
            .order_by(TurnRow.sequence)
        ).all()
    assert signals[1] == ("misconception", "co2_from_roots")


def test_hint_marks_following_answer_assisted(service):
    learner = Learner(service)
    r = learner.say("Can I have a hint?")
    assert r.prompt.purpose == "hint" and r.prompt.question_id == "q1"
    assert r.prompt.hint and r.prompt.lead_in.startswith("Here's a hint:")

    r = learner.say(GOOD_Q1)
    assert r.prompt.question_id == "q2"
    transcript = service.get_session(learner.id, learner.token).transcript
    assert [t.assisted for t in transcript] == [False, True]


def test_ambiguous_answer_gets_clarification_not_a_score(service):
    learner = Learner(service)
    r = learner.say("yes")
    assert r.prompt.purpose == "clarify" and r.prompt.question_id == "q1"
    assert r.prompt.lead_in


def test_stop_phrase_finishes_with_learner_request(service):
    learner = Learner(service)
    r = learner.say("I want to stop")
    assert r.status is SessionStatus.COMPLETED and r.finish_reason == "learner_request"


def test_turn_budget_ends_session(service):
    learner = Learner(service)
    for text in ["yes", "maybe", "no", "hmm", "ok"]:
        r = learner.say(text)
    assert r.status is SessionStatus.COMPLETED and r.finish_reason == "budget"


def test_invalid_evaluator_tag_is_treated_as_ambiguous(service, evaluator, seeded_engine):
    learner = Learner(service)
    learner.say(GOOD_Q1)  # now on q2 (carbon_dioxide)
    evaluator.override = EvaluationResult(Signal.MISCONCEPTION, "light_is_food", "test")
    r = learner.say(ROOTS_Q2)
    assert r.prompt.purpose == "clarify"
    with seeded_engine.connect() as c:
        tag = c.scalar(select(TurnRow.misconception_tag).where(TurnRow.question_id == "q2"))
    assert tag is None


# --- idempotency and versioning ------------------------------------------------------


def test_identical_retry_returns_stored_response_without_reevaluating(
    service, evaluator, seeded_engine
):
    learner = Learner(service)
    turn = learner.turn(GOOD_Q1)
    first = learner.submit(turn)
    second = service.submit_turn(learner.id, learner.token, turn)  # e.g. network retry
    assert second == first
    assert evaluator.calls == 1
    assert count_turns(seeded_engine, learner.id, "committed") == 1


def test_reused_turn_id_with_different_payload_conflicts(service):
    learner = Learner(service)
    turn = learner.turn(GOOD_Q1, cid="same-id")
    learner.submit(turn)
    altered = turn.model_copy(update={"transcript": "something else entirely"})
    with pytest.raises(IdempotencyMismatchError):
        service.submit_turn(learner.id, learner.token, altered)


def test_stale_state_version_conflicts_and_reports_current_version(service):
    learner = Learner(service)
    learner.say(GOOD_Q1)
    with pytest.raises(StaleStateVersionError) as info:
        learner.say(ROOTS_Q2, version=1)
    assert info.value.state_version == learner.version


def test_answer_for_wrong_question_conflicts(service):
    learner = Learner(service)
    with pytest.raises(QuestionMismatchError):
        learner.say(GOOD_Q1, qid="q4")


def test_wrong_token_and_unknown_session_look_identical(service):
    learner = Learner(service)
    with pytest.raises(SessionNotFoundError):
        service.get_session(learner.id, "not-the-token")
    with pytest.raises(SessionNotFoundError):
        service.get_session(uuid.uuid4(), learner.token)


# --- concurrency ---------------------------------------------------------------------


def _race(n: int, fn):
    barrier = threading.Barrier(n)

    def run(i: int):
        barrier.wait()
        try:
            return fn(i)
        except Exception as exc:  # noqa: BLE001 - collected for assertions
            return exc

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))


def test_simultaneous_different_turns_commit_exactly_once(service, seeded_engine):
    learner = Learner(service)
    turns = [learner.turn(f"Answer number {i} about sugar and light.") for i in range(8)]
    results = _race(8, lambda i: service.submit_turn(learner.id, learner.token, turns[i]))

    successes = [r for r in results if isinstance(r, TurnResponse)]
    failures = [r for r in results if not isinstance(r, TurnResponse)]
    assert len(successes) == 1
    assert all(isinstance(f, StaleStateVersionError | TurnInProgressError) for f in failures)
    assert count_turns(seeded_engine, learner.id, "committed") == 1


def test_simultaneous_retries_of_one_turn_commit_once(service, evaluator, seeded_engine):
    learner = Learner(service)
    turn = learner.turn(GOOD_Q1, cid="double-click")
    results = _race(8, lambda _: service.submit_turn(learner.id, learner.token, turn))

    successes = [r for r in results if isinstance(r, TurnResponse)]
    assert successes and all(s == successes[0] for s in successes)
    assert all(isinstance(r, TurnResponse | TurnInProgressError) for r in results)
    assert evaluator.calls == 1
    assert count_turns(seeded_engine, learner.id, "committed") == 1


def test_submissions_while_evaluating_are_rejected(service, evaluator):
    learner = Learner(service)
    evaluator.gate = threading.Event()
    turn = learner.turn(GOOD_Q1, cid="slow")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.submit_turn, learner.id, learner.token, turn)
        assert evaluator.entered.wait(5)
        with pytest.raises(TurnInProgressError):  # same id: still processing
            service.submit_turn(learner.id, learner.token, turn)
        with pytest.raises(StaleStateVersionError):  # different id: version moved on
            learner.say("another answer here", cid="other")
        evaluator.gate.set()
        assert pending.result(timeout=5).prompt.question_id == "q2"


# --- failure and recovery ------------------------------------------------------------


def test_evaluator_error_releases_turn_and_same_id_can_retry(service, evaluator, seeded_engine):
    learner = Learner(service)
    evaluator.raise_next = ConnectionError("provider down")
    turn = learner.turn(GOOD_Q1, cid="retry-me")
    with pytest.raises(EvaluationUnavailableError) as info:
        service.submit_turn(learner.id, learner.token, turn)
    assert info.value.state_version == 3  # claimed (2), released (3)
    assert session_status(seeded_engine, learner.id) == "awaiting_answer"

    retried = learner.submit(turn.model_copy(update={"expected_state_version": 3}))
    assert retried.prompt.question_id == "q2"
    assert count_turns(seeded_engine, learner.id, "committed") == 1
    assert count_turns(seeded_engine, learner.id, "failed") == 1


def test_evaluator_timeout_is_recoverable(service, evaluator):
    learner = Learner(service)
    evaluator.delay_seconds = 1.5  # service timeout is 1.0 s in tests
    with pytest.raises(EvaluationUnavailableError):
        learner.say(GOOD_Q1)


def test_crash_between_claim_and_commit_is_recovered_without_duplicates(
    service, evaluator, clock, seeded_engine, simulated_crash
):
    learner = Learner(service)
    evaluator.raise_next = simulated_crash()
    turn = learner.turn(GOOD_Q1, cid="crashy")
    with pytest.raises(simulated_crash):
        service.submit_turn(learner.id, learner.token, turn)
    assert session_status(seeded_engine, learner.id) == "evaluating"  # claim left behind

    with pytest.raises(TurnInProgressError):  # lease not yet expired
        service.submit_turn(learner.id, learner.token, turn)

    clock.advance(31)  # past the 30 s processing lease
    learner.refresh()
    assert session_status(seeded_engine, learner.id) == "awaiting_answer"

    retried = learner.submit(turn.model_copy(update={"expected_state_version": learner.version}))
    assert retried.prompt.question_id == "q2"
    assert count_turns(seeded_engine, learner.id, "committed") == 1
    assert count_turns(seeded_engine, learner.id, "failed") == 1


def test_late_commit_after_recovery_is_rejected(service, evaluator, clock, seeded_engine):
    learner = Learner(service)
    evaluator.gate = threading.Event()
    turn = learner.turn(GOOD_Q1, cid="too-slow")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.submit_turn, learner.id, learner.token, turn)
        assert evaluator.entered.wait(5)
        clock.advance(31)
        learner.refresh()  # another request recovers the expired claim
        evaluator.gate.set()
        with pytest.raises(ClaimLostError):
            pending.result(timeout=5)
    assert count_turns(seeded_engine, learner.id, "committed") == 0


# --- deadline and exit ---------------------------------------------------------------


def test_idle_session_past_deadline_becomes_incomplete(service, clock):
    learner = Learner(service)
    clock.advance(300 + 60 + 1)
    with pytest.raises(SessionClosedError):
        learner.say(GOOD_Q1)
    view = service.get_session(learner.id, learner.token)
    assert view.status is SessionStatus.INCOMPLETE and view.finish_reason == "timeout"


def test_learner_exit_marks_incomplete_and_is_idempotent(service):
    learner = Learner(service)
    learner.say(GOOD_Q1)
    view = service.finish(learner.id, learner.token, learner.version)
    assert view.status is SessionStatus.INCOMPLETE and view.finish_reason == "learner_exit"
    again = service.finish(learner.id, learner.token, learner.version)
    assert again == view
    with pytest.raises(SessionClosedError):
        learner.say(ROOTS_Q2, version=view.state_version)


def test_finish_with_stale_version_conflicts(service):
    learner = Learner(service)
    learner.say(GOOD_Q1)
    with pytest.raises(StaleStateVersionError):
        service.finish(learner.id, learner.token, 1)
