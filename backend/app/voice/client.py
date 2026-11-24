"""Minimal async client for the Kira Verbal API, authorized with a voice-worker credential."""

from __future__ import annotations

from typing import Any

import httpx

# A turn can wait on the evaluator (up to EVALUATOR_TIMEOUT_SECONDS, default 45 s).
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


class ApiError(Exception):
    def __init__(self, status: int, code: str, state_version: int | None) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.state_version = state_version


class KiraClient:
    def __init__(
        self,
        base_url: str,
        credential: str,
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._http = http or httpx.AsyncClient(base_url=base_url, timeout=DEFAULT_TIMEOUT)
        self._headers = {"Authorization": f"Bearer {credential}"}

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/sessions/{session_id}")

    async def submit_turn(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/v1/sessions/{session_id}/turns", json=body)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._http.request(method, path, headers=self._headers, **kwargs)
        if response.is_success:
            return response.json()
        try:
            data = response.json()
        except ValueError:
            data = {}
        raise ApiError(
            response.status_code, data.get("error", "unknown_error"), data.get("state_version")
        )

    async def aclose(self) -> None:
        await self._http.aclose()
