from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

# Tests must never depend on the developer's .env, and must never make paid API calls or
# reach LiveKit. Environment variables override .env values in pydantic-settings, so pin
# the providers to fake and blank every credential (blank means "not configured").
# This runs at import time, before any test builds a Settings object.
for _name, _value in {
    "EVALUATOR_PROVIDER": "fake",
    "RATE_LIMIT_ENABLED": "false",  # limits are tested explicitly in test_limits.py
    "RESPONDER_PROVIDER": "fake",
    "LLM_API_KEY": "",
    "LIVEKIT_URL": "",
    "LIVEKIT_API_KEY": "",
    "LIVEKIT_API_SECRET": "",
    "VOICE_WORKER_SECRET": "",
}.items():
    os.environ[_name] = _value

import pytest  # noqa: E402

from app.config import REPO_ROOT  # noqa: E402
from app.domain.models import Lesson  # noqa: E402

LESSONS_DIR = REPO_ROOT / "data" / "lessons"


@pytest.fixture
def lessons_dir() -> Path:
    return LESSONS_DIR


@pytest.fixture
def photosynthesis_raw() -> dict[str, Any]:
    """A mutable deep copy of the real fixture, for building invalid variants."""
    raw = json.loads((LESSONS_DIR / "photosynthesis.v1.json").read_text(encoding="utf-8"))
    return copy.deepcopy(raw)


@pytest.fixture
def photosynthesis(photosynthesis_raw: dict[str, Any]) -> Lesson:
    return Lesson.model_validate(photosynthesis_raw)
