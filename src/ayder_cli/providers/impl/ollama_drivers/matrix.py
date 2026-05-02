"""Resolution matrix for Ollama chat drivers.

This module contains an ordered list of matcher-to-driver mappings. The
DriverRegistry walks the list top-to-bottom and the first matching row wins.
Rows should be added only for observed model behavior with paired tests.
Custom-trained forks should usually provide a driver subclass with a custom
supports() method instead of adding a matrix row.
"""

from __future__ import annotations

from dataclasses import dataclass

from ayder_cli.providers.impl.ollama_inspector import ModelInfo


@dataclass(frozen=True)
class ResolutionRule:
    """One row in the built-in resolution matrix.

    Matchers are AND-combined. None means this dimension is not checked.
    At least one matcher must be specified.
    """

    family_substring: str | None = None
    name_substring: str | None = None
    requires_capability: str | None = None
    driver: str = "generic_native"
    note: str = ""

    def __post_init__(self) -> None:
        if not any(
            [self.family_substring, self.name_substring, self.requires_capability]
        ):
            raise ValueError("ResolutionRule needs at least one matcher dimension")

    def matches(self, info: ModelInfo) -> bool:
        family = (info.family or "").lower()
        name = (info.name or "").lower()
        if self.family_substring and self.family_substring.lower() not in family:
            return False
        if self.name_substring and self.name_substring.lower() not in name:
            return False
        if self.requires_capability and self.requires_capability not in info.capabilities:
            return False
        return True


RESOLUTION_MATRIX: tuple[ResolutionRule, ...] = (
    ResolutionRule(
        family_substring="qwen3",
        driver="qwen3",
        note="Ollama #14834: native tools path crashes on truncated XML output",
    ),
    ResolutionRule(
        family_substring="qwen2",
        driver="qwen3",
        note="Same training format as qwen3; reuses qwen3 driver",
    ),
    ResolutionRule(
        family_substring="deepseek",
        driver="deepseek",
        note="Emits function_calls invoke blocks in message content",
    ),
    ResolutionRule(
        family_substring="minimax",
        driver="minimax",
        note="Emits namespaced minimax tool_call blocks in message content",
    ),
    ResolutionRule(family_substring="llama", driver="generic_native"),
    ResolutionRule(family_substring="mistral", driver="generic_native"),
    ResolutionRule(family_substring="gemma", driver="generic_native"),
    ResolutionRule(family_substring="phi", driver="generic_native"),
    ResolutionRule(family_substring="granite", driver="generic_native"),
    ResolutionRule(
        requires_capability="tools",
        driver="generic_native",
        note="Trust native extraction for unknown tools-capable families",
    ),
)
