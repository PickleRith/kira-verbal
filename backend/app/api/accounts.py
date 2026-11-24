"""Account routes: register, sign in and out, the signed-in user, a student's check-ins.

Signed-in routes take `Authorization: Bearer <kvu_ token>`. A signed-in teacher uses the
same token on the teacher routes (app/api/teacher.py) to open their class.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import session_token as bearer_token
from app.api.errors import error_responses
from app.schemas.accounts import (
    AuthResponse,
    JoinClassRequest,
    LoginRequest,
    MeView,
    RegisterRequest,
    ResumeResponse,
    StartLessonRequest,
    StudentSessionItem,
)
from app.schemas.sessions import CreateSessionResponse
from app.services.accounts import AccountService

router = APIRouter(prefix="/v1", tags=["accounts"])


def get_accounts(request: Request) -> AccountService:
    return request.app.state.accounts


@router.post(
    "/auth/register",
    status_code=201,
    response_model=AuthResponse,
    responses=error_responses(404, 409, 422),
)
def register(
    body: RegisterRequest, accounts: AccountService = Depends(get_accounts)
) -> AuthResponse:
    user, token, expires = accounts.register(body)
    return AuthResponse(token=token, expires_at=expires, user=user)


@router.post("/auth/login", response_model=AuthResponse, responses=error_responses(401))
def login(body: LoginRequest, accounts: AccountService = Depends(get_accounts)) -> AuthResponse:
    user, token, expires = accounts.login(body.email, body.password)
    return AuthResponse(token=token, expires_at=expires, user=user)


@router.post("/auth/logout", status_code=204, responses=error_responses(401))
def logout(
    token: str = Depends(bearer_token), accounts: AccountService = Depends(get_accounts)
) -> Response:
    accounts.logout(token)
    return Response(status_code=204)


@router.get("/me", response_model=MeView, responses=error_responses(401))
def me(token: str = Depends(bearer_token), accounts: AccountService = Depends(get_accounts)):
    return accounts.me(token)


@router.post("/me/class", response_model=MeView, responses=error_responses(401, 403, 404))
def join_class(
    body: JoinClassRequest,
    token: str = Depends(bearer_token),
    accounts: AccountService = Depends(get_accounts),
) -> MeView:
    return accounts.join_class(token, body.join_code)


@router.get(
    "/me/sessions", response_model=list[StudentSessionItem], responses=error_responses(401, 403)
)
def my_sessions(
    token: str = Depends(bearer_token), accounts: AccountService = Depends(get_accounts)
) -> list[StudentSessionItem]:
    return accounts.student_sessions(token)


@router.post(
    "/me/sessions",
    status_code=201,
    response_model=CreateSessionResponse,
    responses=error_responses(401, 403, 404, 409),
)
def start_lesson(
    body: StartLessonRequest,
    token: str = Depends(bearer_token),
    accounts: AccountService = Depends(get_accounts),
) -> CreateSessionResponse:
    view, session_token = accounts.start_session(token, body.lesson_id)
    return CreateSessionResponse(**view.model_dump(), session_token=session_token)


@router.post(
    "/me/sessions/{session_id}/resume",
    response_model=ResumeResponse,
    responses=error_responses(401, 403, 404),
)
def resume(
    session_id: uuid.UUID,
    token: str = Depends(bearer_token),
    accounts: AccountService = Depends(get_accounts),
) -> ResumeResponse:
    return ResumeResponse(
        session_id=session_id, session_token=accounts.resume_session(token, session_id)
    )
