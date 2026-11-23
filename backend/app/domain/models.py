"""Lesson content types and their structural invariants.

A lesson fixture is authored data. This module is the single place that decides
whether it is well-formed, so the policy and evaluator can trust it without
re-checking. Invariants enforced on construction:

* IDs are unique within their kind (objective, criterion, misconception, question).
* 2-4 objectives; each has exactly one rubric criterion and at least one open question.
* Every criterion has descriptors for exactly levels 0, 1, 2 and 3.
* Every reference (question -> objective, diagnostic -> misconception) resolves,
  and a diagnostic targets a misconception of its own objective.
* At most one diagnostic question per misconception, so the policy's choice is unambiguous.

Models are frozen: a published lesson version must not change in memory either.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.errors import UnknownQuestionError

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
RUBRIC_LEVELS: tuple[int, ...] = (0, 1, 2, 3)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Objective(_Frozen):
    id: Identifier
    description: str = Field(min_length=1)


class RubricCriterion(_Frozen):
    id: Identifier
    objective: Identifier
    # JSON object keys are strings, so levels are keyed "0".."3".
    levels: dict[str, str]

    @model_validator(mode="after")
    def _has_exactly_four_levels(self) -> RubricCriterion:
        expected = {str(level) for level in RUBRIC_LEVELS}
        if set(self.levels) != expected:
            raise ValueError(
                f"criterion {self.id!r} must define levels {sorted(expected)}, "
                f"got {sorted(self.levels)}"
            )
        if any(not text.strip() for text in self.levels.values()):
            raise ValueError(f"criterion {self.id!r} has an empty level descriptor")
        return self


class Misconception(_Frozen):
    tag: Identifier
    objective: Identifier
    description: str = Field(min_length=1)


class QuestionKind(StrEnum):
    OPEN = "open"  # unassisted first question for an objective
    DIAGNOSTIC = "diagnostic"  # approved follow-up that probes one misconception


class Question(_Frozen):
    id: Identifier
    objective: Identifier
    kind: QuestionKind
    prompt: str = Field(min_length=1, max_length=500)
    difficulty: int = Field(ge=1, le=3)
    hints: tuple[str, ...] = ()
    targets_misconception: Identifier | None = None

    @model_validator(mode="after")
    def _target_matches_kind(self) -> Question:
        if self.kind is QuestionKind.DIAGNOSTIC and self.targets_misconception is None:
            raise ValueError(f"diagnostic question {self.id!r} must set targets_misconception")
        if self.kind is QuestionKind.OPEN and self.targets_misconception is not None:
            raise ValueError(f"open question {self.id!r} must not set targets_misconception")
        return self


def _duplicates(values: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


class Lesson(_Frozen):
    id: Identifier
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    objectives: tuple[Objective, ...] = Field(min_length=2, max_length=4)
    criteria: tuple[RubricCriterion, ...]
    misconceptions: tuple[Misconception, ...] = ()
    questions: tuple[Question, ...]

    @model_validator(mode="after")
    def _references_resolve(self) -> Lesson:
        errors: list[str] = []
        for kind, ids in (
            ("objective", [o.id for o in self.objectives]),
            ("criterion", [c.id for c in self.criteria]),
            ("misconception", [m.tag for m in self.misconceptions]),
            ("question", [q.id for q in self.questions]),
        ):
            if dupes := _duplicates(ids):
                errors.append(f"duplicate {kind} ids: {dupes}")

        objective_ids = {o.id for o in self.objectives}
        misconceptions = {m.tag: m for m in self.misconceptions}

        criteria_per_objective = Counter(c.objective for c in self.criteria)
        for criterion in self.criteria:
            if criterion.objective not in objective_ids:
                errors.append(f"criterion {criterion.id!r} references unknown objective")
        for objective_id in objective_ids:
            if criteria_per_objective[objective_id] != 1:
                errors.append(f"objective {objective_id!r} needs exactly one rubric criterion")

        for m in self.misconceptions:
            if m.objective not in objective_ids:
                errors.append(f"misconception {m.tag!r} references unknown objective")

        for q in self.questions:
            if q.objective not in objective_ids:
                errors.append(f"question {q.id!r} references unknown objective {q.objective!r}")
            if q.targets_misconception is not None:
                target = misconceptions.get(q.targets_misconception)
                if target is None:
                    errors.append(
                        f"question {q.id!r} targets undeclared misconception "
                        f"{q.targets_misconception!r}"
                    )
                elif target.objective != q.objective:
                    errors.append(
                        f"question {q.id!r} targets misconception of a different objective"
                    )

        targets = [q.targets_misconception for q in self.questions if q.targets_misconception]
        if dupes := _duplicates(targets):
            errors.append(f"more than one diagnostic for misconceptions: {dupes}")

        open_objectives = {q.objective for q in self.questions if q.kind is QuestionKind.OPEN}
        for objective_id in sorted(objective_ids - open_objectives):
            errors.append(f"objective {objective_id!r} has no open question")

        if errors:
            raise ValueError(f"lesson {self.id!r} v{self.version}: " + "; ".join(errors))
        return self

    # --- lookups used by the policy and evaluator ---------------------------------

    def question(self, question_id: str) -> Question:
        for q in self.questions:
            if q.id == question_id:
                return q
        raise UnknownQuestionError(
            f"question {question_id!r} is not in lesson {self.id!r} v{self.version}"
        )

    def open_question_for(self, objective_id: str) -> Question:
        """The first open question authored for an objective (validation guarantees one)."""
        return next(
            q for q in self.questions if q.objective == objective_id and q.kind is QuestionKind.OPEN
        )

    def diagnostic_for(self, misconception_tag: str) -> Question | None:
        return next(
            (q for q in self.questions if q.targets_misconception == misconception_tag),
            None,
        )

    def misconception(self, tag: str) -> Misconception | None:
        return next((m for m in self.misconceptions if m.tag == tag), None)
