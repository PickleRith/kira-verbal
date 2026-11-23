"""FastAPI application factory.

Startup order matters: lesson fixtures are validated first and an invalid
fixture stops the process, so we never serve sessions against broken content.
Postgres and Redis clients are created lazily (no connection at startup), so
/health works during a dependency outage and /ready reports it.

Run locally:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from sqlalchemy import text

from app.api import health
from app.config import Settings, get_settings
from app.db.session import make_engine
from app.lesson_catalog import load_catalog


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checks: Mapping[str, Callable[[], None]] | None = None,
) -> FastAPI:
    """Build the app. Tests pass `readiness_checks` to avoid real dependencies."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        catalog = load_catalog(settings.lessons_dir)  # raises -> startup fails
        app.state.settings = settings
        app.state.lesson_catalog = catalog

        engine = make_engine(settings.database_url)
        redis_client = redis.Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
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
            redis_client.close()
            engine.dispose()

    app = FastAPI(
        title="Kira Verbal API",
        version="0.1.0",
        description="Independent portfolio prototype. Synthetic data only.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    return app


app = create_app()
