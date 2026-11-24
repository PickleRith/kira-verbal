"""API tests for /health and /ready with injected readiness checks (no services needed)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _ok() -> None:
    return None


def _fail() -> None:
    raise ConnectionError("secret-host:5432 refused")


def client(**checks) -> TestClient:
    return TestClient(create_app(Settings(), readiness_checks=checks))


def test_health_is_ok_without_dependencies():
    with client(database=_fail) as c:
        response = c.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_when_all_checks_pass():
    with client(database=_ok, redis=_ok) as c:
        response = c.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}


def test_not_ready_returns_503_without_leaking_error_details():
    with client(database=_fail, redis=_ok) as c:
        response = c.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "not_ready", "checks": {"database": "unavailable", "redis": "ok"}}
    assert "secret-host" not in response.text


def test_startup_fails_on_invalid_lesson_fixture(tmp_path: Path):
    (tmp_path / "broken.v1.json").write_text("{not json", encoding="utf-8")
    app = create_app(Settings(lessons_dir=tmp_path), readiness_checks={"x": _ok})
    with pytest.raises(Exception, match="broken.v1.json"):
        with TestClient(app):
            pass


def test_blank_optional_settings_mean_not_configured():
    """`.env.example` copied as-is has `VOICE_WORKER_SECRET=` etc.; that must not fail startup."""
    from app.config import Settings

    settings = Settings(
        _env_file=None, voice_worker_secret="", livekit_url="", llm_api_key="  key  "
    )
    assert settings.voice_worker_secret is None and not settings.voice_configured
    assert settings.llm_api_key.get_secret_value() == "key"
