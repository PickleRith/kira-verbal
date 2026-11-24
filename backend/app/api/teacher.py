"""Teacher routes: demo classroom, sessions, reports, review, export.

All of these (except creating a workspace) need `Authorization: Bearer <teacher_token>`.
A learner's session token is not a teacher token and never opens a report.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import session_token as bearer_token
from app.api.errors import error_responses
from app.schemas.reports import (
    ExportResponse,
    ReportView,
    ReviewRequest,
    TeacherCreateSession,
    TeacherSessionCreated,
    TeacherSessionItem,
    WorkspaceCreated,
    WorkspaceView,
)
from app.services.reports import ReportService

router = APIRouter(prefix="/v1", tags=["teacher"])


def get_reports(request: Request) -> ReportService:
    return request.app.state.reports


@router.post("/teacher/workspaces", status_code=201, response_model=WorkspaceCreated)
def create_workspace(reports: ReportService = Depends(get_reports)) -> WorkspaceCreated:
    workspace_id, token = reports.create_workspace()
    return WorkspaceCreated(workspace_id=workspace_id, teacher_token=token)


@router.get("/teacher/workspace", response_model=WorkspaceView, responses=error_responses(401))
def get_workspace(
    token: str = Depends(bearer_token), reports: ReportService = Depends(get_reports)
) -> WorkspaceView:
    row = reports.workspace(token)
    return WorkspaceView(workspace_id=row.id, created_at=row.created_at)


@router.post(
    "/teacher/sessions",
    status_code=201,
    response_model=TeacherSessionCreated,
    responses=error_responses(401, 404),
)
def create_session(
    body: TeacherCreateSession,
    token: str = Depends(bearer_token),
    reports: ReportService = Depends(get_reports),
) -> TeacherSessionCreated:
    view, session_token = reports.create_session(token, body.lesson_id, body.synthetic_learner_id)
    return TeacherSessionCreated(
        session_id=view.id,
        session_token=session_token,
        lesson=view.lesson,
        synthetic_learner_id=body.synthetic_learner_id,
    )


@router.get(
    "/teacher/sessions", response_model=list[TeacherSessionItem], responses=error_responses(401)
)
def list_sessions(
    token: str = Depends(bearer_token), reports: ReportService = Depends(get_reports)
) -> list[TeacherSessionItem]:
    return reports.list_sessions(token)


@router.get(
    "/sessions/{session_id}/report", response_model=ReportView, responses=error_responses(401, 404)
)
def get_report(
    session_id: uuid.UUID,
    token: str = Depends(bearer_token),
    reports: ReportService = Depends(get_reports),
) -> ReportView:
    return reports.get_report(token, session_id)


@router.post(
    "/reports/{report_id}/review",
    response_model=ReportView,
    responses=error_responses(401, 404, 409, 422),
)
def review_report(
    report_id: uuid.UUID,
    body: ReviewRequest,
    token: str = Depends(bearer_token),
    reports: ReportService = Depends(get_reports),
) -> ReportView:
    return reports.review(token, report_id, body)


@router.post(
    "/reports/{report_id}/export",
    response_model=ExportResponse,
    responses=error_responses(401, 404, 409),
)
def export_report(
    report_id: uuid.UUID,
    token: str = Depends(bearer_token),
    reports: ReportService = Depends(get_reports),
) -> ExportResponse:
    return reports.export(token, report_id)
