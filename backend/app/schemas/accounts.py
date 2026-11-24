"""Account contracts: register, sign in, the signed-in user, and a student's check-ins."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.reports import ScoreView
from app.schemas.sessions import FinishReasonOut, LessonRef

Role = Literal["student", "teacher"]
ReviewStatus = Literal["in_progress", "awaiting_review", "reviewed"]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]

MIN_PASSWORD = 8
MAX_PASSWORD = 128
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise ValueError("name contains control characters")
    if not value:
        raise ValueError("name is required")
    return value


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL.match(value):
        raise ValueError("enter a valid email address")
    return value


def normalize_join_code(value: str) -> str:
    return re.sub(r"[\s-]", "", value).upper()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Strict):
    email: str = Field(max_length=254)
    password: str = Field(min_length=MIN_PASSWORD, max_length=MAX_PASSWORD)
    display_name: str = Field(max_length=80)
    role: Role
    # Students: the code their teacher shares (optional; they can join later).
    join_code: str | None = Field(default=None, max_length=16)
    # Teachers: what to call their class.
    class_name: str | None = Field(default=None, max_length=80)

    _email = field_validator("email")(normalize_email)
    _name = field_validator("display_name")(_clean_name)

    @field_validator("class_name")
    @classmethod
    def _class_name(cls, value: str | None) -> str | None:
        return _clean_name(value) if value and value.strip() else None


class LoginRequest(_Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=MAX_PASSWORD)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return value.strip().lower()


class JoinClassRequest(_Strict):
    join_code: str = Field(min_length=4, max_length=16)


class StartLessonRequest(_Strict):
    lesson_id: Identifier


class ClassView(BaseModel):
    id: uuid.UUID
    name: str
    join_code: str | None = Field(description="Only shown to the class's teacher.")
    teacher_name: str | None
    student_count: int | None = Field(description="Only shown to the class's teacher.")


class MeView(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    created_at: datetime
    class_: ClassView | None = Field(alias="class", serialization_alias="class")

    model_config = ConfigDict(populate_by_name=True)


class AuthResponse(BaseModel):
    token: str = Field(description="Bearer token for this sign-in. Shown once; expires.")
    expires_at: datetime
    user: MeView


class StudentCriterionResult(BaseModel):
    criterion_id: str
    objective_description: str
    level: int | None  # the teacher's approved level; None = not enough evidence
    max_level: int
    descriptor: str | None  # what this level means, from the rubric


class StudentResult(BaseModel):
    """Shown to the student only once their teacher has approved the check-in."""

    score: ScoreView
    approved_at: datetime
    criteria: list[StudentCriterionResult]


class StudentSessionItem(BaseModel):
    session_id: uuid.UUID
    lesson: LessonRef
    session_status: str
    finish_reason: FinishReasonOut | None
    created_at: datetime
    answers: int
    review_status: ReviewStatus
    result: StudentResult | None = None  # only when the latest revision is approved


class ResumeResponse(BaseModel):
    session_id: uuid.UUID
    session_token: str = Field(description="A fresh session token; the previous one stops working.")
