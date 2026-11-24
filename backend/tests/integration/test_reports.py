"""Teacher reports, review and export against real Postgres through the HTTP API."""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError

from app.db.models import ExportEventRow, ReportRow

pytestmark = pytest.mark.integration

GOOD_Q1 = "Plants use sunlight to make sugar from carbon dioxide and water, and release oxygen."
ROOTS_Q2 = "From the soil through its roots."
ALL_UNKNOWN = {"purpose": None, "carbon_dioxide": None, "light": None}


class Teacher:
    def __init__(self, api: TestClient) -> None:
        created = api.post("/v1/teacher/workspaces")
        assert created.status_code == 201
        self.api, self.token = api, created.json()["teacher_token"]
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def start(self, lesson: str = "photosynthesis", learner: str = "demo-ana") -> Learner:
        r = self.api.post(
            "/v1/teacher/sessions",
            json={"lesson_id": lesson, "synthetic_learner_id": learner},
            headers=self.auth,
        )
        assert r.status_code == 201, r.text
        return Learner(self.api, r.json()["session_id"], r.json()["session_token"])

    def report(self, session_id: str, expect: int = 200) -> dict:
        r = self.api.get(f"/v1/sessions/{session_id}/report", headers=self.auth)
        assert r.status_code == expect, r.text
        return r.json()

    def review(self, report_id: str, **body):
        return self.api.post(f"/v1/reports/{report_id}/review", json=body, headers=self.auth)

    def export(self, report_id: str):
        return self.api.post(f"/v1/reports/{report_id}/export", headers=self.auth)


class Learner:
    def __init__(self, api: TestClient, session_id: str, token: str) -> None:
        self.api, self.id, self.token = api, session_id, token
        self.auth = {"Authorization": f"Bearer {token}"}
        view = api.get(f"/v1/sessions/{session_id}", headers=self.auth).json()
        self.version, self.qid = view["state_version"], view["prompt"]["question_id"]

    def say(self, text_: str) -> dict:
        r = self.api.post(
            f"/v1/sessions/{self.id}/turns",
            json={
                "client_turn_id": uuid.uuid4().hex,
                "expected_state_version": self.version,
                "transcript": text_,
                "modality": "text",
                "question_id": self.qid,
            },
            headers=self.auth,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        self.version = body["state_version"]
        self.qid = body["prompt"]["question_id"] if body["prompt"] else None
        return body

    def finish(self) -> None:
        r = self.api.post(
            f"/v1/sessions/{self.id}/finish",
            json={"expected_state_version": self.version},
            headers=self.auth,
        )
        assert r.status_code == 200, r.text


def finished_report(teacher: Teacher, *answers: str) -> dict:
    learner = teacher.start()
    for answer in answers:
        learner.say(answer)
    learner.finish()
    return teacher.report(learner.id)


def levels(report: dict) -> dict:
    return {c["criterion_id"]: c["level"] for c in report["criteria"]}


# --- authorization and isolation ----------------------------------------------------


def test_only_the_owning_teacher_can_open_a_report(api: TestClient):
    owner, stranger = Teacher(api), Teacher(api)
    learner = owner.start()
    path = f"/v1/sessions/{learner.id}/report"

    assert api.get(path).status_code == 401  # no token
    assert api.get(path, headers=learner.auth).json()["error"] == "teacher_not_found"
    assert api.get(path, headers=stranger.auth).json()["error"] == "session_not_found"
    assert owner.report(learner.id)["status"] == "pending"

    # A home-page session belongs to no workspace: nobody can see its report.
    anonymous = api.post("/v1/sessions", json={"lesson_id": "photosynthesis"}).json()
    assert owner.report(anonymous["id"], expect=404)["error"] == "session_not_found"


def test_teachers_see_only_their_own_sessions(api: TestClient):
    a, b = Teacher(api), Teacher(api)
    mine = a.start(learner="demo-mine")
    b.start(learner="demo-theirs")
    listed = api.get("/v1/teacher/sessions", headers=a.auth).json()
    assert [s["session_id"] for s in listed] == [mine.id]
    assert listed[0]["report_status"] == "pending"


def test_review_and_export_of_another_workspace_report_are_404(api: TestClient):
    owner, stranger = Teacher(api), Teacher(api)
    report = finished_report(owner, GOOD_Q1)
    assert stranger.review(report["report_id"], decision="reject", reason="x").status_code == 404
    assert stranger.export(report["report_id"]).json()["error"] == "report_not_found"


# --- lifecycle and content ----------------------------------------------------------


def test_pending_preview_then_one_ready_revision(api: TestClient, seeded_engine: Engine):
    teacher = Teacher(api)
    learner = teacher.start()
    learner.say(GOOD_Q1)
    pending = teacher.report(learner.id)
    assert (pending["status"], pending["report_id"], pending["revision"]) == ("pending", None, None)
    assert levels(pending)["purpose"] == 2  # live preview of the suggestion

    learner.finish()
    first = teacher.report(learner.id)
    again = teacher.report(learner.id)
    assert (first["status"], first["revision"]) == ("ready_for_review", 1)
    assert again["report_id"] == first["report_id"]
    with seeded_engine.connect() as c:
        count = c.scalar(select(func.count()).select_from(ReportRow))
    assert count == 1


def test_report_links_exact_quotes_and_keeps_unknowns(api: TestClient):
    report = finished_report(Teacher(api), GOOD_Q1, ROOTS_Q2)
    assert report["session_status"] == "incomplete" and report["finish_reason"] == "learner_exit"
    by_id = {c["criterion_id"]: c for c in report["criteria"]}

    co2 = by_id["carbon_dioxide"]
    assert co2["suggested_level"] == 1
    assert [m["tag"] for m in co2["misconceptions"]] == ["co2_from_roots"]
    [quote] = [e for e in co2["evidence"] if e["status"] == "accepted"]
    turn = next(t for t in report["transcript"] if t["sequence"] == quote["turn_sequence"])
    assert quote["quote"] in turn["answer"]  # evidence points at what was actually said

    light = by_id["light"]
    assert light["suggested_level"] is None and light["evidence"] == []  # unknown, not zero
    assert report["coverage"] == {"with_evidence": 2, "total": 3}
    assert by_id["purpose"]["level_descriptors"]["3"].startswith("Explains the plant makes sugar")


def test_wellbeing_concern_is_flagged_for_the_teacher(api: TestClient):
    teacher = Teacher(api)
    learner = teacher.start()
    learner.say("I'm scared to go home today")
    learner.finish()
    assert teacher.report(learner.id)["wellbeing_turns"] == [1]
    [item] = api.get("/v1/teacher/sessions", headers=teacher.auth).json()
    assert item["wellbeing_flags"] == 1 and item["answer_turns"] == 0


def test_abandoned_session_times_out_when_the_teacher_opens_it(api: TestClient, clock):
    teacher = Teacher(api)
    learner = teacher.start()
    learner.say(GOOD_Q1)
    clock.advance(10_000)
    report = teacher.report(learner.id)
    assert (report["session_status"], report["finish_reason"]) == ("incomplete", "timeout")
    assert report["status"] == "ready_for_review"


# --- review -------------------------------------------------------------------------


def test_approving_unchanged_levels_needs_no_reason(api: TestClient):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1, ROOTS_Q2)
    r = teacher.review(report["report_id"], decision="approve", levels=levels(report))
    assert r.status_code == 200, r.text
    approved = r.json()
    assert (approved["status"], approved["revision"]) == ("approved", 2)
    [entry] = approved["reviews"]
    assert (entry["from_revision"], entry["to_revision"], entry["decision"]) == (1, 2, "approve")
    assert [v["status"] for v in approved["revisions"]] == ["ready_for_review", "approved"]


def test_changing_a_level_requires_a_reason(api: TestClient):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1, ROOTS_Q2)
    edited = {**levels(report), "carbon_dioxide": 2}
    r = teacher.review(report["report_id"], decision="approve", levels=edited)
    assert (r.status_code, r.json()["error"]) == (422, "invalid_review")

    r = teacher.review(
        report["report_id"],
        decision="approve",
        levels=edited,
        reason="Said 'from the air' later in class discussion.",
    )
    assert r.status_code == 200
    co2 = next(c for c in r.json()["criteria"] if c["criterion_id"] == "carbon_dioxide")
    assert (co2["suggested_level"], co2["level"]) == (1, 2)  # both kept: suggestion and decision


@pytest.mark.parametrize(
    "levels_",
    [
        {"purpose": 2, "carbon_dioxide": 1},  # missing a criterion
        {**ALL_UNKNOWN, "made_up": 1},  # unknown criterion
    ],
)
def test_levels_must_cover_exactly_the_criteria(api: TestClient, levels_):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    r = teacher.review(report["report_id"], decision="approve", levels=levels_, reason="x")
    assert r.json()["error"] == "invalid_review"


def test_level_outside_the_rubric_is_rejected(api: TestClient):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    bad = {**ALL_UNKNOWN, "purpose": 4}
    assert teacher.review(report["report_id"], decision="approve", levels=bad).status_code == 422


def test_reject_requires_a_reason_and_blocks_export(api: TestClient):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    assert teacher.review(report["report_id"], decision="reject").status_code == 422
    rejected = teacher.review(
        report["report_id"], decision="reject", reason="Answers were read aloud from notes."
    ).json()
    assert rejected["status"] == "rejected"
    r = teacher.export(rejected["report_id"])
    assert (r.status_code, r.json()["error"]) == (409, "report_not_approved")


def test_reviewing_an_old_revision_is_a_conflict(api: TestClient):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    first_id = report["report_id"]
    assert teacher.review(first_id, decision="approve", levels=levels(report)).status_code == 200
    stale = teacher.review(first_id, decision="reject", reason="second tab")
    assert (stale.status_code, stale.json()["error"]) == (409, "stale_revision")


def test_concurrent_reviews_of_one_revision_save_exactly_one(
    api: TestClient, seeded_engine: Engine
):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    barrier, results = threading.Barrier(4), []

    def go() -> None:
        barrier.wait()
        results.append(
            teacher.review(report["report_id"], decision="reject", reason="r").status_code
        )

    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 409, 409, 409]
    with seeded_engine.connect() as c:
        revisions = c.scalars(select(ReportRow.revision).order_by(ReportRow.revision)).all()
    assert revisions == [1, 2]


# --- export -------------------------------------------------------------------------


def test_only_an_approved_report_can_be_exported(api: TestClient):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    r = teacher.export(report["report_id"])
    assert (r.status_code, r.json()["error"]) == (409, "report_not_approved")


def test_export_is_idempotent_and_reaches_the_receiver_once(api: TestClient, seeded_engine: Engine):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1, ROOTS_Q2)
    approved = teacher.review(report["report_id"], decision="approve", levels=levels(report)).json()

    first = teacher.export(approved["report_id"]).json()
    second = teacher.export(approved["report_id"]).json()
    assert (first["replayed"], second["replayed"]) == (False, True)
    assert second["id"] == first["id"] and second["payload"] == first["payload"]
    with seeded_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(ExportEventRow)) == 1
    kira = api.app.state.reports.kira
    assert list(kira.applied) == [first["idempotency_key"]] and kira.deliveries == 2

    payload = first["payload"]
    assert payload["idempotency_key"] == f"kira-verbal:{report['session_id']}:rev2"
    assert "Not a Kira Learning API" in payload["source"]["disclaimer"]
    by_id = {o["criterion_id"]: o for o in payload["objectives"]}
    assert by_id["light"] == {
        **by_id["light"],
        "status": "insufficient_evidence",
        "level": None,
        "evidence": [],
    }
    assert by_id["carbon_dioxide"]["misconceptions"] == ["co2_from_roots"]
    assert by_id["carbon_dioxide"]["evidence"][0]["quote"] == ROOTS_Q2
    assert teacher.report(report["session_id"])["exports"][0]["id"] == first["id"]


def test_new_revision_needs_its_own_approval_and_export(api: TestClient):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    rev2 = teacher.review(report["report_id"], decision="approve", levels=levels(report)).json()
    exported = teacher.export(rev2["report_id"]).json()

    rev3 = teacher.review(
        rev2["report_id"],
        decision="approve",
        levels={**levels(rev2), "purpose": 3},
        reason="Re-listened to the answer.",
    ).json()
    assert rev3["revision"] == 3
    # The old export is unchanged and replays; the new revision exports separately.
    assert teacher.export(rev2["report_id"]).json()["id"] == exported["id"]
    new = teacher.export(rev3["report_id"]).json()
    assert new["idempotency_key"].endswith(":rev3") and new["id"] != exported["id"]
    assert next(o for o in new["payload"]["objectives"] if o["criterion_id"] == "purpose")[
        "teacher_changed_level"
    ]


def test_side_turns_never_reach_the_export(api: TestClient):
    teacher = Teacher(api)
    # A question back mentions roots; it is a side turn, so no evidence from it is accepted.
    report = finished_report(teacher, "What are roots for?", GOOD_Q1)
    approved = teacher.review(report["report_id"], decision="approve", levels=levels(report)).json()
    payload = teacher.export(approved["report_id"]).json()["payload"]
    quotes = [e["quote"] for o in payload["objectives"] for e in o["evidence"]]
    assert all("roots" not in q for q in quotes)


# --- audit trail is append-only -----------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE reports SET status = 'approved'",
        "DELETE FROM reports",
        "UPDATE reviews SET reason = 'rewritten'",
        "DELETE FROM reviews",
        "UPDATE export_events SET payload = '{}'",
    ],
)
def test_audit_rows_cannot_be_changed(api: TestClient, seeded_engine: Engine, statement):
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    approved = teacher.review(report["report_id"], decision="approve", levels=levels(report)).json()
    teacher.export(approved["report_id"])
    with pytest.raises(DBAPIError, match="append-only"), seeded_engine.begin() as c:
        c.execute(text(statement))


def test_deleting_a_session_still_removes_its_reports(api: TestClient, seeded_engine: Engine):
    """Retention: whole-session deletion cascades through the append-only tables."""
    teacher = Teacher(api)
    report = finished_report(teacher, GOOD_Q1)
    approved = teacher.review(report["report_id"], decision="approve", levels=levels(report)).json()
    teacher.export(approved["report_id"])
    with seeded_engine.begin() as c:
        c.execute(text("DELETE FROM sessions WHERE id = :id"), {"id": report["session_id"]})
        assert c.scalar(select(func.count()).select_from(ReportRow)) == 0
