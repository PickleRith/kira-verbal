"""Fixtures for tests against real Postgres/Redis from compose.yaml.

They use a throwaway `kira_test` database (recreated per test session) so they
never modify your development data. If services are unreachable these tests are
skipped with a clear reason, unless REQUIRE_SERVICES=1 (set in CI), in which case
they fail: a missing dependency must not silently look like a pass there.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import redis
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import REPO_ROOT, Settings
from app.lesson_catalog import load_catalog
from app.main import create_app
from app.providers.fake import FakeEvaluator
from app.providers.llm import EvaluationRequest, EvaluatorOutput
from app.repositories.lessons import publish_lesson
from app.services.assessment import AssessmentConfig, AssessmentService
from app.services.lessons import LessonStore

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://kira:kira@127.0.0.1:5432/kira_test"
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
REQUIRE_SERVICES = os.environ.get("REQUIRE_SERVICES") == "1"


def _unavailable(reason: str) -> None:
    if REQUIRE_SERVICES:
        pytest.fail(f"REQUIRE_SERVICES=1 but {reason}")
    pytest.skip(f"{reason} (run `docker compose up -d`)")


def alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},  # fail fast instead of hanging when down
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    except Exception as exc:  # noqa: BLE001 - any connection error means unavailable
        admin.dispose()
        _unavailable(f"Postgres unreachable at {url.host}:{url.port}: {type(exc).__name__}")
    admin.dispose()
    yield TEST_DATABASE_URL


@pytest.fixture(scope="session")
def alembic_cfg(database_url: str) -> Config:
    return alembic_config(database_url)


@pytest.fixture(scope="session")
def migrated_engine(database_url: str, alembic_cfg: Config) -> Iterator[Engine]:
    command.upgrade(alembic_cfg, "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


def truncate_all(engine: Engine) -> None:
    """Start each test from empty tables, whatever earlier tests committed."""
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE turns, sessions, workspaces, lesson_versions CASCADE"))


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test."""
    truncate_all(migrated_engine)
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def seeded_engine(migrated_engine: Engine) -> Engine:
    """Empty tables plus the three published demo lessons (committed)."""
    truncate_all(migrated_engine)
    with sessionmaker(bind=migrated_engine).begin() as db:
        for lesson in load_catalog(REPO_ROOT / "data" / "lessons"):
            publish_lesson(db, lesson)
    return migrated_engine


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class SimulatedCrash(BaseException):
    """BaseException so the service's `except Exception` cannot catch it: models a process
    dying mid-request, leaving the processing claim behind."""


class ControllableEvaluator:
    """The real FakeEvaluator, plus hooks to block, fail, delay or crash on demand."""

    def __init__(self) -> None:
        self.inner = FakeEvaluator()
        self.calls = 0
        self.entered = threading.Event()  # set when evaluate() starts
        self.gate: threading.Event | None = None  # if set, evaluate() waits for it
        self.raise_next: BaseException | None = None
        self.delay_seconds = 0.0
        self.override: EvaluatorOutput | None = None  # return this instead of evaluating

    def evaluate(self, request: EvaluationRequest) -> EvaluatorOutput:
        self.calls += 1
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(timeout=10)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.raise_next is not None:
            exc, self.raise_next = self.raise_next, None
            raise exc
        if self.override is not None:
            return self.override
        return self.inner.evaluate(request)


@pytest.fixture
def simulated_crash() -> type[SimulatedCrash]:
    return SimulatedCrash


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def evaluator() -> ControllableEvaluator:
    return ControllableEvaluator()


@pytest.fixture
def service(
    seeded_engine: Engine, clock: FakeClock, evaluator: ControllableEvaluator
) -> Iterator[AssessmentService]:
    factory = sessionmaker(bind=seeded_engine, expire_on_commit=False)
    executor = ThreadPoolExecutor(max_workers=8)
    yield AssessmentService(
        factory,
        LessonStore(factory),
        evaluator,
        executor,
        AssessmentConfig(evaluator_timeout_seconds=1.0, processing_lease_seconds=30),
        clock=clock,
    )
    executor.shutdown(wait=False, cancel_futures=True)


@pytest.fixture
def api(
    seeded_engine: Engine, database_url: str, clock: FakeClock, evaluator: ControllableEvaluator
) -> Iterator[TestClient]:
    settings = Settings(database_url=database_url, evaluator_timeout_seconds=1.0)
    app = create_app(settings, readiness_checks={"ok": lambda: None}, evaluator=evaluator)
    with TestClient(app) as client:
        app.state.assessment.clock = clock
        yield client


@pytest.fixture(scope="session")
def redis_url() -> str:
    client = redis.Redis.from_url(TEST_REDIS_URL, socket_connect_timeout=2)
    try:
        client.ping()
    except redis.RedisError as exc:
        _unavailable(f"Redis unreachable: {type(exc).__name__}")
    finally:
        client.close()
    return TEST_REDIS_URL
