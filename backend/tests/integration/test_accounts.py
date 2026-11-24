"""Accounts: registration, sign-in, classes, and a student's check-in reaching the teacher."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker
from test_reports import GOOD_Q1, ROOTS_Q2, Learner  # same folder

from app.db.models import AuthTokenRow, UserRow, WorkspaceRow
from app.purge import purge
from app.services.accounts import hash_password, verify_password

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery"


def register(api: TestClient, role: str, email: str, **extra) -> dict:
    body = {
        "email": email,
        "password": PASSWORD,
        "display_name": f"{role} {email[:3]}",
        "role": role,
    }
    r = api.post("/v1/auth/register", json={**body, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def teacher_and_student(api: TestClient) -> tuple[dict, dict]:
    teacher = register(api, "teacher", "ms.rivera@example.test", class_name="Period 3 Science")
    code = teacher["user"]["class"]["join_code"]
    student = register(api, "student", "sam@example.test", join_code=code.lower())
    return teacher, student


# --- passwords --------------------------------------------------------------------------


def test_password_hash_round_trip_and_salt():
    first, second = hash_password("pw-123456"), hash_password("pw-123456")
    assert first != second  # random salt
    assert "pw-123456" not in first
    assert verify_password("pw-123456", first)
    assert not verify_password("pw-1234567", first)
    assert not verify_password("pw-123456", "garbage")


# --- registration and sign-in -----------------------------------------------------------


def test_teacher_registration_creates_a_class_with_a_join_code(api: TestClient):
    teacher = register(api, "teacher", "t@example.test", class_name="Period 3 Science")
    klass = teacher["user"]["class"]
    assert teacher["token"].startswith("kvu_")
    assert teacher["user"]["role"] == "teacher"
    assert klass["name"] == "Period 3 Science"
    assert len(klass["join_code"]) == 6 and klass["student_count"] == 0


def test_student_joins_with_code_and_never_sees_it(api: TestClient):
    teacher, student = teacher_and_student(api)
    klass = student["user"]["class"]
    assert klass["id"] == teacher["user"]["class"]["id"]
    assert klass["join_code"] is None  # only the teacher sees the code
    assert klass["teacher_name"] == teacher["user"]["display_name"]
    me = api.get("/v1/me", headers=auth(teacher["token"])).json()
    assert me["class"]["student_count"] == 1


def test_registration_validation(api: TestClient):
    base = {"password": PASSWORD, "display_name": "A", "role": "student"}
    assert api.post("/v1/auth/register", json={**base, "email": "nope"}).status_code == 422
    short = {**base, "email": "a@example.test", "password": "short"}
    assert api.post("/v1/auth/register", json=short).status_code == 422
    blank = {**base, "email": "a@example.test", "display_name": "   "}
    assert api.post("/v1/auth/register", json=blank).status_code == 422
    bad_code = api.post(
        "/v1/auth/register", json={**base, "email": "a@example.test", "join_code": "ZZZZZZ"}
    )
    assert bad_code.status_code == 404 and bad_code.json()["error"] == "class_not_found"


def test_email_is_unique_case_insensitively(api: TestClient):
    register(api, "student", "Case@Example.test")
    r = api.post(
        "/v1/auth/register",
        json={
            "email": "case@example.TEST",
            "password": PASSWORD,
            "display_name": "B",
            "role": "student",
        },
    )
    assert r.status_code == 409 and r.json()["error"] == "email_taken"


def test_login_logout_and_uniform_errors(api: TestClient, seeded_engine: Engine):
    register(api, "student", "lee@example.test")
    ok = api.post("/v1/auth/login", json={"email": " LEE@example.test ", "password": PASSWORD})
    assert ok.status_code == 200
    token = ok.json()["token"]
    assert api.get("/v1/me", headers=auth(token)).json()["email"] == "lee@example.test"

    wrong_pw = api.post("/v1/auth/login", json={"email": "lee@example.test", "password": "x" * 9})
    no_user = api.post("/v1/auth/login", json={"email": "who@example.test", "password": "x" * 9})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()  # doesn't reveal which accounts exist

    # Only hashes are stored.
    with sessionmaker(bind=seeded_engine).begin() as db:
        user = db.scalar(select(UserRow).where(UserRow.email == "lee@example.test"))
        assert user is not None and PASSWORD not in user.password_hash
        assert db.get(AuthTokenRow, token) is None

    assert api.post("/v1/auth/logout", headers=auth(token)).status_code == 204
    signed_out = api.get("/v1/me", headers=auth(token))
    assert signed_out.status_code == 401 and signed_out.json()["error"] == "not_signed_in"


def test_tokens_expire(api: TestClient, clock):
    token = register(api, "student", "exp@example.test")["token"]
    clock.advance(8 * 24 * 3600)
    assert api.get("/v1/me", headers=auth(token)).status_code == 401


# --- the student -> teacher flow ---------------------------------------------------------


def test_student_check_in_lands_in_teacher_review_queue(api: TestClient):
    teacher, student = teacher_and_student(api)
    started = api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(student["token"])
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["id"]
    assert started.json()["prompt"] is not None

    queue = api.get("/v1/teacher/sessions", headers=auth(teacher["token"])).json()
    assert [s["session_id"] for s in queue] == [session_id]
    assert queue[0]["learner_name"] == student["user"]["display_name"]
    assert queue[0]["report_status"] == "pending"
    assert queue[0]["synthetic_learner_id"].startswith("user-")  # no email or name
    assert queue[0]["score"] is None  # no score while the student is answering

    learner = Learner(api, session_id, started.json()["session_token"])
    learner.say(GOOD_Q1)
    learner.say(ROOTS_Q2)
    learner.finish()

    report = api.get(f"/v1/sessions/{session_id}/report", headers=auth(teacher["token"])).json()
    assert report["status"] == "ready_for_review"
    assert report["learner_name"] == student["user"]["display_name"]
    assert [t["answer"] for t in report["transcript"]][:2] == [GOOD_Q1, ROOTS_Q2]
    suggested = {c["criterion_id"]: c["suggested_level"] for c in report["criteria"]}
    assert report["score"] == report["suggested_score"]  # revision 1 holds the suggestion
    assert report["score"]["total"] == 3
    assert report["score"]["assessed"] == sum(v is not None for v in suggested.values())
    queue = api.get("/v1/teacher/sessions", headers=auth(teacher["token"])).json()
    assert queue[0]["score"] == report["score"]

    mine = api.get("/v1/me/sessions", headers=auth(student["token"])).json()
    assert mine[0]["session_id"] == session_id
    assert mine[0]["review_status"] == "awaiting_review"
    assert mine[0]["answers"] == 2
    assert mine[0]["result"] is None  # nothing before the teacher approves

    # The teacher sets every level and approves: 3 + 1 + 2 = 6 of 9 -> 67%, proficient.
    review = api.post(
        f"/v1/reports/{report['report_id']}/review",
        json={
            "decision": "approve",
            "levels": {"purpose": 3, "carbon_dioxide": 1, "light": 2},
            "reason": "Set light from the follow-up discussion.",
        },
        headers=auth(teacher["token"]),
    )
    assert review.status_code == 200, review.text
    expected = {
        "points": 6,
        "max_points": 9,
        "percent": 67,
        "assessed": 3,
        "total": 3,
        "band": "proficient",
    }
    assert review.json()["score"] == expected
    assert review.json()["suggested_score"] == report["suggested_score"]

    mine = api.get("/v1/me/sessions", headers=auth(student["token"])).json()
    assert mine[0]["review_status"] == "reviewed"
    result = mine[0]["result"]
    assert result["score"] == expected
    co2 = next(c for c in result["criteria"] if c["criterion_id"] == "carbon_dioxide")
    assert co2["level"] == 1 and co2["max_level"] == 3 and co2["descriptor"]
    # Only the teacher's decision reaches the student: no evidence, quotes or reasons.
    assert "evidence" not in str(result) and "follow-up discussion" not in str(mine)


def test_rejected_check_in_has_no_result(api: TestClient):
    teacher, student = teacher_and_student(api)
    started = api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(student["token"])
    ).json()
    learner = Learner(api, started["id"], started["session_token"])
    learner.say(GOOD_Q1)
    learner.finish()
    report = api.get(f"/v1/sessions/{started['id']}/report", headers=auth(teacher["token"]))
    r = api.post(
        f"/v1/reports/{report.json()['report_id']}/review",
        json={"decision": "reject", "reason": "Redo in class."},
        headers=auth(teacher["token"]),
    )
    assert r.status_code == 200
    mine = api.get("/v1/me/sessions", headers=auth(student["token"])).json()
    assert mine[0]["review_status"] == "reviewed" and mine[0]["result"] is None


def test_student_needs_a_class_to_start_and_can_join_later(api: TestClient):
    teacher = register(api, "teacher", "t2@example.test")
    student = register(api, "student", "late@example.test")
    assert student["user"]["class"] is None
    r = api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(student["token"])
    )
    assert r.status_code == 409 and r.json()["error"] == "no_class"

    code = teacher["user"]["class"]["join_code"]
    joined = api.post(
        "/v1/me/class", json={"join_code": f"{code[:3]}-{code[3:]}"}, headers=auth(student["token"])
    )
    assert joined.status_code == 200 and joined.json()["class"]["name"].startswith("teacher")
    r = api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(student["token"])
    )
    assert r.status_code == 201


def test_roles_are_enforced(api: TestClient):
    teacher, student = teacher_and_student(api)
    # A student token can't open teacher routes...
    r = api.get("/v1/teacher/sessions", headers=auth(student["token"]))
    assert r.status_code == 401 and r.json()["error"] == "teacher_not_found"
    # ...and a teacher can't start student check-ins or join a class.
    r = api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(teacher["token"])
    )
    assert r.status_code == 403 and r.json()["error"] == "wrong_role"
    r = api.post("/v1/me/class", json={"join_code": "ABCDEF"}, headers=auth(teacher["token"]))
    assert r.status_code == 403


def test_teachers_only_see_their_own_class(api: TestClient):
    teacher, student = teacher_and_student(api)
    other = register(api, "teacher", "other@example.test")
    started = api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(student["token"])
    ).json()
    assert api.get("/v1/teacher/sessions", headers=auth(other["token"])).json() == []
    r = api.get(f"/v1/sessions/{started['id']}/report", headers=auth(other["token"]))
    assert r.status_code == 404


def test_resume_rotates_the_session_token(api: TestClient):
    _, student = teacher_and_student(api)
    started = api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(student["token"])
    ).json()
    old = started["session_token"]
    r = api.post(f"/v1/me/sessions/{started['id']}/resume", headers=auth(student["token"]))
    assert r.status_code == 200
    new = r.json()["session_token"]
    assert api.get(f"/v1/sessions/{started['id']}", headers=auth(new)).status_code == 200
    assert api.get(f"/v1/sessions/{started['id']}", headers=auth(old)).status_code == 404

    # Someone else's session (or an unknown id) is indistinguishable: 404.
    intruder = register(api, "student", "intruder@example.test")
    for sid in (started["id"], str(uuid.uuid4())):
        r = api.post(f"/v1/me/sessions/{sid}/resume", headers=auth(intruder["token"]))
        assert r.status_code == 404


def test_demo_classroom_tokens_still_work(api: TestClient):
    created = api.post("/v1/teacher/workspaces").json()
    assert api.get("/v1/teacher/sessions", headers=auth(created["teacher_token"])).json() == []


def test_purge_removes_old_check_ins_but_keeps_accounts_and_classes(api, seeded_engine, clock):
    teacher, student = teacher_and_student(api)
    api.post(
        "/v1/me/sessions", json={"lesson_id": "photosynthesis"}, headers=auth(student["token"])
    )
    factory = sessionmaker(bind=seeded_engine)
    assert purge(factory, older_than_days=7, now=clock() + timedelta(days=30)) == (1, 0)
    with factory.begin() as db:
        assert db.scalar(select(WorkspaceRow.id)) is not None
        assert len(list(db.scalars(select(UserRow.id)))) == 2
