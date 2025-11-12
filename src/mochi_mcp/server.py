"""Server wiring for the Mochi MCP integration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from mcp import types
from mcp.server import NotificationOptions, Server
from mcp.server import stdio
from mcp.server.lowlevel.helper_types import ReadResourceContents

from .api import MochiAPIError, MochiClient

LOGGER = logging.getLogger(__name__)

_DECK_URI_PREFIX = "mochi://deck/"
_MAX_DECK_RESOURCES = 500


@dataclass(slots=True)
class _ParsedResourceUri:
    kind: str
    identifier: str


def create_server(client: MochiClient, *, read_only: bool = True) -> Server:
    """Create and configure the MCP server."""

    instructions = [
        "Interact with the Mochi flashcard API through MCP tools.",
        "The server authenticates with the API using the configured MOCHI_API_KEY.",
    ]
    if read_only:
        instructions.append("Write operations are disabled; only read-only tools are available.")
    else:
        instructions.append("Write tools are enabled; use destructive operations carefully.")

    server = Server(
        name="mochi-mcp",
        instructions="\n".join(instructions),
        website_url="https://mochi.cards",
    )

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        LOGGER.debug("Listing decks for resource catalog")
        resources: list[types.Resource] = []
        cursor: str | None = None

        while True:
            page = await client.list_decks(cursor=cursor, limit=200)
            for deck in page.items:
                if _deck_identifier(deck):
                    resources.append(_deck_to_resource(deck))
            if not page.next_cursor or len(resources) >= _MAX_DECK_RESOURCES:
                break
            cursor = page.next_cursor

        return resources[:_MAX_DECK_RESOURCES]

    @server.read_resource()
    async def read_resource(uri: Any):
        parsed = _parse_resource_uri(str(uri))
        if parsed.kind == "deck":
            payload = await client.get_deck(parsed.identifier)
        elif parsed.kind == "note":
            payload = await client.get_note(parsed.identifier)
        else:  # pragma: no cover - guarded by parser
            raise ValueError(f"Unsupported resource URI: {uri}")
        content = json.dumps(payload, indent=2, sort_keys=True)
        return [ReadResourceContents(content=content, mime_type="application/json")]

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        tools: list[types.Tool] = [
            _tool_definition(
                "list_decks",
                "List decks from the authenticated Mochi workspace.",
                {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "description": "Maximum number of decks to return.",
                        },
                        "cursor": {
                            "type": "string",
                            "description": "Cursor returned by a previous list_decks call.",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            _tool_definition(
                "get_deck",
                "Fetch metadata about a single deck by identifier.",
                {
                    "type": "object",
                    "properties": {
                        "deck_id": {
                            "type": "string",
                            "description": "Deck identifier (id or slug).",
                        }
                    },
                    "required": ["deck_id"],
                    "additionalProperties": False,
                },
            ),
            _tool_definition(
                "list_notes",
                "List notes/cards from Mochi. Optionally scope to a deck or search query.",
                {
                    "type": "object",
                    "properties": {
                        "deck_id": {
                            "type": "string",
                            "description": "Only return notes that belong to this deck.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Full text search term.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "description": "Maximum number of notes to return.",
                        },
                        "cursor": {
                            "type": "string",
                            "description": "Cursor returned by a previous list_notes call.",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            _tool_definition(
                "get_note",
                "Fetch a single note/card by identifier.",
                {
                    "type": "object",
                    "properties": {
                        "note_id": {
                            "type": "string",
                            "description": "Note identifier.",
                        }
                    },
                    "required": ["note_id"],
                    "additionalProperties": False,
                },
            ),
        ]

        if not read_only:
            tools.extend(
                [
                    _tool_definition(
                        "create_deck",
                        "Create a new deck in Mochi.",
                        {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Name of the deck."},
                                "description": {
                                    "type": "string",
                                    "description": "Optional deck description.",
                                },
                                "parent_deck_id": {
                                    "type": "string",
                                    "description": "Optional parent deck identifier.",
                                },
                                "fields": {
                                    "type": "object",
                                    "description": "Additional raw fields to merge into the request body.",
                                },
                            },
                            "required": ["name"],
                            "additionalProperties": False,
                        },
                        annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=False),
                    ),
                    _tool_definition(
                        "update_deck",
                        "Update fields on an existing deck.",
                        {
                            "type": "object",
                            "properties": {
                                "deck_id": {"type": "string", "description": "Deck identifier."},
                                "fields": {
                                    "type": "object",
                                    "description": "Fields to update on the deck payload.",
                                },
                            },
                            "required": ["deck_id", "fields"],
                            "additionalProperties": False,
                        },
                        annotations=types.ToolAnnotations(readOnlyHint=False),
                    ),
                    _tool_definition(
                        "delete_deck",
                        "Delete a deck and its notes.",
                        {
                            "type": "object",
                            "properties": {
                                "deck_id": {"type": "string", "description": "Deck identifier."}
                            },
                            "required": ["deck_id"],
                            "additionalProperties": False,
                        },
                        annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=True),
                    ),
                    _tool_definition(
                        "create_note",
                        "Create a new note/card in Mochi.",
                        {
                            "type": "object",
                            "properties": {
                                "deck_id": {"type": "string", "description": "Deck to add the note to."},
                                "fields": {
                                    "type": "object",
                                    "description": "Payload describing the note fields (front/back, etc).",
                                },
                            },
                            "required": ["deck_id", "fields"],
                            "additionalProperties": False,
                        },
                        annotations=types.ToolAnnotations(readOnlyHint=False),
                    ),
                    _tool_definition(
                        "update_note",
                        "Update an existing note/card.",
                        {
                            "type": "object",
                            "properties": {
                                "note_id": {"type": "string", "description": "Note identifier."},
                                "fields": {
                                    "type": "object", "description": "Fields to update on the note."},
                            },
                            "required": ["note_id", "fields"],
                            "additionalProperties": False,
                        },
                        annotations=types.ToolAnnotations(readOnlyHint=False),
                    ),
                    _tool_definition(
                        "delete_note",
                        "Delete a note/card.",
                        {
                            "type": "object",
                            "properties": {
                                "note_id": {"type": "string", "description": "Note identifier."}
                            },
                            "required": ["note_id"],
                            "additionalProperties": False,
                        },
                        annotations=types.ToolAnnotations(readOnlyHint=False, destructiveHint=True),
                    ),
                ]
            )

        return tools

    @server.call_tool()
    async def call_tool(tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        match tool_name:
            case "list_decks":
                result = await client.list_decks(
                    cursor=_optional_str(arguments.get("cursor")),
                    limit=_optional_int(arguments.get("limit")),
                )
                return result.to_payload("decks")
            case "get_deck":
                deck_id = _require_str(arguments, "deck_id")
                deck = await client.get_deck(deck_id)
                return {"deck": deck}
            case "list_notes":
                result = await client.list_notes(
                    deck_id=_optional_str(arguments.get("deck_id")),
                    cursor=_optional_str(arguments.get("cursor")),
                    limit=_optional_int(arguments.get("limit")),
                    query=_optional_str(arguments.get("query")),
                )
                return result.to_payload("notes")
            case "get_note":
                note_id = _require_str(arguments, "note_id")
                note = await client.get_note(note_id)
                return {"note": note}

        if read_only:
            raise MochiAPIError(f"Unknown tool: {tool_name}")

        match tool_name:
            case "create_deck":
                payload = {
                    "name": _require_str(arguments, "name"),
                }
                if description := _optional_str(arguments.get("description")):
                    payload["description"] = description
                if parent := _optional_str(arguments.get("parent_deck_id")):
                    payload["parentDeckId"] = parent
                if "fields" in arguments:
                    payload.update(_require_mapping(arguments, "fields"))
                deck = await client.create_deck(payload)
                return {"deck": deck}
            case "update_deck":
                deck_id = _require_str(arguments, "deck_id")
                fields = _require_mapping(arguments, "fields")
                deck = await client.update_deck(deck_id, fields)
                return {"deck": deck}
            case "delete_deck":
                deck_id = _require_str(arguments, "deck_id")
                await client.delete_deck(deck_id)
                return {"status": "deleted", "deck_id": deck_id}
            case "create_note":
                deck_id = _require_str(arguments, "deck_id")
                fields = _require_mapping(arguments, "fields")
                payload = dict(fields)
                payload["deckId"] = deck_id
                note = await client.create_note(payload)
                return {"note": note}
            case "update_note":
                note_id = _require_str(arguments, "note_id")
                fields = _require_mapping(arguments, "fields")
                note = await client.update_note(note_id, fields)
                return {"note": note}
            case "delete_note":
                note_id = _require_str(arguments, "note_id")
                await client.delete_note(note_id)
                return {"status": "deleted", "note_id": note_id}

        raise MochiAPIError(f"Unknown tool: {tool_name}")

    return server


async def run_server(server: Server) -> None:
    """Run the server over stdio."""

    initialization_options = server.create_initialization_options(NotificationOptions())
    async with stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, initialization_options)


def _deck_identifier(deck: Mapping[str, Any]) -> str | None:
    for key in ("id", "uuid", "slug"):
        value = deck.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, int):
            return str(value)
    return None


def _deck_to_resource(deck: Mapping[str, Any]) -> types.Resource:
    identifier = _deck_identifier(deck)
    if not identifier:
        raise MochiAPIError("Deck payload is missing an identifier")
    name = str(deck.get("name") or deck.get("title") or identifier)
    description = deck.get("description")
    annotations = types.Annotations(priority=0.5) if description else None
    return types.Resource(
        name=name,
        uri=f"{_DECK_URI_PREFIX}{identifier}",
        description=str(description) if isinstance(description, str) else None,
        annotations=annotations,
    )


def _parse_resource_uri(uri: str) -> _ParsedResourceUri:
    parsed = urlparse(uri)
    if parsed.scheme != "mochi" or not parsed.netloc:
        raise ValueError(f"Unsupported Mochi resource URI: {uri}")
    identifier = parsed.path.lstrip("/")
    if not identifier:
        raise ValueError(f"Missing identifier in resource URI: {uri}")
    return _ParsedResourceUri(kind=parsed.netloc, identifier=identifier)


def _optional_str(value: Any) -> str | None:
    return str(value) if isinstance(value, (str, int)) and value != "" else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Expected integer, received {value!r}") from exc
    return None


def _require_str(arguments: Mapping[str, Any], field: str) -> str:
    value = arguments.get(field)
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int):
        return str(value)
    raise ValueError(f"Field '{field}' is required and must be a string")


def _require_mapping(arguments: Mapping[str, Any], field: str) -> dict[str, Any]:
    value = arguments.get(field)
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"Field '{field}' must be an object containing fields to send to Mochi")


def _tool_definition(
    name: str,
    description: str,
    input_schema: Mapping[str, Any],
    *,
    annotations: types.ToolAnnotations | None = None,
) -> types.Tool:
    annotations = annotations or types.ToolAnnotations(readOnlyHint=True)
    return types.Tool(
        name=name,
        description=description,
        inputSchema=dict(input_schema),
        annotations=annotations,
    )


__all__ = ["create_server", "run_server"]
