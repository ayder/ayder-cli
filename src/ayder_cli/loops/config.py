"""Unified loop configuration for CLI and TUI agent loops."""

from dataclasses import dataclass, field


@dataclass
class LoopConfig:
    """Shared configuration for both CLI and TUI agent loops.

    Both ``chat_loop.LoopConfig`` and ``tui.chat_loop.TuiLoopConfig`` are
    compatible with this dataclass (same fields, different defaults).
    """

    model: str = "qwen3-coder:latest"
    num_ctx: int = 65536
    max_output_tokens: int = 4096
    stop_sequences: list = field(default_factory=list)
    max_iterations: int = 50
    verbose: bool = False
    permissions: set = field(default_factory=set)
    tool_tags: frozenset | None = None
