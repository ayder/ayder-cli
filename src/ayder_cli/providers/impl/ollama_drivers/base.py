"""Base interface for per-family Ollama chat drivers.

Each driver owns one model family's prompt template, parser, and detection.
Drivers are independent: adding, modifying, or removing one should not
require edits to other drivers, the registry, or the provider.

See docs/superpowers/specs/2026-05-02-ollama-chat-drivers-design.md section 6.1.
"""

from __future__ import annotations

from abc import ABC
from enum import Enum
from typing import Any, ClassVar

from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


class DriverMode(Enum):
    NATIVE = "native"
    IN_CONTENT = "in_content"


class ChatDriver(ABC):
    """Per-family driver for Ollama tool-calling quirks."""

    name: ClassVar[str]
    mode: ClassVar[DriverMode]
    priority: ClassVar[int] = 100
    abstract: ClassVar[bool] = False
    supports_families: ClassVar[tuple[str, ...]] = ()
    fallback_driver: ClassVar[str | None] = None

    @classmethod
    def supports(cls, model_info: ModelInfo) -> bool:
        """Default case-insensitive substring match on model family."""
        family = (model_info.family or "").lower()
        return any(f.lower() in family for f in cls.supports_families)

    def render_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Inject tool schemas into messages for in-content drivers."""
        return messages

    def parse_tool_calls(self, content: str, reasoning: str) -> list[ToolCallDef]:
        """Extract tool calls from model output for in-content drivers."""
        return []

    def display_filter(self) -> Any:
        """Return a fresh stateful display filter, or None when unused."""
        return None
