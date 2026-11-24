import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

from app.providers.livekit_tokens import mint_room_token
from app.services import voice_credentials as vc

SECRET = "test-secret"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_credential_round_trip():
    sid = uuid.uuid4()
    token = vc.issue(SECRET, sid, NOW + timedelta(minutes=5))
    assert vc.looks_like_credential(token)
    assert vc.verify(SECRET, token, sid, NOW)


def test_credential_is_scoped_to_one_session():
    token = vc.issue(SECRET, uuid.uuid4(), NOW + timedelta(minutes=5))
    assert not vc.verify(SECRET, token, uuid.uuid4(), NOW)


def test_credential_expires():
    sid = uuid.uuid4()
    token = vc.issue(SECRET, sid, NOW + timedelta(minutes=5))
    assert not vc.verify(SECRET, token, sid, NOW + timedelta(minutes=5))


def test_tampered_or_foreign_credentials_fail():
    sid = uuid.uuid4()
    token = vc.issue(SECRET, sid, NOW + timedelta(minutes=5))
    prefix, s, exp, sig = token.split(".")
    longer = f"{prefix}.{s}.{int(exp) + 3600}.{sig}"  # extend expiry without re-signing
    assert not vc.verify(SECRET, longer, sid, NOW)
    assert not vc.verify("other-secret", token, sid, NOW)
    assert not vc.verify(SECRET, "v1.not-a-uuid.1.abc", sid, NOW)
    assert not vc.verify(SECRET, "garbage", sid, NOW)


def _jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def test_room_token_dispatches_worker_with_session_metadata():
    sid = uuid.uuid4()
    room = mint_room_token(
        api_key="key",
        api_secret="secret-0123456789abcdef0123456789abcdef",
        server_url="wss://example.livekit.cloud",
        agent_name="kira-verbal-voice",
        session_id=sid,
        worker_credential="v1.cred",
        ttl=timedelta(minutes=10),
        now=NOW,
    )
    claims = _jwt_claims(room.participant_token)
    assert room.room_name.startswith(f"kv-{sid}-")
    assert claims["sub"] == f"learner-{sid}"
    assert claims["video"]["room"] == room.room_name and claims["video"]["roomJoin"] is True
    [dispatch] = claims["roomConfig"]["agents"]
    assert dispatch["agentName"] == "kira-verbal-voice"
    assert json.loads(dispatch["metadata"]) == {"session_id": str(sid), "credential": "v1.cred"}


def test_each_voice_attempt_gets_a_fresh_room():
    """Token dispatch only fires when a room is created, so rooms must not be reused."""
    kwargs = dict(
        api_key="k",
        api_secret="s-0123456789abcdef0123456789abcdef",
        server_url="wss://x",
        agent_name="a",
        session_id=uuid.uuid4(),
        worker_credential="c",
        ttl=timedelta(minutes=1),
        now=NOW,
    )
    assert mint_room_token(**kwargs).room_name != mint_room_token(**kwargs).room_name
