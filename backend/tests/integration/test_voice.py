"""Voice against the real API: token endpoint, worker credential, and the full spoken flow.

The worker's turn logic (app/voice/transport.py) talks HTTP to the same FastAPI app the
browser uses, via httpx's ASGI transport. Only LiveKit itself (audio, STT, TTS) is absent.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db.models import TurnRow
from app.main import create_app
from app.voice import transport
from app.voice.client import KiraClient
from app.voice.transport import VoiceTurnBridge

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def voice_api(seeded_engine, database_url, clock, evaluator):
    settings = Settings(
        database_url=database_url,
        evaluator_timeout_seconds=1.0,
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-livekit-secret-0123456789abcdef",
        voice_worker_secret="test-worker-secret-0123456789abcdef",
    )
    app = create_app(settings, readiness_checks={"ok": lambda: None}, evaluator=evaluator)
    with TestClient(app) as client:
        app.state.assessment.clock = clock
        yield client


def start(api: TestClient) -> tuple[str, dict[str, str]]:
    session = api.post("/v1/sessions", json={"lesson_id": "photosynthesis"}).json()
    return session["id"], {"Authorization": f"Bearer {session['session_token']}"}


def credential_from(token_response: dict) -> str:
    payload = token_response["participant_token"].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return json.loads(claims["roomConfig"]["agents"][0]["metadata"])["credential"]


def bridge_for(api: TestClient, session_id: str, credential: str) -> VoiceTurnBridge:
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://api")
    return VoiceTurnBridge(KiraClient("http://api", credential, http=http), session_id)


# --- token endpoint ---------------------------------------------------------------------


def test_voice_token_requires_configuration(api: TestClient):
    sid, auth = start(api)
    response = api.post(f"/v1/sessions/{sid}/voice-token", headers=auth)
    assert response.status_code == 503 and response.json()["error"] == "voice_unavailable"


def test_voice_token_requires_session_auth(voice_api: TestClient):
    sid, _ = start(voice_api)
    assert voice_api.post(f"/v1/sessions/{sid}/voice-token").status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=wrong).status_code == 404


def test_voice_token_issued_for_open_session(voice_api: TestClient):
    sid, auth = start(voice_api)
    response = voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["server_url"] == "wss://example.livekit.cloud"
    assert body["room_name"].startswith(f"kv-{sid}-")
    assert credential_from(body).startswith("v1.")


def test_no_voice_token_for_finished_session(voice_api: TestClient):
    sid, auth = start(voice_api)
    voice_api.post(f"/v1/sessions/{sid}/finish", json={"expected_state_version": 1}, headers=auth)
    response = voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth)
    assert response.status_code == 409 and response.json()["error"] == "session_closed"


def test_worker_credential_only_opens_its_own_session(voice_api: TestClient):
    sid, auth = start(voice_api)
    other_sid, _ = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    worker = {"Authorization": f"Bearer {cred}"}
    assert voice_api.get(f"/v1/sessions/{sid}", headers=worker).status_code == 200
    assert voice_api.get(f"/v1/sessions/{other_sid}", headers=worker).status_code == 404


def test_worker_credential_expires_with_the_session(voice_api: TestClient, clock):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    clock.advance(300 + 60 + 1)  # past the session deadline
    response = voice_api.get(f"/v1/sessions/{sid}", headers={"Authorization": f"Bearer {cred}"})
    assert response.status_code == 404


# --- the spoken flow through the worker's bridge --------------------------------------


async def test_voice_completes_the_same_flow_as_text(voice_api: TestClient, seeded_engine):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    bridge = bridge_for(voice_api, sid, cred)

    opening = await bridge.opening()
    assert opening.startswith("Hi! This is a short spoken check-in about Photosynthesis.")
    assert opening.endswith("Explain photosynthesis in your own words.")

    said = await bridge.handle_final_transcript(
        "Plants use sunlight to make sugar from carbon dioxide and water."
    )
    assert said == "Where does a plant get carbon dioxide?"
    said = await bridge.handle_final_transcript("From the soil through its roots.")
    assert said == "How do leaves exchange gases with the air?"  # adaptive follow-up
    said = await bridge.handle_final_transcript("Through tiny holes called stomata.")
    assert said == "What role does sunlight play for a plant?"
    said = await bridge.handle_final_transcript("It gives the energy to make sugar.")
    assert said == transport.DEFAULT_CLOSING and bridge.finished

    # The browser sees the same transcript, recorded as voice.
    view = voice_api.get(f"/v1/sessions/{sid}", headers=auth).json()
    assert view["status"] == "completed"
    assert [t["modality"] for t in view["transcript"]] == ["voice"] * 4
    with seeded_engine.connect() as c:
        answers = c.scalars(select(TurnRow.transcript).order_by(TurnRow.sequence)).all()
    assert all("Where does a plant" not in a for a in answers)  # agent speech never stored


async def test_hint_by_voice_is_spoken_with_lead_in(voice_api: TestClient):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    bridge = bridge_for(voice_api, sid, cred)
    await bridge.opening()
    said = await bridge.handle_final_transcript("Can I have a hint?")
    assert said.startswith("Here's a hint:") and said.endswith("in your own words.")


async def test_spoken_side_turns_get_a_reply_and_use_no_answer(voice_api: TestClient):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    bridge = bridge_for(voice_api, sid, cred)
    await bridge.opening()
    said = await bridge.handle_final_transcript("Sorry, can you say that again?")
    assert said == "Sure, here's the question again. Explain photosynthesis in your own words."
    said = await bridge.handle_final_transcript("What is chlorophyll?")
    assert said.startswith("That's a good question.")
    assert said.endswith("Explain photosynthesis in your own words.")
    # The session moves on normally afterwards.
    said = await bridge.handle_final_transcript(
        "Plants use sunlight to make sugar from carbon dioxide and water."
    )
    assert said == "Where does a plant get carbon dioxide?"


async def test_empty_turn_is_not_submitted(voice_api: TestClient, evaluator):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    bridge = bridge_for(voice_api, sid, cred)
    await bridge.opening()
    assert await bridge.handle_final_transcript("   ") is None
    assert evaluator.calls == 0


async def test_typing_in_the_browser_meanwhile_resyncs_voice(voice_api: TestClient):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    bridge = bridge_for(voice_api, sid, cred)
    await bridge.opening()  # bridge thinks we're on q1, version 1

    typed = {
        "client_turn_id": "typed-1",
        "expected_state_version": 1,
        "modality": "text",
        "question_id": "q1",
        "transcript": "Plants make sugar using light, water and CO2.",
    }
    assert voice_api.post(f"/v1/sessions/{sid}/turns", json=typed, headers=auth).status_code == 200

    said = await bridge.handle_final_transcript("Plants turn light into food energy.")
    assert said == transport.RESYNC + "Where does a plant get carbon dioxide?"
    view = voice_api.get(f"/v1/sessions/{sid}", headers=auth).json()
    assert len(view["transcript"]) == 1  # the stale spoken answer was not counted


async def test_evaluator_outage_asks_learner_to_repeat(voice_api: TestClient, evaluator):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    bridge = bridge_for(voice_api, sid, cred)
    await bridge.opening()
    evaluator.raise_next = ConnectionError("provider down")
    assert await bridge.handle_final_transcript("Plants make food.") == transport.RETRY_ANSWER
    # and the retry works, from the refreshed state version
    said = await bridge.handle_final_transcript("Plants make food from light and water.")
    assert said == "Where does a plant get carbon dioxide?"


async def test_silence_reprompts_twice_then_stays_quiet(voice_api: TestClient):
    sid, auth = start(voice_api)
    cred = credential_from(voice_api.post(f"/v1/sessions/{sid}/voice-token", headers=auth).json())
    bridge = bridge_for(voice_api, sid, cred)
    await bridge.opening()
    assert await bridge.reprompt() == "Take your time. Explain photosynthesis in your own words."
    assert await bridge.reprompt() is not None
    assert await bridge.reprompt() is None


async def test_unreachable_api_offers_text_fallback():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://api")
    bridge = VoiceTurnBridge(KiraClient("http://api", "v1.x.1.y", http=http), "sid")
    assert await bridge.handle_final_transcript("an answer") == transport.TROUBLE


async def test_network_retry_reuses_the_same_turn_id():
    seen: list[str] = []
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "status": "awaiting_answer",
                    "state_version": 1,
                    "lesson": {"title": "T"},
                    "prompt": {"question_id": "q1", "text": "Q1?", "lead_in": None},
                },
            )
        seen.append(json.loads(request.content)["client_turn_id"])
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("lost response", request=request)
        return httpx.Response(
            200,
            json={
                "status": "awaiting_answer",
                "state_version": 3,
                "finish_reason": None,
                "prompt": {"question_id": "q2", "text": "Q2?", "lead_in": None},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(flaky), base_url="http://api")
    bridge = VoiceTurnBridge(KiraClient("http://api", "cred", http=http), "sid")
    assert await bridge.handle_final_transcript("answer") == "Q2?"
    assert len(seen) == 2 and seen[0] == seen[1]  # idempotent retry
