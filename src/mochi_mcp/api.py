"""HTTP client abstractions for interacting with the Mochi API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

import httpx


class MochiAPIError(RuntimeError):
    """Raised when the Mochi API responds with an error."""


@dataclass(slots=True)
class PaginatedResult:
    """Represents a paginated response from Mochi."""

    items: list[dict[str, Any]]
    next_cursor: str | None = None

    def to_payload(self, collection_name: str) -> dict[str, Any]:
        """Return a dictionary formatted for tool responses."""

        payload: dict[str, Any] = {collection_name: self.items}
        if self.next_cursor:
            payload["nextCursor"] = self.next_cursor
        return payload


class MochiClient:
    """Asynchronous client that wraps the Mochi REST API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.mochi.cards/v1",
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "mochi-mcp/0.1.0",
        }
        self._client = client or httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout)
        if client is None:
            self._owns_client = True
            self._client.headers.update(headers)
        else:
            # Ensure caller provided the authentication headers.
            for key, value in headers.items():
                self._client.headers.setdefault(key, value)
            self._owns_client = False

    async def __aenter__(self) -> "MochiClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def list_decks(self, *, cursor: str | None = None, limit: int | None = None) -> PaginatedResult:
        params: MutableMapping[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = limit
        response = await self._request("GET", "/decks", params=params)
        data = self._json(response)
        return self._parse_paginated(data, "decks")

    async def get_deck(self, deck_id: str) -> dict[str, Any]:
        response = await self._request("GET", f"/decks/{deck_id}")
        data = self._json(response)
        return self._parse_item(data, "deck")

    async def list_notes(
        self,
        *,
        deck_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        query: str | None = None,
    ) -> PaginatedResult:
        params: MutableMapping[str, Any] = {}
        if deck_id:
            params["deckId"] = deck_id
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = limit
        if query:
            params["query"] = query
        response = await self._request("GET", "/notes", params=params)
        data = self._json(response)
        return self._parse_paginated(data, "notes")

    async def get_note(self, note_id: str) -> dict[str, Any]:
        response = await self._request("GET", f"/notes/{note_id}")
        data = self._json(response)
        return self._parse_item(data, "note")

    async def create_deck(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._request("POST", "/decks", json=payload)
        return self._parse_item(self._json(response), "deck")

    async def update_deck(self, deck_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._request("PATCH", f"/decks/{deck_id}", json=payload)
        return self._parse_item(self._json(response), "deck")

    async def delete_deck(self, deck_id: str) -> None:
        await self._request("DELETE", f"/decks/{deck_id}")

    async def create_note(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._request("POST", "/notes", json=payload)
        return self._parse_item(self._json(response), "note")

    async def update_note(self, note_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._request("PATCH", f"/notes/{note_id}", json=payload)
        return self._parse_item(self._json(response), "note")

    async def delete_note(self, note_id: str) -> None:
        await self._request("DELETE", f"/notes/{note_id}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:  # pragma: no cover - httpx ensures str(exc)
            raise MochiAPIError(f"HTTP error communicating with Mochi: {exc}") from exc

        if response.status_code >= 400:
            message = self._extract_error_message(response)
            raise MochiAPIError(message)

        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise MochiAPIError("Mochi API returned invalid JSON") from exc

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except json.JSONDecodeError:
            return f"Mochi API error {response.status_code}: {response.text.strip()}"

        if isinstance(data, dict):
            for key in ("message", "error", "detail"):
                value = data.get(key)
                if isinstance(value, str):
                    return f"Mochi API error {response.status_code}: {value}"
        return f"Mochi API error {response.status_code}"

    @staticmethod
    def _parse_paginated(data: Any, collection_name: str) -> PaginatedResult:
        items: list[dict[str, Any]] = []
        next_cursor: str | None = None

        if isinstance(data, list):
            items = [item for item in data if isinstance(item, Mapping)]  # type: ignore[list-item]
            return PaginatedResult(items, None)

        if isinstance(data, Mapping):
            # Most API responses use a nested `data` object.
            potential_container: Mapping[str, Any] = data
            data_field = potential_container.get("data")
            if isinstance(data_field, Mapping):
                potential_container = data_field

            if collection_name in potential_container and isinstance(potential_container[collection_name], list):
                items = [item for item in potential_container[collection_name] if isinstance(item, Mapping)]
            elif "items" in potential_container and isinstance(potential_container["items"], list):
                items = [item for item in potential_container["items"] if isinstance(item, Mapping)]

            cursor_value = potential_container.get("nextCursor") or potential_container.get("cursor")
            if isinstance(cursor_value, str) and cursor_value:
                next_cursor = cursor_value

        return PaginatedResult(items, next_cursor)

    @staticmethod
    def _parse_item(data: Any, key: str) -> dict[str, Any]:
        if isinstance(data, Mapping):
            if key in data and isinstance(data[key], Mapping):
                return dict(data[key])
            data_field = data.get("data")
            if isinstance(data_field, Mapping):
                if key in data_field and isinstance(data_field[key], Mapping):
                    return dict(data_field[key])
                return dict(data_field)
        if isinstance(data, Mapping):
            return dict(data)
        raise MochiAPIError("Unexpected response format from Mochi API")


__all__ = ["MochiAPIError", "MochiClient", "PaginatedResult"]
