"""HTTP contract tests: status codes, error bodies, auth, and what students can see."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

GOOD_Q1 = "Plants use sunlight to make sugar from carbon dioxide and water."


def create(api: TestClient, lesson_id: str = "photosynthesis") -> dict:
    response = api.post("/v1/sessions", json={"lesson_id": lesson_id})
    assert response.status_code == 201, response.text
    return response.json()


def auth(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_token']}"}


def turn_body(session: dict, text: str, cid: str = "t1", **overrides) -> dict:
    body = {
        "client_turn_id": cid,
        "expected_state_version": session["state_version"],
        "transcript": text,
        "modality": "text",
        "question_id": session["prompt"]["question_id"],
    }
    return body | overrides


def test_lists_published_lessons(api: TestClient):
    lessons = api.get("/v1/lessons").json()
    assert [lesson["id"] for lesson in lessons] == ["fractions", "photosynthesis", "python_loops"]
    assert all(lesson["version"] == 1 and lesson["objective_count"] == 3 for lesson in lessons)


def test_create_returns_token_and_first_question(api: TestClient):
    session = create(api)
    assert session["status"] == "awaiting_answer"
    assert session["prompt"] == {
        "question_id": "q1",
        "text": "Explain photosynthesis in your own words.",
        "purpose": "open",
        "lead_in": None,
        "hint": None,
    }
    assert len(session["session_token"]) >= 32


def test_unknown_lesson_is_404(api: TestClient):
    response = api.post("/v1/sessions", json={"lesson_id": "astrology"})
    assert response.status_code == 404
    assert response.json()["error"] == "lesson_not_found"


def test_auth_is_required_and_wrong_token_is_404(api: TestClient):
    session = create(api)
    url = f"/v1/sessions/{session['id']}"
    assert api.get(url).status_code == 401
    assert api.get(url).json()["error"] == "missing_token"
    wrong = api.get(url, headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 404 and wrong.json()["error"] == "session_not_found"
    assert api.get(url, headers=auth(session)).status_code == 200


def test_turn_retry_and_conflicts(api: TestClient):
    session = create(api)
    url = f"/v1/sessions/{session['id']}/turns"
    body = turn_body(session, GOOD_Q1)

    first = api.post(url, json=body, headers=auth(session))
    assert first.status_code == 200, first.text
    assert first.json()["prompt"]["question_id"] == "q2"

    replay = api.post(url, json=body, headers=auth(session))
    assert replay.status_code == 200 and replay.json() == first.json()

    mismatch = api.post(url, json=body | {"transcript": "different"}, headers=auth(session))
    assert mismatch.status_code == 409 and mismatch.json()["error"] == "idempotency_mismatch"

    stale = api.post(url, json=turn_body(session, "again", cid="t2"), headers=auth(session))
    assert stale.status_code == 409
    assert stale.json()["error"] == "stale_state_version"
    assert stale.json()["state_version"] == first.json()["state_version"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"transcript": "x" * 2001},
        {"modality": "telepathy"},
        {"client_turn_id": "has spaces"},
        {"grade": 3},  # unknown fields are rejected, not ignored
    ],
)
def test_invalid_turn_input_is_422(api: TestClient, overrides: dict):
    session = create(api)
    body = turn_body(session, GOOD_Q1) | overrides
    response = api.post(f"/v1/sessions/{session['id']}/turns", json=body, headers=auth(session))
    assert response.status_code == 422


def test_evaluator_outage_is_503_with_retry_after(api: TestClient, evaluator):
    session = create(api)
    evaluator.raise_next = TimeoutError("provider timeout")
    response = api.post(
        f"/v1/sessions/{session['id']}/turns",
        json=turn_body(session, GOOD_Q1),
        headers=auth(session),
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"] == "evaluation_unavailable"


def test_student_responses_never_expose_evaluation(api: TestClient):
    session = create(api)
    url = f"/v1/sessions/{session['id']}"
    body = turn_body(session, GOOD_Q1)
    api.post(f"{url}/turns", json=body, headers=auth(session))
    roots = api.post(
        f"{url}/turns",
        json=turn_body(
            session,
            "From the soil through its roots.",
            cid="t2",
            expected_state_version=3,
            question_id="q2",
        ),
        headers=auth(session),
    )
    view = api.get(url, headers=auth(session))
    for text in (roots.text, view.text):
        for forbidden in ("signal", "misconception", "co2_from_roots", "level", "evaluator"):
            assert forbidden not in text


def test_finish_then_turn_is_closed(api: TestClient):
    session = create(api)
    url = f"/v1/sessions/{session['id']}"
    finished = api.post(f"{url}/finish", json={"expected_state_version": 1}, headers=auth(session))
    assert finished.status_code == 200
    assert finished.json()["status"] == "incomplete"
    late = api.post(
        f"{url}/turns",
        json=turn_body(session, GOOD_Q1, expected_state_version=2),
        headers=auth(session),
    )
    assert late.status_code == 409 and late.json()["error"] == "session_closed"


def test_cors_allows_frontend_origin_only(api: TestClient):
    def preflight(origin: str):
        return api.options(
            "/v1/lessons",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    assert preflight("http://localhost:3000").headers.get("access-control-allow-origin") == (
        "http://localhost:3000"
    )
    assert "access-control-allow-origin" not in preflight("https://evil.example").headers
