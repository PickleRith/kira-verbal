import pytest

from app.domain.grading import band_for, grade


def test_all_levels_scored():
    g = grade({"a": 3, "b": 2, "c": 2})
    assert (g.points, g.max_points, g.percent, g.band) == (7, 9, 78, "proficient")
    assert (g.assessed, g.total) == (3, 3)


def test_unknown_is_not_zero_and_makes_the_grade_incomplete():
    g = grade({"a": 3, "b": None, "c": 3})
    assert (g.points, g.max_points, g.percent) == (6, 6, 100)
    assert g.band == "incomplete" and (g.assessed, g.total) == (2, 3)


def test_nothing_known():
    g = grade({"a": None, "b": None})
    assert g.percent is None and g.band == "incomplete" and g.max_points == 0
    assert grade({}).band == "incomplete"


@pytest.mark.parametrize(
    ("percent", "band"),
    [
        (100, "mastered"),
        (85, "mastered"),
        (84, "proficient"),
        (65, "proficient"),
        (64, "developing"),
        (40, "developing"),
        (39, "beginning"),
        (0, "beginning"),
    ],
)
def test_band_boundaries(percent, band):
    assert band_for(percent) == band


def test_rounding_is_half_up():
    # 1/8 = 12.5% -> 13 (Python's round() would give 12)
    levels = {str(i): (3 if i == 0 else 0) for i in range(8)}
    assert grade(levels).percent == 13
    assert grade({"a": 2, "b": 2, "c": 1}).percent == 56  # 5/9 = 55.6


def test_rejects_out_of_range():
    with pytest.raises(ValueError):
        grade({"a": 4})
