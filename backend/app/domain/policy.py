"""Deterministic next-question policy.

`next_action` is a pure function of (lesson, turn history, elapsed time, budget).
It never invents a question ID: every ID it returns comes from the lesson.
Given the same inputs it always returns the same action, which makes sessions
replayable and the policy unit-testable without an LLM.

Rules, checked in order (PROJECT_PLAN.md §5 "Question policy"):

1. Learner asked to stop                        -> Finish(learner_request)
2. Turn or time budget used up                  -> Finish(budget)
3. Follow-up on the most recent turn:
   a. help requested and a hint remains          -> GiveHint (next answer is assisted)
   b. misconception flagged, diagnostic unused   -> AskQuestion(diagnostic)
   c. ambiguous for the first time on question   -> AskQuestion(clarify, same question)
4. First objective whose open question is unasked -> AskQuestion(open)
5. Nothing left                                 -> Finish(objectives_exhausted)

Why this terminates even without the budget: each open question is asked at most
once, each diagnostic at most once, each question is clarified at most once, and
each question has a finite list of hints. Every follow-up path is bounded.

What the policy deliberately does not do: score, judge correctness, or treat
silence/ambiguity as wrong. It only reacts to signals produced elsewhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.domain.errors import InvalidTurnRecordError
from app.domain.models import Lesson


class Signal(StrEnum):
    """What the evaluator/orchestrator concluded about one learner turn."""

    ANSWERED = "answered"  # usable evidence, no misconception flagged
    MISCONCEPTION = "misconception"  # evidence matches a declared misconception tag
    AMBIGUOUS = "ambiguous"  # empty, unclear, or insufficient evidence
    HELP_REQUESTED = "help_requested"
    STOP_REQUESTED = "stop_requested"


@dataclass(frozen=True)
class TurnRecord:
    question_id: str
    signal: Signal
    misconception_tag: str | None = None


@dataclass(frozen=True)
class Budget:
    max_turns: int = 5
    max_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.max_turns < 1 or self.max_seconds <= 0:
            raise ValueError("budget must allow at least one turn and positive time")


class FinishReason(StrEnum):
    LEARNER_REQUEST = "learner_request"
    BUDGET = "budget"
    OBJECTIVES_EXHAUSTED = "objectives_exhausted"


@dataclass(frozen=True)
class AskQuestion:
    question_id: str
    purpose: Literal["open", "diagnostic", "clarify"]


@dataclass(frozen=True)
class GiveHint:
    question_id: str
    hint_index: int


@dataclass(frozen=True)
class Finish:
    reason: FinishReason


Action = AskQuestion | GiveHint | Finish


def validate_history(lesson: Lesson, history: Sequence[TurnRecord]) -> None:
    """Reject records that reference unknown questions or inconsistent tags."""
    for index, record in enumerate(history):
        question = lesson.question(record.question_id)  # raises UnknownQuestionError
        tag = record.misconception_tag
        if record.signal is Signal.MISCONCEPTION:
            if tag is None:
                raise InvalidTurnRecordError(f"turn {index}: misconception signal needs a tag")
            misconception = lesson.misconception(tag)
            if misconception is None:
                raise InvalidTurnRecordError(f"turn {index}: undeclared misconception {tag!r}")
            if misconception.objective != question.objective:
                raise InvalidTurnRecordError(
                    f"turn {index}: misconception {tag!r} does not belong to the "
                    f"objective of question {question.id!r}"
                )
        elif tag is not None:
            raise InvalidTurnRecordError(
                f"turn {index}: tag {tag!r} given with signal {record.signal.value!r}"
            )


def next_action(
    lesson: Lesson,
    history: Sequence[TurnRecord],
    *,
    elapsed_seconds: float,
    budget: Budget | None = None,
) -> Action:
    budget = budget or Budget()
    if elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be non-negative")
    validate_history(lesson, history)

    last = history[-1] if history else None

    if last is not None and last.signal is Signal.STOP_REQUESTED:
        return Finish(FinishReason.LEARNER_REQUEST)
    if len(history) >= budget.max_turns or elapsed_seconds >= budget.max_seconds:
        return Finish(FinishReason.BUDGET)

    asked = {record.question_id for record in history}

    if last is not None:
        on_same_question = [r for r in history if r.question_id == last.question_id]

        if last.signal is Signal.HELP_REQUESTED:
            hints = lesson.question(last.question_id).hints
            hint_index = sum(r.signal is Signal.HELP_REQUESTED for r in on_same_question) - 1
            if hint_index < len(hints):
                return GiveHint(last.question_id, hint_index)

        elif last.signal is Signal.MISCONCEPTION:
            assert last.misconception_tag is not None  # guaranteed by validate_history
            diagnostic = lesson.diagnostic_for(last.misconception_tag)
            if diagnostic is not None and diagnostic.id not in asked:
                return AskQuestion(diagnostic.id, "diagnostic")

        elif last.signal is Signal.AMBIGUOUS:
            if sum(r.signal is Signal.AMBIGUOUS for r in on_same_question) == 1:
                return AskQuestion(last.question_id, "clarify")

    for objective in lesson.objectives:
        question = lesson.open_question_for(objective.id)
        if question.id not in asked:
            return AskQuestion(question.id, "open")

    return Finish(FinishReason.OBJECTIVES_EXHAUSTED)
