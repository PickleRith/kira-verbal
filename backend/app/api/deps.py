"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.assessment import AssessmentService
from app.services.errors import MissingTokenError
from app.services.lessons import LessonStore

_bearer = HTTPBearer(auto_error=False)


def get_assessment(request: Request) -> AssessmentService:
    return request.app.state.assessment


def get_lessons(request: Request) -> LessonStore:
    return request.app.state.lesson_store


def session_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Demo authorization: a per-session bearer token issued at creation.

    This isolates synthetic sessions from each other; it is not school authentication.
    """
    if credentials is None or not credentials.credentials:
        raise MissingTokenError("Authorization: Bearer <session_token> required")
    return credentials.credentials
