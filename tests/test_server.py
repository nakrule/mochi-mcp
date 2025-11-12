from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from mcp import types

from mochi_mcp.api import PaginatedResult
from mochi_mcp.server import create_server


@dataclass
class FakeMochiClient:
    decks: list[dict[str, Any]] = field(default_factory=lambda: [{"id": "deck-1", "name": "Deck One"}])
    notes: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "note-1": {"id": "note-1", "deckId": "deck-1", "front": "hello"},
            "note-2": {"id": "note-2", "deckId": "deck-2", "front": "world"},
        }
    )
    created_notes: list[dict[str, Any]] = field(default_factory=list)
    updated_notes: list[dict[str, Any]] = field(default_factory=list)
    deleted_notes: list[str] = field(default_factory=list)
    deleted_decks: list[str] = field(default_factory=list)

    async def list_decks(self, *, cursor: str | None = None, limit: int | None = None) -> PaginatedResult:
        return PaginatedResult(self.decks[: limit or len(self.decks)], None)

    async def get_deck(self, deck_id: str) -> dict[str, Any]:
        for deck in self.decks:
            if deck["id"] == deck_id:
                return deck
        return {"id": deck_id}

    async def list_notes(
        self,
        *,
        deck_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        query: str | None = None,
    ) -> PaginatedResult:
        filtered = [note for note in self.notes.values() if deck_id is None or note.get("deckId") == deck_id]
        if query:
            filtered = [note for note in filtered if query.lower() in str(note).lower()]
        return PaginatedResult(filtered[: limit or len(filtered)], None)

    async def get_note(self, note_id: str) -> dict[str, Any]:
        return self.notes[note_id]

    async def create_deck(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        new_deck = {"id": payload.get("name", "deck-new"), **payload}
        self.decks.append(new_deck)
        return new_deck

    async def update_deck(self, deck_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        deck = await self.get_deck(deck_id)
        deck.update(payload)
        return deck

    async def delete_deck(self, deck_id: str) -> None:
        self.deleted_decks.append(deck_id)

    async def create_note(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        note_id = payload.get("id", f"generated-{len(self.created_notes)}")
        note = {"id": note_id, **payload}
        self.created_notes.append(note)
        self.notes[note_id] = note
        return note

    async def update_note(self, note_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        note = self.notes[note_id]
        note.update(payload)
        self.updated_notes.append({"note_id": note_id, **payload})
        return note

    async def delete_note(self, note_id: str) -> None:
        self.deleted_notes.append(note_id)
        self.notes.pop(note_id, None)


@pytest.mark.asyncio
async def test_read_only_tools_exposed() -> None:
    server = create_server(FakeMochiClient(), read_only=True)
    result = await server.request_handlers[types.ListToolsRequest](types.ListToolsRequest())
    tool_names = {tool.name for tool in result.root.tools}
    assert {"list_decks", "get_deck", "list_notes", "get_note"} <= tool_names
    assert "delete_note" not in tool_names


@pytest.mark.asyncio
async def test_write_tools_available_when_enabled() -> None:
    server = create_server(FakeMochiClient(), read_only=False)
    result = await server.request_handlers[types.ListToolsRequest](types.ListToolsRequest())
    tool_names = {tool.name for tool in result.root.tools}
    assert "delete_note" in tool_names
    assert "create_deck" in tool_names


@pytest.mark.asyncio
async def test_call_tool_list_notes_filters_by_deck() -> None:
    client = FakeMochiClient()
    server = create_server(client, read_only=True)
    req = types.CallToolRequest(
        params=types.CallToolRequestParams(name="list_notes", arguments={"deck_id": "deck-1"})
    )
    result = await server.request_handlers[types.CallToolRequest](req)
    structured = result.root.structuredContent
    assert structured is not None
    assert {note["id"] for note in structured["notes"]} == {"note-1"}


@pytest.mark.asyncio
async def test_write_tool_delete_note_records_action() -> None:
    client = FakeMochiClient()
    server = create_server(client, read_only=False)
    req = types.CallToolRequest(
        params=types.CallToolRequestParams(name="delete_note", arguments={"note_id": "note-1"})
    )
    result = await server.request_handlers[types.CallToolRequest](req)
    assert result.root.structuredContent == {"status": "deleted", "note_id": "note-1"}
    assert client.deleted_notes == ["note-1"]


@pytest.mark.asyncio
async def test_read_resource_returns_json() -> None:
    client = FakeMochiClient()
    server = create_server(client, read_only=True)
    req = types.ReadResourceRequest(params=types.ReadResourceRequestParams(uri="mochi://deck/deck-1"))
    result = await server.request_handlers[types.ReadResourceRequest](req)
    text = result.root.contents[0].text
    assert "deck-1" in text
