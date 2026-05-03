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
    # qwen3 / qwen2: native tool extraction works on current Ollama. Earlier
    # Ollama crashed with "XML syntax error: unexpected EOF" on truncated qwen3
    # output (#14834). Injecting our own <tools>/<tool_call> XML into the system
    # prompt instead causes bare-EOF mid-stream because Ollama's qwen3 template
    # scans the prompt. If #14834 returns, OllamaServerToolBug classification
    # engages reactive fallback (generic_native -> generic_xml).
    ResolutionRule(
        family_substring="qwen3",
        driver="generic_native",
        note="Native tool extraction works; reactive fallback to generic_xml on #14834",
    ),
    ResolutionRule(
        family_substring="qwen2",
        driver="generic_native",
        note="Same routing as qwen3",
    ),
    # deepseek: native tool extraction confirmed working on current Ollama
    # (verified empirically against deepseek-v4-pro:cloud — returns empty
    # content + populated msg.tool_calls). Earlier deepseek-r1/v3 reportedly
    # leaked <function_calls><invoke> blocks into msg.content; our IN_CONTENT
    # routing then made the model emit <｜DSML｜tool_calls> wrappers, which
    # display-leaked. Trusting native; reactive fallback engages on #14834.
    # If a specific deepseek variant regresses, prefer the model-name-specific
    # driver (priority < 50) over re-engaging the family-wide IN_CONTENT path.
    ResolutionRule(
        family_substring="deepseek",
        driver="generic_native",
        note="Native works on current Ollama; verified for deepseek-v4-pro:cloud",
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
