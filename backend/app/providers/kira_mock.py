"""Mock Kira export adapter: the proposed shape of an approved oral-assessment result.

This is NOT a Kira Learning API. Kira Verbal is an independent prototype with no access to
Kira's systems, and this module sends nothing anywhere. It defines the payload an actual
integration could send after a teacher approves a report, and a fake client that records
deliveries the way an idempotent receiver would.

Why export is its own boundary:
* Only a teacher-approved report revision can be exported. Suggestions never leave the
  system on their own.
* The payload is built from the approved revision alone, so later edits can't change what
  was sent. A new approval is a new revision with its own idempotency key.
* The idempotency key is deterministic (session + revision). Retries, double clicks and
  replays produce the same key, so a receiver applies the update at most once.
* Levels the teacher left unknown are exported as `insufficient_evidence` with a null
  level, never as zero.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "kira-verbal.mastery-update.v1"
DISCLAIMER = (
    "Independent prototype export. Not a Kira Learning API or gradebook record. "
    "Synthetic data only; levels are teacher-approved rubric judgments, not proof of mastery."
)


def idempotency_key(session_id: uuid.UUID, revision: int) -> str:
    return f"kira-verbal:{session_id}:rev{revision}"


@dataclass(frozen=True)
class ExportEvidence:
    turn_sequence: int
    quote: str
    assisted: bool
    misconception_tag: str | None


@dataclass(frozen=True)
class ExportCriterion:
    criterion_id: str
    objective_id: str
    level: int | None  # teacher-approved; None = insufficient evidence
    suggested_level: int | None
    misconception_tags: tuple[str, ...]
    evidence: tuple[ExportEvidence, ...]  # accepted evidence only


@dataclass(frozen=True)
class ExportInput:
    session_id: uuid.UUID
    synthetic_learner_id: str
    lesson_id: str
    lesson_version: int
    lesson_title: str
    session_status: str
    finish_reason: str | None
    session_started_at: datetime
    modalities: tuple[str, ...]
    report_revision: int
    reviewer_id: str
    reviewed_at: datetime
    review_reason: str
    criteria: tuple[ExportCriterion, ...]
    evaluator_versions: tuple[str, ...]


def build_payload(data: ExportInput) -> dict[str, Any]:
    """Pure function: the same approved revision always yields the same payload."""
    objectives = [
        {
            "objective_id": c.objective_id,
            "criterion_id": c.criterion_id,
            "status": "assessed" if c.level is not None else "insufficient_evidence",
            "level": c.level,
            "level_scale": "0-3 rubric (0 incorrect, 1 partial, 2 mostly correct, 3 accurate)",
            "suggested_level": c.suggested_level,
            "teacher_changed_level": c.level != c.suggested_level,
            "misconceptions": list(c.misconception_tags),
            "evidence": [
                {
                    "turn_sequence": e.turn_sequence,
                    "quote": e.quote,
                    "assisted": e.assisted,
                    "misconception_tag": e.misconception_tag,
                }
                for e in c.evidence
            ],
        }
        for c in data.criteria
    ]
    assessed = sum(c.level is not None for c in data.criteria)
    return {
        "schema_version": SCHEMA_VERSION,
        "idempotency_key": idempotency_key(data.session_id, data.report_revision),
        "source": {"system": "kira-verbal-prototype", "disclaimer": DISCLAIMER},
        "learner": {"synthetic_learner_id": data.synthetic_learner_id},
        "activity": {
            "type": "oral_assessment",
            "session_id": str(data.session_id),
            "lesson_id": data.lesson_id,
            "lesson_version": data.lesson_version,
            "lesson_title": data.lesson_title,
            "session_status": data.session_status,
            "finish_reason": data.finish_reason,
            "started_at": data.session_started_at.isoformat(),
            "modalities": list(data.modalities),
        },
        "review": {
            "decision": "approved",
            "report_revision": data.report_revision,
            "reviewer_id": data.reviewer_id,
            "reviewed_at": data.reviewed_at.isoformat(),
            "reason": data.review_reason,
        },
        "objectives": objectives,
        "coverage": {"assessed": assessed, "total": len(data.criteria)},
        "provenance": {
            "rubric": {"lesson_id": data.lesson_id, "lesson_version": data.lesson_version},
            "evaluator_versions": list(data.evaluator_versions),
        },
    }


class MockKiraClient:
    """Records deliveries in memory, applying each idempotency key at most once.

    Stands in for a downstream receiver so the duplicate-export guarantee can be tested.
    Nothing leaves the process.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.applied: dict[str, dict[str, Any]] = {}
        self.deliveries = 0

    def deliver(self, payload: dict[str, Any]) -> bool:
        """Return True if this delivery applied a new update, False if it was a duplicate."""
        with self._lock:
            self.deliveries += 1
            key = payload["idempotency_key"]
            if key in self.applied:
                return False
            self.applied[key] = payload
            return True
