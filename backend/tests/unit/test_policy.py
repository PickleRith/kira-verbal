import random

import pytest

from app.domain.errors import InvalidTurnRecordError, UnknownQuestionError
from app.domain.models import Lesson
from app.domain.policy import (
    AskQuestion,
    Budget,
    Finish,
    FinishReason,
    GiveHint,
    Signal,
    TurnRecord,
    next_action,
)
from app.lesson_catalog import load_catalog

ROOMY = Budget(max_turns=50, max_seconds=10_000)


def act(lesson: Lesson, *records: TurnRecord, elapsed: float = 0.0, budget: Budget = ROOMY):
    return next_action(lesson, list(records), elapsed_seconds=elapsed, budget=budget)


def test_first_action_is_open_question_for_first_objective(photosynthesis: Lesson):
    assert act(photosynthesis) == AskQuestion("q1", "open")


def test_answered_moves_to_next_uncovered_objective(photosynthesis: Lesson):
    assert act(photosynthesis, TurnRecord("q1", Signal.ANSWERED)) == AskQuestion("q2", "open")


def test_roots_misconception_triggers_approved_diagnostic(photosynthesis: Lesson):
    history = [
        TurnRecord("q1", Signal.ANSWERED),
        TurnRecord("q2", Signal.MISCONCEPTION, "co2_from_roots"),
    ]
    assert act(photosynthesis, *history) == AskQuestion("q3", "diagnostic")


def test_diagnostic_is_asked_at_most_once(photosynthesis: Lesson):
    history = [
        TurnRecord("q2", Signal.MISCONCEPTION, "co2_from_roots"),
        TurnRecord("q3", Signal.MISCONCEPTION, "co2_from_roots"),
    ]
    action = act(photosynthesis, *history)
    assert action == AskQuestion("q1", "open")  # moves on instead of looping


def test_ambiguous_answer_gets_one_clarification_then_moves_on(photosynthesis: Lesson):
    once = [TurnRecord("q1", Signal.AMBIGUOUS)]
    assert act(photosynthesis, *once) == AskQuestion("q1", "clarify")
    twice = [*once, TurnRecord("q1", Signal.AMBIGUOUS)]
    assert act(photosynthesis, *twice) == AskQuestion("q2", "open")


def test_help_request_delivers_permitted_hints_then_moves_on(photosynthesis: Lesson):
    first = [TurnRecord("q1", Signal.HELP_REQUESTED)]
    assert act(photosynthesis, *first) == GiveHint("q1", 0)
    # q1 has exactly one authored hint; a second request must not invent another.
    second = [*first, TurnRecord("q1", Signal.HELP_REQUESTED)]
    assert act(photosynthesis, *second) == AskQuestion("q2", "open")


def test_help_on_question_without_hints_moves_on(photosynthesis: Lesson):
    assert photosynthesis.question("q3").hints == ()
    history = [
        TurnRecord("q2", Signal.MISCONCEPTION, "co2_from_roots"),
        TurnRecord("q3", Signal.HELP_REQUESTED),
    ]
    assert act(photosynthesis, *history) == AskQuestion("q1", "open")


def test_stop_request_finishes_immediately(photosynthesis: Lesson):
    action = act(photosynthesis, TurnRecord("q1", Signal.STOP_REQUESTED))
    assert action == Finish(FinishReason.LEARNER_REQUEST)


def test_turn_budget_finishes(photosynthesis: Lesson):
    history = [TurnRecord("q1", Signal.AMBIGUOUS), TurnRecord("q1", Signal.AMBIGUOUS)]
    action = act(photosynthesis, *history, budget=Budget(max_turns=2, max_seconds=300))
    assert action == Finish(FinishReason.BUDGET)


def test_time_budget_finishes(photosynthesis: Lesson):
    action = act(photosynthesis, elapsed=300.0, budget=Budget(max_turns=5, max_seconds=300))
    assert action == Finish(FinishReason.BUDGET)


def test_all_objectives_attempted_finishes(photosynthesis: Lesson):
    history = [TurnRecord(q, Signal.ANSWERED) for q in ("q1", "q2", "q4")]
    assert act(photosynthesis, *history) == Finish(FinishReason.OBJECTIVES_EXHAUSTED)


# --- rejection of bad inputs --------------------------------------------------------


def test_unknown_question_id_is_rejected(photosynthesis: Lesson):
    with pytest.raises(UnknownQuestionError):
        act(photosynthesis, TurnRecord("q99", Signal.ANSWERED))


@pytest.mark.parametrize(
    "record",
    [
        TurnRecord("q2", Signal.MISCONCEPTION, None),  # missing tag
        TurnRecord("q2", Signal.MISCONCEPTION, "made_up_tag"),  # undeclared tag
        TurnRecord("q2", Signal.MISCONCEPTION, "light_is_food"),  # tag from another objective
        TurnRecord("q2", Signal.ANSWERED, "co2_from_roots"),  # tag without misconception
    ],
)
def test_inconsistent_records_are_rejected(photosynthesis: Lesson, record: TurnRecord):
    with pytest.raises(InvalidTurnRecordError):
        act(photosynthesis, record)


def test_negative_elapsed_time_is_rejected(photosynthesis: Lesson):
    with pytest.raises(ValueError):
        act(photosynthesis, elapsed=-1)


def test_policy_is_deterministic(photosynthesis: Lesson):
    history = [TurnRecord("q1", Signal.ANSWERED), TurnRecord("q2", Signal.AMBIGUOUS)]
    assert len({act(photosynthesis, *history) for _ in range(20)}) == 1


# --- property-style check over every real lesson ------------------------------------


def _random_record(rng: random.Random, lesson: Lesson, question_id: str) -> TurnRecord:
    question = lesson.question(question_id)
    tags = [m.tag for m in lesson.misconceptions if m.objective == question.objective]
    signal = rng.choice([s for s in Signal if s is not Signal.STOP_REQUESTED])
    if signal is Signal.MISCONCEPTION:
        return TurnRecord(question_id, signal, rng.choice(tags))
    return TurnRecord(question_id, signal)


@pytest.mark.parametrize("seed", range(200))
def test_any_learner_behaviour_terminates_with_only_lesson_question_ids(lessons_dir, seed):
    """Without a turn budget the policy must still finish, using only real IDs."""
    rng = random.Random(seed)
    for lesson in load_catalog(lessons_dir):
        valid_ids = {q.id for q in lesson.questions}
        # Upper bound from the termination argument in policy.py.
        bound = sum(2 + len(q.hints) for q in lesson.questions) + len(lesson.questions) + 1
        history: list[TurnRecord] = []
        for _ in range(bound):
            action = act(lesson, *history)
            if isinstance(action, Finish):
                break
            assert action.question_id in valid_ids
            history.append(_random_record(rng, lesson, action.question_id))
        else:
            pytest.fail(f"{lesson.id}: policy did not finish within {bound} steps")
