import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.errors import UnknownQuestionError
from app.domain.models import Lesson
from app.lesson_catalog import LessonFixtureError, content_hash, load_catalog


def test_all_shipped_fixtures_are_valid(lessons_dir: Path):
    catalog = load_catalog(lessons_dir)
    assert {lesson.id for lesson in catalog} == {"photosynthesis", "fractions", "python_loops"}
    for lesson in catalog:
        assert 2 <= len(lesson.objectives) <= 4


def test_lookup_of_unknown_question_raises(photosynthesis: Lesson):
    with pytest.raises(UnknownQuestionError):
        photosynthesis.question("nope")


def test_lessons_are_immutable_in_memory(photosynthesis: Lesson):
    with pytest.raises(ValidationError):
        photosynthesis.title = "changed"  # type: ignore[misc]


def test_content_hash_is_stable_and_sensitive(photosynthesis_raw: dict[str, Any]):
    a = Lesson.model_validate(photosynthesis_raw)
    b = Lesson.model_validate(photosynthesis_raw)
    assert content_hash(a) == content_hash(b)
    photosynthesis_raw["title"] = "Photosynthesis!"
    assert content_hash(Lesson.model_validate(photosynthesis_raw)) != content_hash(a)


def _break(raw: dict[str, Any], mutation: str) -> dict[str, Any]:
    q = {q["id"]: q for q in raw["questions"]}
    if mutation == "duplicate_question_id":
        q["q4"]["id"] = "q1"
    elif mutation == "question_unknown_objective":
        q["q1"]["objective"] = "gravity"
    elif mutation == "diagnostic_undeclared_tag":
        q["q3"]["targets_misconception"] = "unicorns"
    elif mutation == "diagnostic_without_target":
        del q["q3"]["targets_misconception"]
    elif mutation == "open_with_target":
        q["q1"]["targets_misconception"] = "food_from_soil"
    elif mutation == "diagnostic_targets_other_objective":
        q["q3"]["targets_misconception"] = "light_is_food"
    elif mutation == "missing_rubric_level":
        del raw["criteria"][0]["levels"]["3"]
    elif mutation == "extra_rubric_level":
        raw["criteria"][0]["levels"]["4"] = "Exceeds"
    elif mutation == "objective_without_criterion":
        raw["criteria"] = raw["criteria"][1:]
    elif mutation == "objective_without_open_question":
        raw["questions"] = [x for x in raw["questions"] if x["id"] != "q4"]
    elif mutation == "too_many_objectives":
        raw["objectives"] += [{"id": f"extra{i}", "description": "x"} for i in range(2)]
    elif mutation == "bad_identifier":
        q["q1"]["id"] = "Q 1"
    elif mutation == "unknown_field":
        raw["grading"] = "automatic"
    elif mutation == "version_zero":
        raw["version"] = 0
    else:
        raise AssertionError(mutation)
    return raw


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_question_id",
        "question_unknown_objective",
        "diagnostic_undeclared_tag",
        "diagnostic_without_target",
        "open_with_target",
        "diagnostic_targets_other_objective",
        "missing_rubric_level",
        "extra_rubric_level",
        "objective_without_criterion",
        "objective_without_open_question",
        "too_many_objectives",
        "bad_identifier",
        "unknown_field",
        "version_zero",
    ],
)
def test_invalid_fixtures_are_rejected(photosynthesis_raw: dict[str, Any], mutation: str):
    with pytest.raises(ValidationError):
        Lesson.model_validate(_break(photosynthesis_raw, mutation))


def _write(directory: Path, name: str, raw: dict[str, Any]) -> None:
    (directory / name).write_text(json.dumps(raw), encoding="utf-8")


def test_filename_must_match_id_and_version(tmp_path: Path, photosynthesis_raw: dict[str, Any]):
    _write(tmp_path, "photosynthesis.v2.json", photosynthesis_raw)
    with pytest.raises(LessonFixtureError, match="should be named photosynthesis.v1.json"):
        load_catalog(tmp_path)


def test_invalid_fixture_file_names_the_file(tmp_path: Path, photosynthesis_raw: dict[str, Any]):
    _write(tmp_path, "photosynthesis.v1.json", _break(photosynthesis_raw, "version_zero"))
    with pytest.raises(LessonFixtureError, match="photosynthesis.v1.json"):
        load_catalog(tmp_path)


def test_empty_directory_is_an_error(tmp_path: Path):
    with pytest.raises(LessonFixtureError):
        load_catalog(tmp_path)


def test_multiple_versions_and_latest(tmp_path: Path, photosynthesis_raw: dict[str, Any]):
    _write(tmp_path, "photosynthesis.v1.json", photosynthesis_raw)
    photosynthesis_raw["version"] = 2
    _write(tmp_path, "photosynthesis.v2.json", photosynthesis_raw)
    catalog = load_catalog(tmp_path)
    assert catalog.latest("photosynthesis").version == 2
    assert catalog.get("photosynthesis", 1).version == 1
    assert catalog.latest("missing") is None
