"""Fixtures for tests against real Postgres/Redis from compose.yaml.

They use a throwaway `kira_test` database (recreated per test session) so they
never modify your development data. If services are unreachable these tests are
skipped with a clear reason, unless REQUIRE_SERVICES=1 (set in CI), in which case
they fail: a missing dependency must not silently look like a pass there.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import redis
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import REPO_ROOT

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


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test."""
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


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
