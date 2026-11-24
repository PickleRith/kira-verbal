"""Rate limits and request-size cap, against real Redis (test database 15)."""

from __future__ import annotations

import pytest
import redis as redis_lib
from fastapi.testclient import TestClient

from app.api.limits import LimitConfig, classify
from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def limited_api(seeded_engine, database_url, redis_url, evaluator):
    client = redis_lib.Redis.from_url(redis_url)
    client.flushdb()
    client.close()
    settings = Settings(
        database_url=database_url,
        redis_url=redis_url,
        evaluator_timeout_seconds=1.0,
        rate_limit_enabled=True,
        rate_limit_create_per_minute=3,
        rate_limit_turns_per_minute=2,
        rate_limit_requests_per_minute=5,
        max_body_bytes=2000,
    )
    app = create_app(settings, readiness_checks={"ok": lambda: None}, evaluator=evaluator)
    with TestClient(app) as api:
        yield api


def test_classify_buckets():
    config = LimitConfig()
    sid = "0f8fad5b-d9cb-469f-a165-70867728950e"
    assert classify("POST", "/v1/sessions", "1.2.3.4", config) == ("create:1.2.3.4", 30)
    assert classify("POST", f"/v1/sessions/{sid}/turns", "1.2.3.4", config) == (f"turn:{sid}", 40)
    assert classify("GET", f"/v1/sessions/{sid}", "1.2.3.4", config) == ("default:1.2.3.4", 600)
    assert classify("GET", "/health", "1.2.3.4", config) is None
    assert classify("OPTIONS", "/v1/sessions", "1.2.3.4", config) is None
    assert classify("POST", "/v1/auth/login", "1.2.3.4", config) == ("auth:1.2.3.4", 10)
    assert classify("POST", "/v1/me/sessions", "1.2.3.4", config) == ("create:1.2.3.4", 30)


def test_session_creation_is_limited_per_client(limited_api: TestClient):
    codes = [
        limited_api.post("/v1/sessions", json={"lesson_id": "photosynthesis"}).status_code
        for _ in range(4)
    ]
    assert codes == [201, 201, 201, 429]
    blocked = limited_api.post("/v1/sessions", json={"lesson_id": "photosynthesis"})
    assert blocked.json()["error"] == "rate_limited"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 61
    # Health checks are never limited.
    assert all(limited_api.get("/health").status_code == 200 for _ in range(10))


def test_turns_are_limited_per_session_not_per_client(limited_api: TestClient):
    def start():
        s = limited_api.post("/v1/sessions", json={"lesson_id": "photosynthesis"}).json()
        return s, {"Authorization": f"Bearer {s['session_token']}"}

    def turn(s, auth, n, version):
        return limited_api.post(
            f"/v1/sessions/{s['id']}/turns",
            headers=auth,
            json={
                "client_turn_id": f"t{n}",
                "expected_state_version": version,
                "transcript": "I don't know",
                "modality": "text",
                "question_id": "q1",
            },
        )

    first, first_auth = start()
    r1 = turn(first, first_auth, 1, 1)
    r2 = turn(first, first_auth, 2, r1.json()["state_version"])
    r3 = turn(first, first_auth, 3, r2.json()["state_version"])
    assert [r1.status_code, r2.status_code, r3.status_code] == [200, 200, 429]
    # A different session from the same client is unaffected.
    other, other_auth = start()
    assert turn(other, other_auth, 1, 1).status_code == 200


def test_oversized_body_is_rejected_before_parsing(limited_api: TestClient):
    r = limited_api.post("/v1/sessions", json={"lesson_id": "x" * 5000})
    assert (r.status_code, r.json()["error"]) == (413, "payload_too_large")


def test_limiter_fails_open_when_redis_is_down(seeded_engine, database_url, evaluator):
    settings = Settings(
        database_url=database_url,
        redis_url="redis://127.0.0.1:1/0",  # nothing listens here
        rate_limit_enabled=True,
        rate_limit_create_per_minute=1,
    )
    app = create_app(settings, readiness_checks={"ok": lambda: None}, evaluator=evaluator)
    with TestClient(app) as api:
        codes = [
            api.post("/v1/sessions", json={"lesson_id": "photosynthesis"}).status_code
            for _ in range(3)
        ]
    assert codes == [201, 201, 201]
