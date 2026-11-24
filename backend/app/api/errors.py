"""Map service errors to HTTP responses with one consistent body shape (ErrorResponse)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas.sessions import ErrorResponse
from app.services import errors as e

# (status code, machine-readable error code)
ERROR_MAP: dict[type[e.AssessmentError], tuple[int, str]] = {
    e.MissingTokenError: (401, "missing_token"),
    e.SessionNotFoundError: (404, "session_not_found"),
    e.LessonNotFoundError: (404, "lesson_not_found"),
    e.StaleStateVersionError: (409, "stale_state_version"),
    e.IdempotencyMismatchError: (409, "idempotency_mismatch"),
    e.TurnInProgressError: (409, "turn_in_progress"),
    e.ClaimLostError: (409, "claim_lost"),
    e.QuestionMismatchError: (409, "question_mismatch"),
    e.SessionClosedError: (409, "session_closed"),
    e.SessionExpiredError: (409, "session_expired"),
    e.EvaluationUnavailableError: (503, "evaluation_unavailable"),
    e.VoiceUnavailableError: (503, "voice_unavailable"),
    e.TeacherNotFoundError: (401, "teacher_not_found"),
    e.ReportNotFoundError: (404, "report_not_found"),
    e.StaleRevisionError: (409, "stale_revision"),
    e.ReportNotReadyError: (409, "report_not_ready"),
    e.ReportNotApprovedError: (409, "report_not_approved"),
    e.InvalidReviewError: (422, "invalid_review"),
    e.NotSignedInError: (401, "not_signed_in"),
    e.InvalidCredentialsError: (401, "invalid_credentials"),
    e.EmailTakenError: (409, "email_taken"),
    e.WrongRoleError: (403, "wrong_role"),
    e.ClassNotFoundError: (404, "class_not_found"),
    e.NoClassError: (409, "no_class"),
}
RETRYABLE = {e.TurnInProgressError, e.EvaluationUnavailableError}


async def _handle(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, e.AssessmentError)
    status, code = ERROR_MAP.get(type(exc), (500, "internal_error"))
    body = ErrorResponse(error=code, message=str(exc), state_version=exc.state_version)
    headers = {"Retry-After": "1"} if type(exc) in RETRYABLE else None
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(e.AssessmentError, _handle)


def error_responses(*codes: int) -> dict[int | str, dict[str, object]]:
    """OpenAPI docs: declare that these status codes return ErrorResponse."""
    return {code: {"model": ErrorResponse} for code in codes}
