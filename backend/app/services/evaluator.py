"""Validate proposed evidence and derive the policy signal.

Nothing an evaluator returns is trusted. Each proposed item is checked against the pinned
lesson and the stored transcript, then classified:

  REJECTED   unknown criterion; criterion not assessed by this question; level outside
             0-3; quote empty or not found in the transcript; undeclared or off-objective
             misconception tag
  ABSTAINED  the evaluator declined (abstain=true or no level)
  ACCEPTED   everything checks out

Quote matching is "exact after normalisation": case, curly vs straight quotes, dashes and
runs of whitespace are ignored; everything else must match as one contiguous span.

The signal for the question policy uses ACCEPTED evidence only, so an invented quote can
never trigger a follow-up or change a suggested level. Missing evidence means AMBIGUOUS
(ask for clarification), never a zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models import RUBRIC_LEVELS, Lesson, Question
from app.domain.policy import Signal
from app.domain.scoring import EvidenceStatus
from app.providers.llm import EvaluatorOutput, LearnerIntent, ProposedEvidence

MAX_REASON_CHARS = 500
MIN_QUOTE_CHARS = 2

_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTE_CHARS)).strip().casefold()


@dataclass(frozen=True)
class ValidatedEvidence:
    criterion_id: str
    objective: str | None  # None if the criterion id was unknown
    proposed_level: int | None
    evidence_quote: str
    misconception_tag: str | None
    reason: str
    status: EvidenceStatus
    rejection_reason: str | None


@dataclass(frozen=True)
class TurnAssessment:
    signal: Signal
    misconception_tag: str | None
    evidence: tuple[ValidatedEvidence, ...]


def _validate_item(
    lesson: Lesson, question: Question, transcript: str, item: ProposedEvidence
) -> ValidatedEvidence:
    criterion = next((c for c in lesson.criteria if c.id == item.criterion_id), None)
    reason = item.reason.strip()[:MAX_REASON_CHARS]

    def result(
        status: EvidenceStatus,
        rejection: str | None = None,
        *,
        level: int | None = None,
        tag: str | None = None,
    ) -> ValidatedEvidence:
        return ValidatedEvidence(
            criterion_id=item.criterion_id[:64],
            objective=criterion.objective if criterion else None,
            proposed_level=level,
            evidence_quote=item.evidence_quote[:2000],
            misconception_tag=tag,
            reason=reason,
            status=status,
            rejection_reason=rejection,
        )

    if criterion is None:
        return result(EvidenceStatus.REJECTED, "unknown criterion")
    if criterion.objective != question.objective:
        return result(EvidenceStatus.REJECTED, "criterion is not assessed by this question")
    if item.abstain or item.proposed_level is None:
        return result(EvidenceStatus.ABSTAINED)
    if item.proposed_level not in RUBRIC_LEVELS:
        return result(EvidenceStatus.REJECTED, "level outside 0-3")

    quote = normalize_for_match(item.evidence_quote)
    if len(quote) < MIN_QUOTE_CHARS:
        return result(EvidenceStatus.REJECTED, "empty quote", level=item.proposed_level)
    if quote not in normalize_for_match(transcript):
        return result(
            EvidenceStatus.REJECTED, "quote not found in transcript", level=item.proposed_level
        )

    tag = item.misconception_tag
    if tag is not None:
        misconception = lesson.misconception(tag)
        if misconception is None or misconception.objective != question.objective:
            return result(
                EvidenceStatus.REJECTED,
                "misconception tag not allowed for this question",
                level=item.proposed_level,
            )
    return result(EvidenceStatus.ACCEPTED, level=item.proposed_level, tag=tag)


def validate_output(
    lesson: Lesson, question: Question, transcript: str, output: EvaluatorOutput
) -> TurnAssessment:
    evidence = tuple(_validate_item(lesson, question, transcript, i) for i in output.evidence)
    accepted = [e for e in evidence if e.status is EvidenceStatus.ACCEPTED]

    if output.intent is LearnerIntent.STOP_REQUEST:
        return TurnAssessment(Signal.STOP_REQUESTED, None, evidence)
    if output.intent is LearnerIntent.HELP_REQUEST:
        return TurnAssessment(Signal.HELP_REQUESTED, None, evidence)
    tagged = next((e for e in accepted if e.misconception_tag), None)
    if tagged is not None:
        return TurnAssessment(Signal.MISCONCEPTION, tagged.misconception_tag, evidence)
    if accepted:
        return TurnAssessment(Signal.ANSWERED, None, evidence)
    return TurnAssessment(Signal.AMBIGUOUS, None, evidence)
