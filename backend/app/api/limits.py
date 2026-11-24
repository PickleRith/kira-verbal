"""Request limits: rate limiting (Redis) and a request-size cap.

Why: the demo is public and every answer can cost a model call, so creation and turn
submission must be bounded per caller. Limits are fixed one-minute windows:

  create   POST /v1/sessions, /v1/teacher/workspaces, /v1/teacher/sessions,
           /v1/me/sessions                                                     per client IP
  auth     POST /v1/auth/login, /v1/auth/register (password guessing)          per client IP
  turn     POST /v1/sessions/{id}/turns                                        per session
  default  every other /v1 request (reads, polling, review, export)            per client IP

Over the limit -> 429 `rate_limited` with Retry-After (seconds to the next window).
A body larger than MAX_BODY_BYTES -> 413 `payload_too_large` before it is parsed.

Redis is coordination only. If it is unreachable the limiter FAILS OPEN (requests pass,
a warning is logged): losing rate limiting must not take the assessment down, and
correctness never depends on it. /health and /ready are never limited.

Client IP is `request.client.host`. Behind a reverse proxy, run uvicorn with
`--proxy-headers --forwarded-allow-ips=<proxy>` so that value is the real client.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import redis
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.schemas.sessions import ErrorResponse

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
_TURN_PATH = re.compile(r"^/v1/sessions/([0-9a-fA-F-]{36})/turns$")
_CREATE_PATHS = frozenset(
    {"/v1/sessions", "/v1/teacher/workspaces", "/v1/teacher/sessions", "/v1/me/sessions"}
)
_AUTH_PATHS = frozenset({"/v1/auth/login", "/v1/auth/register"})


@dataclass(frozen=True)
class LimitConfig:
    enabled: bool = True
    create_per_minute: int = 30
    turns_per_minute: int = 40
    requests_per_minute: int = 600
    auth_per_minute: int = 10
    max_body_bytes: int = 16_384


def classify(method: str, path: str, client_ip: str, config: LimitConfig) -> tuple[str, int] | None:
    """Return (redis key prefix, limit) for a request, or None if it is not limited."""
    if method == "OPTIONS" or not path.startswith("/v1/"):
        return None
    if method == "POST":
        if path in _AUTH_PATHS:
            return f"auth:{client_ip}", config.auth_per_minute
        if path in _CREATE_PATHS:
            return f"create:{client_ip}", config.create_per_minute
        match = _TURN_PATH.match(path)
        if match:
            return f"turn:{match.group(1).lower()}", config.turns_per_minute
    return f"default:{client_ip}", config.requests_per_minute


def _error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> Response:
    body = ErrorResponse(error=code, message=message, state_version=None)
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


class RequestLimitsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: LimitConfig) -> None:  # noqa: ANN001 - ASGI app
        super().__init__(app)
        self.config = config
        self._last_warning = 0.0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > self.config.max_body_bytes:
            return _error(413, "payload_too_large", "request body is too large")

        if self.config.enabled:
            client_ip = request.client.host if request.client else "unknown"
            bucket = classify(request.method, request.url.path, client_ip, self.config)
            client: redis.Redis | None = getattr(request.app.state, "redis", None)
            if bucket is not None and client is not None:
                key, limit = bucket
                retry_after = await run_in_threadpool(self._hit, client, key, limit)
                if retry_after is not None:
                    return _error(
                        429,
                        "rate_limited",
                        "too many requests; please slow down",
                        {"Retry-After": str(retry_after)},
                    )
        return await call_next(request)

    def _hit(self, client: redis.Redis, key: str, limit: int) -> int | None:
        """Count this request. Return seconds to wait if over the limit, else None."""
        now = time.time()
        window = int(now // WINDOW_SECONDS)
        try:
            pipe = client.pipeline()
            pipe.incr(f"kv:rl:{key}:{window}")
            pipe.expire(f"kv:rl:{key}:{window}", WINDOW_SECONDS * 2)
            count, _ = pipe.execute()
        except redis.RedisError as exc:
            if now - self._last_warning > 30:  # don't flood the log during an outage
                self._last_warning = now
                logger.warning("rate limiter unavailable (%s); allowing", type(exc).__name__)
            return None
        if count > limit:
            return max(1, int((window + 1) * WINDOW_SECONDS - now) + 1)
        return None
