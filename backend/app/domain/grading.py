"""Turn rubric levels into a score and a grade band.

Each criterion is scored 0-3 (the rubric levels). The score is the sum of the levels of the
criteria that have a level, out of 3 per such criterion, so a criterion with no evidence
("unknown") is never counted as zero. The grade band needs every criterion to have a level:
until then the grade is "incomplete" and the teacher can set the missing ones (0 included).

Bands, on the percentage of available points:
  85-100 mastered · 65-84 proficient · 40-64 developing · 0-39 beginning

These are prototype thresholds, not a validated standard. The same rule is mirrored in
frontend/lib/grading.ts so the teacher sees the score change while choosing levels; the
browser test checks that the student is shown exactly the score the teacher approved.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

MAX_LEVEL = 3
BANDS: tuple[tuple[int, str], ...] = (
    (85, "mastered"),
    (65, "proficient"),
    (40, "developing"),
    (0, "beginning"),
)


@dataclass(frozen=True)
class Grade:
    points: int
    max_points: int  # 3 x criteria that have a level
    percent: int | None  # rounded; None when no criterion has a level
    assessed: int
    total: int
    band: str  # mastered | proficient | developing | beginning | incomplete


def band_for(percent: int) -> str:
    return next(name for floor, name in BANDS if percent >= floor)


def grade(levels: Mapping[str, int | None]) -> Grade:
    scored = [level for level in levels.values() if level is not None]
    for level in scored:
        if not 0 <= level <= MAX_LEVEL:
            raise ValueError(f"level {level} outside 0-{MAX_LEVEL}")
    points, max_points = sum(scored), MAX_LEVEL * len(scored)
    # Round half up in integers, so Python and the browser always agree.
    percent = (200 * points + max_points) // (2 * max_points) if max_points else None
    complete = len(levels) > 0 and len(scored) == len(levels)
    return Grade(
        points=points,
        max_points=max_points,
        percent=percent,
        assessed=len(scored),
        total=len(levels),
        band=band_for(percent) if complete and percent is not None else "incomplete",
    )
