"""Student session routes. Handlers only translate HTTP <-> service calls."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_assessment, get_lessons, session_token
from app.api.errors import error_responses
from app.schemas.lessons import LessonSummary
from app.schemas.sessions import (
    CreateSessionRequest,
    CreateSessionResponse,
    FinishRequest,
    StudentSessionView,
    TurnInput,
    TurnResponse,
)
from app.services.assessment import AssessmentService
from app.services.lessons import LessonStore

router = APIRouter(prefix="/v1")


@router.get("/lessons", response_model=list[LessonSummary], tags=["lessons"])
def list_lessons(lessons: LessonStore = Depends(get_lessons)) -> list[LessonSummary]:
    return [
        LessonSummary(
            id=lesson.id,
            version=lesson.version,
            title=lesson.title,
            objective_count=len(lesson.objectives),
        )
        for lesson in lessons.list_latest()
    ]


@router.post(
    "/sessions",
    status_code=201,
    response_model=CreateSessionResponse,
    responses=error_responses(404),
    tags=["sessions"],
)
def create_session(
    body: CreateSessionRequest, service: AssessmentService = Depends(get_assessment)
) -> CreateSessionResponse:
    view, token = service.create_session(
        body.lesson_id, body.lesson_version, body.synthetic_learner_id
    )
    return CreateSessionResponse(**view.model_dump(), session_token=token)


@router.get(
    "/sessions/{session_id}",
    response_model=StudentSessionView,
    responses=error_responses(401, 404),
    tags=["sessions"],
)
def get_session(
    session_id: uuid.UUID,
    token: str = Depends(session_token),
    service: AssessmentService = Depends(get_assessment),
) -> StudentSessionView:
    return service.get_session(session_id, token)


@router.post(
    "/sessions/{session_id}/turns",
    response_model=TurnResponse,
    responses=error_responses(401, 404, 409, 503),
    tags=["sessions"],
)
def submit_turn(
    session_id: uuid.UUID,
    body: TurnInput,
    token: str = Depends(session_token),
    service: AssessmentService = Depends(get_assessment),
) -> TurnResponse:
    return service.submit_turn(session_id, token, body)


@router.post(
    "/sessions/{session_id}/finish",
    response_model=StudentSessionView,
    responses=error_responses(401, 404, 409),
    tags=["sessions"],
)
def finish_session(
    session_id: uuid.UUID,
    body: FinishRequest,
    token: str = Depends(session_token),
    service: AssessmentService = Depends(get_assessment),
) -> StudentSessionView:
    return service.finish(session_id, token, body.expected_state_version)
