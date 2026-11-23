"""Session state machine.

The transition table below is the whole state machine from PROJECT_PLAN.md §5.
Anything not listed is illegal. Callers apply an event and persist the returned
status; they never assign a status directly. Report status (pending ->
ready_for_review -> approved/rejected) is a separate lifecycle and lives elsewhere.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from app.domain.errors import IllegalTransitionError


class SessionStatus(StrEnum):
    CREATED = "created"
    AWAITING_ANSWER = "awaiting_answer"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"


class SessionEvent(StrEnum):
    START = "start"
    TURN_FINALIZED = "turn_finalized"
    EVALUATION_SUCCEEDED = "evaluation_succeeded"  # result validated, next question chosen
    BUDGET_MET = "budget_met"  # policy chose to finish
    RECOVERABLE_ERROR = "recoverable_error"  # e.g. evaluator timeout; learner may retry
    TIMEOUT_OR_EXIT = "timeout_or_exit"
    TERMINAL_FAILURE = "terminal_failure"


S, E = SessionStatus, SessionEvent

TRANSITIONS: Mapping[tuple[SessionStatus, SessionEvent], SessionStatus] = MappingProxyType(
    {
        (S.CREATED, E.START): S.AWAITING_ANSWER,
        (S.AWAITING_ANSWER, E.TURN_FINALIZED): S.EVALUATING,
        (S.EVALUATING, E.EVALUATION_SUCCEEDED): S.AWAITING_ANSWER,
        (S.EVALUATING, E.BUDGET_MET): S.COMPLETED,
        (S.EVALUATING, E.RECOVERABLE_ERROR): S.AWAITING_ANSWER,
        (S.AWAITING_ANSWER, E.TIMEOUT_OR_EXIT): S.INCOMPLETE,
        (S.EVALUATING, E.TERMINAL_FAILURE): S.INCOMPLETE,
    }
)

TERMINAL_STATUSES: frozenset[SessionStatus] = frozenset({S.COMPLETED, S.INCOMPLETE})


def transition(status: SessionStatus, event: SessionEvent) -> SessionStatus:
    """Return the status reached by applying `event`, or raise IllegalTransitionError."""
    try:
        return TRANSITIONS[(status, event)]
    except KeyError:
        raise IllegalTransitionError(
            f"event {event.value!r} is not allowed from status {status.value!r}"
        ) from None


def allowed_events(status: SessionStatus) -> frozenset[SessionEvent]:
    return frozenset(event for (source, event) in TRANSITIONS if source is status)


def is_terminal(status: SessionStatus) -> bool:
    return status in TERMINAL_STATUSES
