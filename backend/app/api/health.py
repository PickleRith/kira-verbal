"""Liveness and readiness.

/health answers "is the process up?" and never touches dependencies, so a
database outage does not make an orchestrator restart a healthy process.
/ready answers "can this instance serve traffic?" and returns 503 if any
dependency check fails. Failure details go to the log, not the response.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping

from fastapi import APIRouter, Request, Response, status

from app.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

ReadinessCheck = Callable[[], None]  # raises on failure


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def ready(request: Request, response: Response) -> ReadinessResponse:
    checks: Mapping[str, ReadinessCheck] = request.app.state.readiness_checks
    results: dict[str, str] = {}
    for name, check in checks.items():
        try:
            check()
            results[name] = "ok"
        except Exception:  # any failure means not ready; record why in logs only
            logger.warning("readiness check %r failed", name, exc_info=True)
            results[name] = "unavailable"

    all_ok = all(value == "ok" for value in results.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if all_ok else "not_ready", checks=results)
