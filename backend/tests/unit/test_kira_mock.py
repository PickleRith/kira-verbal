"""The mock Kira export payload: deterministic, honest about unknowns, deduplicated."""

import uuid
from datetime import UTC, datetime

from app.providers.kira_mock import (
    SCHEMA_VERSION,
    ExportCriterion,
    ExportEvidence,
    ExportInput,
    MockKiraClient,
    build_payload,
    idempotency_key,
)

SESSION = uuid.UUID("00000000-0000-4000-8000-000000000001")
WHEN = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def data(*criteria: ExportCriterion, revision: int = 2) -> ExportInput:
    return ExportInput(
        session_id=SESSION,
        synthetic_learner_id="demo-ana",
        lesson_id="photosynthesis",
        lesson_version=1,
        lesson_title="Photosynthesis",
        session_status="completed",
        finish_reason="objectives_exhausted",
        session_started_at=WHEN,
        modalities=("text", "voice"),
        report_revision=revision,
        reviewer_id="demo-teacher",
        reviewed_at=WHEN,
        review_reason="",
        criteria=criteria,
        evaluator_versions=("anthropic:claude-haiku-5-5:evaluator-v2",),
    )


ROOTS = ExportCriterion(
    criterion_id="carbon_dioxide",
    objective_id="carbon_dioxide",
    level=2,
    suggested_level=1,
    misconception_tags=("co2_from_roots",),
    evidence=(ExportEvidence(2, "From the soil through its roots.", False, "co2_from_roots"),),
)
UNKNOWN = ExportCriterion("light", "light", None, None, (), ())


def test_payload_is_deterministic_and_keyed_by_session_and_revision():
    first, second = build_payload(data(ROOTS, UNKNOWN)), build_payload(data(ROOTS, UNKNOWN))
    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["idempotency_key"] == idempotency_key(SESSION, 2) == f"kira-verbal:{SESSION}:rev2"
    assert build_payload(data(ROOTS, revision=3))["idempotency_key"].endswith(":rev3")


def test_unknown_is_exported_as_insufficient_evidence_never_zero():
    light = build_payload(data(UNKNOWN))["objectives"][0]
    assert (light["status"], light["level"], light["evidence"]) == (
        "insufficient_evidence",
        None,
        [],
    )


def test_teacher_change_and_evidence_are_explicit():
    co2 = build_payload(data(ROOTS, UNKNOWN))["objectives"][0]
    assert (co2["suggested_level"], co2["level"], co2["teacher_changed_level"]) == (1, 2, True)
    assert co2["evidence"][0] == {
        "turn_sequence": 2,
        "quote": "From the soil through its roots.",
        "assisted": False,
        "misconception_tag": "co2_from_roots",
    }
    assert build_payload(data(ROOTS, UNKNOWN))["coverage"] == {"assessed": 1, "total": 2}


def test_payload_says_it_is_not_a_kira_api():
    payload = build_payload(data(ROOTS))
    assert "Not a Kira Learning API" in payload["source"]["disclaimer"]
    assert payload["source"]["system"] == "kira-verbal-prototype"


def test_receiver_applies_each_key_once():
    client, payload = MockKiraClient(), build_payload(data(ROOTS))
    assert client.deliver(payload) is True
    assert client.deliver(payload) is False
    assert (len(client.applied), client.deliveries) == (1, 2)
