from __future__ import annotations

from pydantic import BaseModel


class LessonSummary(BaseModel):
    id: str
    version: int
    title: str
    objective_count: int
