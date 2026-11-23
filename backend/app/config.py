"""Environment configuration.

Settings come from environment variables, falling back to a `.env` file at the
repository root or in `backend/`. Provider keys are `SecretStr` so they are not
printed if settings are logged by mistake. Fake mode requires none of them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True
    evaluator_provider: Literal["fake", "llm"] = "fake"

    # 127.0.0.1, not "localhost": on Windows "localhost" resolves to IPv6 ::1 first,
    # where Docker's 127.0.0.1-only port binding does not listen, so every connection
    # stalls until a timeout before falling back to IPv4.
    database_url: str = "postgresql+psycopg://kira:kira@127.0.0.1:5432/kira"
    redis_url: str = "redis://127.0.0.1:6379/0"
    frontend_origin: str = "http://localhost:3000"
    lessons_dir: Path = REPO_ROOT / "data" / "lessons"

    session_max_seconds: int = 300
    transcript_retention_days: int = 7

    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    livekit_url: str | None = None
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
