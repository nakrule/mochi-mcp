from __future__ import annotations

import httpx
import pytest

from mochi_mcp.api import MochiAPIError, MochiClient


@pytest.mark.asyncio
async def test_list_decks_parses_paginated_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/decks"
        assert request.headers["Authorization"] == "Bearer secret"
        assert request.headers["X-API-Key"] == "secret"
        assert request.url.params["limit"] == "50"
        assert request.url.params["cursor"] == "abc"
        return httpx.Response(
            200,
            json={
                "data": {
                    "decks": [
                        {"id": "deck-1", "name": "My Deck"},
                    ],
                    "cursor": "next-cursor",
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
        async with MochiClient("secret", base_url="https://example.test", client=http_client) as client:
            result = await client.list_decks(limit=50, cursor="abc")
    assert result.items == [{"id": "deck-1", "name": "My Deck"}]
    assert result.next_cursor == "next-cursor"


@pytest.mark.asyncio
async def test_get_note_handles_nested_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/notes/note-1"
        return httpx.Response(200, json={"data": {"note": {"id": "note-1", "front": "Hello"}}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
        async with MochiClient("secret", base_url="https://example.test", client=http_client) as client:
            note = await client.get_note("note-1")
    assert note == {"id": "note-1", "front": "Hello"}


@pytest.mark.asyncio
async def test_delete_note_allows_no_content_response() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
        async with MochiClient("secret", base_url="https://example.test", client=http_client) as client:
            await client.delete_note("note-1")
    assert calls == ["/notes/note-1"]


@pytest.mark.asyncio
async def test_client_raises_for_error_status() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Not Found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://example.test") as http_client:
        async with MochiClient("secret", base_url="https://example.test", client=http_client) as client:
            with pytest.raises(MochiAPIError) as excinfo:
                await client.get_deck("missing")
    assert "404" in str(excinfo.value)
