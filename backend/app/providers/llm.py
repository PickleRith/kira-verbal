"""Evaluator interface.

The orchestrator depends only on this Protocol, so the deterministic fake (Day 2)
and the LLM-backed adapter (Day 3) are interchangeable. An evaluator classifies one
learner turn into a policy Signal; it does not pick questions or set scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import Lesson, Question
from app.domain.policy import Signal


@dataclass(frozen=True)
class EvaluationRequest:
    lesson: Lesson
    question: Question
    transcript: str  # untrusted learner text
    assisted: bool


@dataclass(frozen=True)
class EvaluationResult:
    signal: Signal
    misconception_tag: str | None
    evaluator_version: str


class Evaluator(Protocol):
    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        """Classify one turn. May raise; the orchestrator treats any error as recoverable."""
        ...
