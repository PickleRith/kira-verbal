"""Rubric aggregation: turn validated evidence into per-criterion *suggestions*.

Rules (PROJECT_PLAN.md §5 "Evaluator contract"):
* Only ACCEPTED evidence with a level counts. Abstained and rejected items never do.
* The suggested level for a criterion is the level of the latest accepted *independent*
  (unassisted) evidence. No such evidence -> None ("unknown"), never 0.
* Assisted evidence (given after a hint) is reported separately and never sets the
  suggested level.
* Different independent levels for one criterion -> `conflicting`, which needs review.
  Any rejected item (e.g. a quote the model invented) also flags the session for review.
* Coverage = criteria with a suggested level / all criteria, reported as a count pair,
  not a percentage, so it is not mistaken for a mastery score.

These are suggestions for a teacher, who owns every final decision.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.domain.models import Lesson


class EvidenceStatus(StrEnum):
    ACCEPTED = "accepted"  # passed validation and carries a level
    ABSTAINED = "abstained"  # evaluator declined to propose a level
    REJECTED = "rejected"  # failed validation; stored for audit only


@dataclass(frozen=True)
class EvidenceRecord:
    criterion_id: str
    level: int | None
    status: EvidenceStatus
    assisted: bool
    misconception_tag: str | None
    sequence: int  # turn order within the session


@dataclass(frozen=True)
class CriterionSummary:
    criterion_id: str
    objective: str
    suggested_level: int | None  # None = unknown
    independent_levels: tuple[int, ...]  # in turn order
    assisted_levels: tuple[int, ...]
    misconception_tags: tuple[str, ...]
    conflicting: bool
    abstentions: int
    rejected: int


@dataclass(frozen=True)
class ScoreSummary:
    criteria: tuple[CriterionSummary, ...]
    criteria_with_evidence: int
    criteria_total: int
    needs_review: bool


def summarize(lesson: Lesson, records: Iterable[EvidenceRecord]) -> ScoreSummary:
    by_criterion: dict[str, list[EvidenceRecord]] = {c.id: [] for c in lesson.criteria}
    for record in records:
        if record.criterion_id in by_criterion:  # unknown ids are already rejected upstream
            by_criterion[record.criterion_id].append(record)

    summaries: list[CriterionSummary] = []
    for criterion in lesson.criteria:
        items = sorted(by_criterion[criterion.id], key=lambda r: r.sequence)
        accepted = [r for r in items if r.status is EvidenceStatus.ACCEPTED and r.level is not None]
        independent = [r.level for r in accepted if not r.assisted]
        assisted = [r.level for r in accepted if r.assisted]
        tags = tuple(dict.fromkeys(r.misconception_tag for r in accepted if r.misconception_tag))
        summaries.append(
            CriterionSummary(
                criterion_id=criterion.id,
                objective=criterion.objective,
                suggested_level=independent[-1] if independent else None,
                independent_levels=tuple(independent),  # type: ignore[arg-type]
                assisted_levels=tuple(assisted),  # type: ignore[arg-type]
                misconception_tags=tags,
                conflicting=len(set(independent)) > 1,
                abstentions=sum(r.status is EvidenceStatus.ABSTAINED for r in items),
                rejected=sum(r.status is EvidenceStatus.REJECTED for r in items),
            )
        )

    return ScoreSummary(
        criteria=tuple(summaries),
        criteria_with_evidence=sum(s.suggested_level is not None for s in summaries),
        criteria_total=len(summaries),
        needs_review=any(s.conflicting or s.rejected for s in summaries),
    )
