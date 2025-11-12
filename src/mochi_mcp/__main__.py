"""Command line entry point for the Mochi MCP server."""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from .api import MochiClient, MochiAPIError
from .config import MochiServerSettings
from .server import create_server, run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Mochi MCP server over stdio.")
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Enable write tools (create/update/delete). Defaults to read-only mode.",
    )
    parser.add_argument(
        "--base-url",
        help="Override the Mochi API base URL (defaults to https://api.mochi.cards/v1).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        help="HTTP timeout in seconds for API requests.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> None:
    try:
        settings = MochiServerSettings()
    except ValidationError as exc:
        raise SystemExit(_format_validation_error(exc)) from exc

    updates: dict[str, Any] = {}
    if args.base_url:
        updates["base_url"] = args.base_url
    if args.timeout is not None:
        updates["request_timeout"] = args.timeout
    if updates:
        settings = settings.model_copy(update=updates)
    if args.allow_write:
        settings = settings.with_write_enabled()

    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    async with MochiClient(
        settings.api_key,
        base_url=str(settings.base_url),
        timeout=settings.request_timeout,
    ) as client:
        server = create_server(client, read_only=settings.read_only)
        await run_server(server)


def _format_validation_error(exc: ValidationError) -> str:
    messages = ["Configuration error:"]
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", []))
        msg = error.get("msg", "Invalid value")
        messages.append(f"  - {loc or 'value'}: {msg}")
    return "\n".join(messages)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_async_main(args))
    except MochiAPIError as exc:
        logging.error("Mochi API error: %s", exc)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        logging.info("Shutting down Mochi MCP server")


if __name__ == "__main__":
    main()
