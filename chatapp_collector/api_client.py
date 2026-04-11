"""ChatApp API client with automatic token management and rate limiting.

READ-ONLY: This client only uses GET requests for data retrieval.
The only POST requests are for authentication (tokens).
"""

import asyncio
import sys
import time
from typing import Any

import httpx

from .config import settings


class ChatAppClient:
    """Async HTTP client for ChatApp API."""

    def __init__(self) -> None:
        self.base_url = settings.chatapp_base_url
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._last_request_time = 0.0
        self._min_interval = 1.0 / settings.rate_limit_per_sec

    async def __aenter__(self) -> "ChatAppClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0, read=15.0),
        )
        await self.authenticate()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()

    # ── Auth ──────────────────────────────────────────────────────────

    async def authenticate(self) -> None:
        """Get access + refresh tokens via email/password."""
        resp = await self._raw_post("/v1/tokens", json={
            "email": settings.chatapp_email,
            "password": settings.chatapp_password,
            "appId": settings.chatapp_app_id,
        })
        data = resp.json()["data"]
        self.access_token = data["accessToken"]
        self.refresh_token = data["refreshToken"]

    async def _refresh_access_token(self) -> None:
        resp = await self._raw_post("/v1/tokens/refresh", json={
            "refreshToken": self.refresh_token,
        })
        data = resp.json()["data"]
        self.access_token = data["accessToken"]
        self.refresh_token = data.get("refreshToken", self.refresh_token)

    # ── Low-level HTTP ────────────────────────────────────────────────

    async def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_time = time.monotonic()

    async def _raw_post(self, path: str, **kwargs: Any) -> httpx.Response:
        assert self._client
        resp = await self._client.post(f"{self.base_url}{path}", **kwargs)
        if resp.status_code >= 400:
            print(f"[AUTH ERROR] {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
        return resp

    async def _request(
        self, method: str, path: str, retries: int = 2, **kwargs: Any
    ) -> dict[str, Any]:
        assert self._client
        headers = {"Authorization": self.access_token or "", "Lang": "ru"}
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            await self._throttle()
            try:
                resp = await self._client.request(
                    method, f"{self.base_url}{path}", headers=headers, **kwargs,
                )
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ReadError) as e:
                last_exc = e
                print(f"[TIMEOUT] {method} {path} attempt {attempt+1}: {e}", file=sys.stderr, flush=True)
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                raise
            if resp.status_code == 401 and attempt == 0:
                await self._refresh_access_token()
                headers["Authorization"] = self.access_token or ""
                continue
            if resp.status_code == 429:  # rate limited
                print(f"[RATE LIMIT] {path}, sleeping 2s", file=sys.stderr, flush=True)
                await asyncio.sleep(2)
                continue
            if resp.status_code >= 400:
                print(f"[API {resp.status_code}] {method} {path}: {resp.text[:300]}", file=sys.stderr, flush=True)
            resp.raise_for_status()
            return resp.json()
        raise last_exc or RuntimeError("Request failed after retries")

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return await self._request("GET", path, **kwargs)

    async def safe_get(self, path: str, **kwargs: Any) -> dict[str, Any] | None:
        """GET that returns None on 403/404 instead of raising."""
        try:
            return await self.get(path, **kwargs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                return None
            raise

    # ── High-level API methods (READ-ONLY) ────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        return await self.get("/v1/me")

    async def get_companies(self) -> list[dict[str, Any]]:
        """Returns list of company objects. API: data.items[]"""
        resp = await self.get("/v1/companies")
        data = resp.get("data", {})
        if isinstance(data, list):
            return data
        return data.get("items", [])

    async def get_licenses(self) -> list[dict[str, Any]]:
        """Returns list of license objects. API: data[]"""
        resp = await self.get("/v1/licenses")
        data = resp.get("data", [])
        if isinstance(data, list):
            return data
        return data.get("items", [])

    async def get_employees(self, company_id: int) -> list[dict[str, Any]]:
        """Returns list of employee objects. API: data.items[]"""
        resp = await self.get(f"/v1/companies/{company_id}/employees")
        data = resp.get("data", {})
        if isinstance(data, list):
            return data
        return data.get("items", [])

    async def get_chats_page(
        self,
        license_id: int,
        messenger_type: str,
        *,
        last_time: int | None = None,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch one page of chats. Returns (items, next_last_time)."""
        params: dict[str, Any] = {"limit": limit}
        if last_time is not None:
            params["lastTime"] = last_time
        resp = await self.get(
            f"/v1/licenses/{license_id}/messengers/{messenger_type}/chats",
            params=params,
        )
        data = resp.get("data", {})
        items = data.get("items", []) if isinstance(data, dict) else []
        # Determine next cursor
        next_lt = None
        if items:
            next_lt = items[-1].get("lastTime")
        return items, next_lt

    async def get_all_chats(
        self, license_id: int, messenger_type: str,
    ) -> list[dict[str, Any]]:
        """Iterate through all pages and collect every chat."""
        all_chats: list[dict[str, Any]] = []
        last_time: int | None = None
        while True:
            page, next_lt = await self.get_chats_page(
                license_id, messenger_type, last_time=last_time,
            )
            if not page:
                break
            all_chats.extend(page)
            if len(page) < 100 or next_lt is None:
                break
            last_time = next_lt
        return all_chats

    async def get_messages_page(
        self,
        license_id: int,
        messenger_type: str,
        chat_id: str,
        *,
        next_page: str | None = None,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch one page of messages. Returns (items, nextPage cursor)."""
        params: dict[str, Any] = {"limit": limit}
        if next_page is not None:
            params["nextPage"] = next_page
        resp = await self.get(
            f"/v1/licenses/{license_id}/messengers/{messenger_type}"
            f"/chats/{chat_id}/messages",
            params=params,
        )
        data = resp.get("data", {})
        items = data.get("items", []) if isinstance(data, dict) else []
        cursor = data.get("nextPage") if isinstance(data, dict) else None
        return items, cursor

    async def get_all_messages(
        self, license_id: int, messenger_type: str, chat_id: str,
    ) -> list[dict[str, Any]]:
        """Iterate through all pages and collect every message for a chat."""
        all_msgs: list[dict[str, Any]] = []
        next_page: str | None = None
        while True:
            page, cursor = await self.get_messages_page(
                license_id, messenger_type, chat_id, next_page=next_page,
            )
            if not page:
                break
            all_msgs.extend(page)
            if not cursor or len(page) < 100:
                break
            next_page = cursor
        return all_msgs

    async def get_tags(self) -> list[dict[str, Any]]:
        resp = await self.get("/v1/chatTags")
        data = resp.get("data", [])
        if isinstance(data, list):
            return data
        return data.get("items", [])
