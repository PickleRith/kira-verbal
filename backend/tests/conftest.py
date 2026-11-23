from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.config import REPO_ROOT
from app.domain.models import Lesson

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
