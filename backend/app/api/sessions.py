"""Student session routes. Handlers only translate HTTP <-> service calls."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_assessment, get_lessons, session_token
from app.api.errors import error_responses
from app.config import Settings
from app.providers.livekit_tokens import mint_room_token
from app.schemas.lessons import LessonSummary
from app.schemas.sessions import (
    CreateSessionRequest,
    CreateSessionResponse,
    FinishRequest,
    StudentSessionView,
    TurnInput,
    TurnResponse,
    VoiceTokenResponse,
)
from app.services.assessment import AssessmentService
from app.services.errors import VoiceUnavailableError
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
    "/sessions/{session_id}/voice-token",
    response_model=VoiceTokenResponse,
    responses=error_responses(401, 404, 409, 503),
    tags=["sessions"],
)
def create_voice_token(
    session_id: uuid.UUID,
    request: Request,
    token: str = Depends(session_token),
    service: AssessmentService = Depends(get_assessment),
) -> VoiceTokenResponse:
    """Short-lived LiveKit room token that also dispatches the voice worker to the room."""
    settings: Settings = request.app.state.settings
    if not settings.voice_configured:
        raise VoiceUnavailableError("voice is not configured on this server; use text")
    credential, _ = service.issue_voice_credential(session_id, token)
    room = mint_room_token(
        api_key=settings.livekit_api_key.get_secret_value(),  # type: ignore[union-attr]
        api_secret=settings.livekit_api_secret.get_secret_value(),  # type: ignore[union-attr]
        server_url=settings.livekit_url,  # type: ignore[arg-type]
        agent_name=settings.voice_agent_name,
        session_id=session_id,
        worker_credential=credential,
        ttl=timedelta(seconds=settings.voice_token_ttl_seconds),
        now=service.clock(),
    )
    return VoiceTokenResponse(
        server_url=room.server_url,
        participant_token=room.participant_token,
        room_name=room.room_name,
        expires_at=room.expires_at,
    )


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
