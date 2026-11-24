"""Mint LiveKit room tokens that dispatch the voice worker.

API usage follows the LiveKit docs "Agent dispatch > Dispatch via access token"
(https://docs.livekit.io/agents/server/agent-dispatch/), checked against the installed
livekit-api 1.2.3 (AccessToken.with_identity / with_grants / with_ttl / with_room_config).

Agent dispatch from a token only happens when the room is first created, so every voice
attempt gets a fresh room name.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants


@dataclass(frozen=True)
class VoiceRoomToken:
    server_url: str
    participant_token: str
    room_name: str
    expires_at: datetime


def mint_room_token(
    *,
    api_key: str,
    api_secret: str,
    server_url: str,
    agent_name: str,
    session_id: uuid.UUID,
    worker_credential: str,
    ttl: timedelta,
    now: datetime,
) -> VoiceRoomToken:
    room_name = f"kv-{session_id}-{secrets.token_hex(4)}"
    metadata = json.dumps({"session_id": str(session_id), "credential": worker_credential})
    jwt = (
        AccessToken(api_key, api_secret)
        .with_identity(f"learner-{session_id}")
        .with_name("Learner")
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .with_ttl(ttl)
        .with_room_config(
            RoomConfiguration(agents=[RoomAgentDispatch(agent_name=agent_name, metadata=metadata)])
        )
        .to_jwt()
    )
    return VoiceRoomToken(server_url, jwt, room_name, now + ttl)
