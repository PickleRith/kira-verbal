"""The labelled cases must stay consistent with the lessons they refer to."""

import json
from collections import Counter

import pytest

from app.config import REPO_ROOT
from app.domain.policy import Signal
from app.lesson_catalog import load_catalog
from app.providers.llm import CONVERSATIONAL_INTENTS, LearnerIntent

EVALS = REPO_ROOT / "data" / "evals"
CASES = json.loads((EVALS / "evaluator_cases.v1.json").read_text("utf-8"))
CASES_V2 = json.loads((EVALS / "evaluator_cases.v2.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(REPO_ROOT / "data" / "lessons")


def test_ids_are_unique():
    ids = [case["id"] for case in CASES["cases"]]
    assert len(ids) == len(set(ids))


def test_every_required_category_is_covered():
    categories = Counter(case["category"] for case in CASES["cases"])
    for required in ("correct", "partial", "incorrect", "ambiguous", "adversarial"):
        assert categories[required] >= 2, required


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["id"])
def test_case_references_real_lesson_content(case, catalog):
    lesson = catalog.latest(case["lesson_id"])
    question = lesson.question(case["question_id"])
    expected = case["expected"]
    Signal(expected["signal"])
    tag = expected["misconception_tag"]
    if tag is not None:
        assert lesson.misconception(tag).objective == question.objective
    assert (tag is not None) == (expected["signal"] == "misconception")
    if expected["level_range"] is not None:
        low, high = expected["level_range"]
        assert 0 <= low <= high <= 3


def test_v2_keeps_every_v1_case_unchanged():
    assert CASES_V2["cases"][: len(CASES["cases"])] == CASES["cases"]
    ids = [case["id"] for case in CASES_V2["cases"]]
    assert len(ids) == len(set(ids))


def test_v2_covers_every_side_turn_intent():
    intents = {case["expected"].get("intent") for case in CASES_V2["cases"]}
    assert {i.value for i in CONVERSATIONAL_INTENTS} <= intents


@pytest.mark.parametrize("case", CASES_V2["cases"], ids=lambda c: c["id"])
def test_v2_case_is_consistent(case, catalog):
    lesson = catalog.latest(case["lesson_id"])
    question = lesson.question(case["question_id"])
    expected = case["expected"]
    signal = Signal(expected["signal"])
    tag = expected["misconception_tag"]
    if tag is not None:
        assert lesson.misconception(tag).objective == question.objective
    if "intent" in expected:
        intent = LearnerIntent(expected["intent"])
        assert (intent in CONVERSATIONAL_INTENTS) == (signal is Signal.CONVERSATION)
    if signal is Signal.CONVERSATION:
        assert expected["level_range"] is None and tag is None
