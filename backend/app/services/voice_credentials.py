"""Per-session credential for the voice worker.

The worker submits turns through the same HTTP endpoint as the browser, so it needs to be
authorized for one session. Rather than routing the learner's own session token through
LiveKit, the API mints a separate credential:

    v1.<session_id>.<expires_unix>.<hmac_sha256_hex>

It is scoped to exactly one session, expires at the session deadline, and is verified with
a server-side secret (VOICE_WORKER_SECRET), so nothing needs to be stored.

What it grants: exactly what the learner's session token grants (read the session, submit
turns, finish). It travels inside the LiveKit room token's agent-dispatch metadata, which
the learner's browser can decode. That is acceptable because it gives the browser no more
than it already has; it is NOT a teacher or admin credential.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime

PREFIX = "v1"


def _signature(secret: str, session_id: uuid.UUID, expires: int) -> str:
    message = f"{PREFIX}.{session_id}.{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def issue(secret: str, session_id: uuid.UUID, expires_at: datetime) -> str:
    expires = int(expires_at.timestamp())
    return f"{PREFIX}.{session_id}.{expires}.{_signature(secret, session_id, expires)}"


def looks_like_credential(token: str) -> bool:
    return token.startswith(f"{PREFIX}.") and token.count(".") == 3


def verify(secret: str, token: str, session_id: uuid.UUID, now: datetime) -> bool:
    try:
        prefix, sid, expires_text, signature = token.split(".")
        expires = int(expires_text)
        token_session = uuid.UUID(sid)
    except ValueError:
        return False
    if prefix != PREFIX or token_session != session_id or now.timestamp() >= expires:
        return False
    return hmac.compare_digest(signature, _signature(secret, session_id, expires))
