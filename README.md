# mochi-mcp

An [MCP](https://modelcontextprotocol.io/) server that connects AI agents to the [Mochi flashcard app](https://mochi.cards/).
It exposes read-only tools by default so agents can safely explore decks and notes without mutating your data. Passing the
`--allow-write` flag enables the write tools (create, update, delete).

## Features

- Lists decks as MCP resources and renders deck/note payloads when requested.
- Read-only tools for listing decks and notes or fetching a specific deck/note.
- Optional write tools (gated behind `--allow-write`) for creating, updating, and deleting decks or notes.
- Configurable via environment variables with validation provided by Pydantic settings.

## Installation

Create a virtual environment and install the project with its dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Configuration

Set the `MOCHI_API_KEY` environment variable with the API key found in your Mochi account. Optional overrides:

- `MOCHI_BASE_URL` — change the API base URL (defaults to `https://api.mochi.cards/v1`).
- `MOCHI_REQUEST_TIMEOUT` — change the HTTP timeout (seconds, defaults to `30`).

You can also pass `--base-url` and `--timeout` via the CLI for ad-hoc overrides.

## Running the server

The entry point exposes an stdio MCP server:

```bash
mochi-mcp              # read-only mode (default)
mochi-mcp --allow-write  # enable write tools
```

When write tools are enabled, the server marks destructive tools with appropriate annotations so capable agents
understand the risk.

## Development

Run the unit test suite with `pytest`:

```bash
pytest
```

## Testing notes

The test suite uses `httpx`'s mock transport to avoid making live network calls. This keeps tests deterministic and means
you do not need a live Mochi API key to run them.
