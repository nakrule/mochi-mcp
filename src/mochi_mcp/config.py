"""Configuration helpers for the Mochi MCP server."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class MochiServerSettings(BaseSettings):
    """Settings that control how the MCP server connects to Mochi."""

    model_config = SettingsConfigDict(env_prefix="MOCHI_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: Annotated[str, Field(description="API key used to authenticate with Mochi.")]
    base_url: Annotated[
        HttpUrl,
        Field(
            default="https://api.mochi.cards/v1",
            description="Base URL for the Mochi API.",
        ),
    ]
    read_only: Annotated[
        bool,
        Field(
            default=True,
            description="When true the server only exposes read-only tools.",
        ),
    ]
    request_timeout: Annotated[
        float,
        Field(
            default=30.0,
            description="HTTP timeout (seconds) for requests to the Mochi API.",
            gt=0,
        ),
    ]

    def with_write_enabled(self) -> "MochiServerSettings":
        """Return a copy of the settings with write operations enabled."""

        return self.model_copy(update={"read_only": False})


__all__ = ["MochiServerSettings"]
