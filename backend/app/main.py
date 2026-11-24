"""FastAPI application factory.

Startup order matters: lesson fixtures are validated first and an invalid
fixture stops the process, so we never serve sessions against broken content.
Postgres and Redis clients are created lazily (no connection at startup), so
/health works during a dependency outage and /ready reports it.

Run locally:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import accounts, health, sessions, teacher
from app.api.errors import register_error_handlers
from app.api.limits import LimitConfig, RequestLimitsMiddleware
from app.config import Settings, get_settings
from app.db.session import make_engine, make_session_factory
from app.lesson_catalog import load_catalog
from app.providers.fake import FakeEvaluator
from app.providers.llm import AnthropicEvaluator, Evaluator, build_anthropic_client
from app.providers.responder import AnthropicResponder, FakeResponder, Responder
from app.services.accounts import AccountService
from app.services.assessment import AssessmentConfig, AssessmentService
from app.services.lessons import LessonStore
from app.services.reports import ReportService


def configure_logging() -> None:
    """Uvicorn configures only its own loggers; give ours a handler so INFO lines (turn
    timing) appear. Our log lines never contain learner transcripts."""
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)


def build_evaluator(settings: Settings) -> Evaluator:
    if settings.evaluator_provider == "fake":
        return FakeEvaluator()
    client = build_anthropic_client(
        api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    return AnthropicEvaluator(client, model=settings.llm_model, effort=settings.llm_effort)


def build_responder(settings: Settings) -> Responder:
    if settings.responder_provider == "fake":
        return FakeResponder()
    # Its own client: one attempt, bounded by the responder timeout. A slow or failed reply
    # falls back to the template, so retrying would only add latency.
    client = build_anthropic_client(
        api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
        timeout_seconds=settings.responder_timeout_seconds,
        max_retries=0,
    )
    return AnthropicResponder(
        client, model=settings.responder_model, effort=settings.responder_effort
    )


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checks: Mapping[str, Callable[[], None]] | None = None,
    evaluator: Evaluator | None = None,
    responder: Responder | None = None,
) -> FastAPI:
    """Build the app. Tests inject `readiness_checks`, `evaluator` and `responder`."""
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        catalog = load_catalog(settings.lessons_dir)  # raises -> startup fails
        app.state.settings = settings
        app.state.lesson_catalog = catalog

        engine = make_engine(settings.database_url)
        session_factory = make_session_factory(engine)
        redis_client = redis.Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        )
        app.state.redis = redis_client  # used by the rate limiter
        executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="evaluator")

        lesson_store = LessonStore(session_factory)
        app.state.lesson_store = lesson_store
        app.state.assessment = AssessmentService(
            session_factory,
            lesson_store,
            evaluator or build_evaluator(settings),
            executor,
            AssessmentConfig(
                max_turns=settings.max_turns,
                session_max_seconds=settings.session_max_seconds,
                deadline_grace_seconds=settings.deadline_grace_seconds,
                processing_lease_seconds=settings.processing_lease_seconds,
                evaluator_timeout_seconds=settings.evaluator_timeout_seconds,
                responder_timeout_seconds=settings.responder_timeout_seconds,
                responder_scope=settings.responder_scope,
                max_side_turns=settings.max_side_turns,
            ),
            voice_secret=(
                settings.voice_worker_secret.get_secret_value()
                if settings.voice_worker_secret
                else None
            ),
            responder=responder or build_responder(settings),
        )
        app.state.accounts = AccountService(session_factory, app.state.assessment)
        app.state.reports = ReportService(
            session_factory, app.state.assessment, accounts=app.state.accounts
        )

        def check_database() -> None:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

        def check_redis() -> None:
            if not redis_client.ping():
                raise RuntimeError("redis ping returned false")

        def check_lessons() -> None:
            if len(catalog) == 0:
                raise RuntimeError("no lessons loaded")

        app.state.readiness_checks = readiness_checks or {
            "database": check_database,
            "redis": check_redis,
            "lessons": check_lessons,
        }
        try:
            yield
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            redis_client.close()
            engine.dispose()

    app = FastAPI(
        title="Kira Verbal API",
        version="0.2.0",
        description="Independent portfolio prototype. Synthetic data only.",
        lifespan=lifespan,
    )
    # Added before CORS so CORS stays outermost: a 429/413 still carries CORS headers and
    # the browser can read the error.
    app.add_middleware(
        RequestLimitsMiddleware,
        config=LimitConfig(
            enabled=settings.rate_limit_enabled,
            create_per_minute=settings.rate_limit_create_per_minute,
            turns_per_minute=settings.rate_limit_turns_per_minute,
            requests_per_minute=settings.rate_limit_requests_per_minute,
            auth_per_minute=settings.rate_limit_auth_per_minute,
            max_body_bytes=settings.max_body_bytes,
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(teacher.router)
    app.include_router(accounts.router)
    return app


app = create_app()
