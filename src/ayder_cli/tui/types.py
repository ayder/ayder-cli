"""Shared types for the TUI package."""

from dataclasses import dataclass
from enum import Enum


class MessageType(Enum):
    """Types of chat messages."""

    USER = "user"
    ASSISTANT = "assistant"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"


@dataclass
class ConfirmResult:
    """Result from a tool confirmation screen."""

    action: str  # "approve", "deny", "instruct"
    instructions: str | None = None
