import pytest

from app.domain.errors import IllegalTransitionError
from app.domain.state import (
    TERMINAL_STATUSES,
    TRANSITIONS,
    SessionEvent,
    SessionStatus,
    allowed_events,
    is_terminal,
    transition,
)

S, E = SessionStatus, SessionEvent


@pytest.mark.parametrize(
    ("status", "event", "expected"),
    [
        (S.CREATED, E.START, S.AWAITING_ANSWER),
        (S.AWAITING_ANSWER, E.TURN_FINALIZED, S.EVALUATING),
        (S.EVALUATING, E.EVALUATION_SUCCEEDED, S.AWAITING_ANSWER),
        (S.EVALUATING, E.BUDGET_MET, S.COMPLETED),
        (S.EVALUATING, E.RECOVERABLE_ERROR, S.AWAITING_ANSWER),
        (S.AWAITING_ANSWER, E.TIMEOUT_OR_EXIT, S.INCOMPLETE),
        (S.EVALUATING, E.TERMINAL_FAILURE, S.INCOMPLETE),
    ],
)
def test_legal_transitions(status: SessionStatus, event: SessionEvent, expected: SessionStatus):
    assert transition(status, event) is expected


ILLEGAL = [(s, e) for s in S for e in E if (s, e) not in TRANSITIONS]


@pytest.mark.parametrize(("status", "event"), ILLEGAL)
def test_every_unlisted_pair_is_rejected(status: SessionStatus, event: SessionEvent):
    with pytest.raises(IllegalTransitionError):
        transition(status, event)


def test_specific_illegal_moves_named_in_plan():
    # A turn cannot be submitted while the previous one is still being evaluated,
    # and a session cannot skip straight from created to evaluating.
    with pytest.raises(IllegalTransitionError):
        transition(S.EVALUATING, E.TURN_FINALIZED)
    with pytest.raises(IllegalTransitionError):
        transition(S.CREATED, E.TURN_FINALIZED)


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
def test_terminal_statuses_accept_no_events(status: SessionStatus):
    assert is_terminal(status)
    assert allowed_events(status) == frozenset()
    for event in E:
        with pytest.raises(IllegalTransitionError):
            transition(status, event)


def test_every_non_terminal_status_can_reach_a_terminal_status():
    # Guards against adding a status that traps sessions forever.
    for start in S:
        seen, frontier = {start}, [start]
        while frontier:
            current = frontier.pop()
            for event in allowed_events(current):
                nxt = transition(current, event)
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        assert seen & TERMINAL_STATUSES, f"{start} cannot reach a terminal status"


def test_transition_table_is_read_only():
    with pytest.raises(TypeError):
        TRANSITIONS[(S.COMPLETED, E.START)] = S.AWAITING_ANSWER  # type: ignore[index]
