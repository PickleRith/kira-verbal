"""Environment configuration.

Settings come from environment variables, falling back to a `.env` file at the
repository root or in `backend/`. Provider keys are `SecretStr` so they are not
printed if settings are logged by mistake. Fake mode requires none of them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
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
    # Comma-separated CORS allowlist. Both spellings: browsers treat them as different origins.
    frontend_origin: str = "http://localhost:3000,http://127.0.0.1:3000"
    lessons_dir: Path = REPO_ROOT / "data" / "lessons"

    session_max_seconds: int = 300
    # Extra time after the policy's time budget before an idle session is marked incomplete.
    deadline_grace_seconds: int = 60
    max_turns: int = 5
    # How long a turn may sit in "evaluating" before another request may recover it.
    # Must exceed evaluator_timeout_seconds (checked below).
    processing_lease_seconds: int = 60
    # Wall-clock cap on one evaluator call, including the SDK's own retries.
    evaluator_timeout_seconds: float = 45.0
    # Sessions older than this are deleted by `python -m app.purge` (run it on a schedule).
    transcript_retention_days: int = 7

    # Request limits (app/api/limits.py). Per minute; the limiter fails open if Redis is down.
    rate_limit_enabled: bool = True
    rate_limit_create_per_minute: int = 30  # new sessions / classrooms, per client IP
    rate_limit_turns_per_minute: int = 40  # answers, per session
    rate_limit_requests_per_minute: int = 600  # everything else, per client IP
    rate_limit_auth_per_minute: int = 10  # sign-in / registration attempts, per client IP
    max_body_bytes: int = 16_384

    llm_api_key: SecretStr | None = None  # optional: the SDK also reads ANTHROPIC_API_KEY
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_timeout_seconds: float = 20.0  # per HTTP attempt
    llm_max_retries: int = 1  # SDK retries (connection errors, 429, 5xx)
    # Conversation layer: the line said before each question. "fake" = fixed templates.
    # "llm" = Claude writes it, checked by deterministic guardrails, template on any problem.
    responder_provider: Literal["fake", "llm"] = "fake"
    # A fast model: this call is on the learner's critical path (one per turn).
    responder_model: str = "claude-haiku-5-5"
    responder_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    responder_timeout_seconds: float = 5.0  # then the template is used; never fails a turn
    # side_turns = call the responder only for side turns and "say more" prompts (faster:
    # most turns then make one model call, not two). all = also for every new question.
    responder_scope: Literal["side_turns", "all"] = "side_turns"
    # Side turns (questions about the topic, "say that again", off topic) per session that
    # use no answer budget. Past this they count as turns.
    max_side_turns: int = 4
    # Voice (Day 4). LiveKit Cloud credentials; STT/TTS go through LiveKit Inference, so no
    # separate speech-provider keys are needed.
    livekit_url: str | None = None
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None
    # HMAC key for the per-session credential the voice worker uses to call this API.
    voice_worker_secret: SecretStr | None = None
    voice_agent_name: str = "kira-verbal-voice"
    voice_token_ttl_seconds: int = 600  # how long the browser's room token can be used to join
    # Worker side
    kira_api_url: str = "http://127.0.0.1:8000"
    voice_stt_model: str = "assemblyai/assemblyai-stt-3-7-realtime-agent"
    voice_tts_model: str = "fishaudio/s2.1-pro"
    voice_tts_voice: str = "fa4c9eb3dccc4806b382b40d61c6b10a"
    voice_user_away_seconds: float = 20.0
    # Run each voice job in its own process. LiveKit defaults to threads on Windows, but two
    # overlapping jobs then share the native audio library, and its resampler (soxr) crashed
    # the worker with "Assertion failed: LSX_FFT_BR == NULL" on 2026-11-23. "thread" is the
    # fallback if process spawning fails on a particular Windows Python build.
    voice_job_executor: Literal["process", "thread"] = "process"
    # Unused: kept so old .env files still parse. Plan originally named these providers.
    deepgram_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str | None = None

    @property
    def voice_configured(self) -> bool:
        return bool(
            self.livekit_url
            and self.livekit_api_key
            and self.livekit_api_secret
            and self.voice_worker_secret
        )

    @field_validator(
        "llm_api_key",
        "livekit_url",
        "livekit_api_key",
        "livekit_api_secret",
        "voice_worker_secret",
        "deepgram_api_key",
        "elevenlabs_api_key",
        "elevenlabs_voice_id",
        mode="before",
    )
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        # `.env.example` lists these as `KEY=` with no value; that means "not configured".
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("database_url", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: object) -> object:
        # Hosting providers (e.g. Render) hand out postgres:// or postgresql:// URLs, which
        # SQLAlchemy maps to psycopg2. This project installs psycopg 3, so name it explicitly.
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @model_validator(mode="after")
    def _voice_secret_is_strong(self) -> Settings:
        secret = self.voice_worker_secret
        if secret is not None and len(secret.get_secret_value()) < 32:
            raise ValueError("VOICE_WORKER_SECRET must be at least 32 characters")
        return self

    @model_validator(mode="after")
    def _timeouts_are_consistent(self) -> Settings:
        if (
            self.processing_lease_seconds
            <= self.evaluator_timeout_seconds + self.responder_timeout_seconds
        ):
            raise ValueError(
                "PROCESSING_LEASE_SECONDS must exceed "
                "EVALUATOR_TIMEOUT_SECONDS + RESPONDER_TIMEOUT_SECONDS"
            )
        if self.evaluator_provider == "llm":
            worst_case = self.llm_timeout_seconds * (self.llm_max_retries + 1)
            if self.evaluator_timeout_seconds < worst_case:
                raise ValueError(
                    "EVALUATOR_TIMEOUT_SECONDS must be at least "
                    "LLM_TIMEOUT_SECONDS * (LLM_MAX_RETRIES + 1)"
                )
        return self

    @property
    def frontend_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
