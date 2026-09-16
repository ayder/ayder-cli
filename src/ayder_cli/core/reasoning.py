"""Reasoning settings shared by LLM profiles, agents, and runtime commands."""

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator

OPENAI_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
# The Ollama Python SDK accepts these levels plus booleans. Its request model
# does not yet accept the server API's newer "max" value.
OLLAMA_EFFORTS = ("none", "low", "medium", "high")


def get_effort_label(config: Any) -> str:
    """Return the configured effort for the picker and status bar."""
    values = config if isinstance(config, dict) else vars(config)
    driver = values.get("driver", "openai")
    if driver not in {"openai", "ollama"}:
        return "n/a"
    effort = values.get("reasoning_effort")
    if isinstance(effort, str) and effort != "default":
        return "off" if driver == "ollama" and effort == "none" else effort
    if driver == "ollama":
        think = values.get("think", True)
        if isinstance(think, bool):
            return "on" if think else "off"
        if isinstance(think, str):
            return think
    return "default"


def normalize_effort(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip().lower()
        if value == "default":
            return None
    return value


def normalize_think(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "yes", "on", "1"}:
            return True
        if value in {"false", "no", "off", "0"}:
            return False
    if value is None or isinstance(value, (str, bool)):
        return value
    raise ValueError("think must be true, false, low, medium, high, or null")


ReasoningEffort = Annotated[
    Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None,
    BeforeValidator(normalize_effort),
]
ThinkOption = Annotated[
    bool | Literal["low", "medium", "high"] | None,
    BeforeValidator(normalize_think),
]


def validate_effort(driver: str, effort: str | None) -> None:
    """Reject unsupported Ollama SDK levels after resolving the profile."""
    if driver == "ollama" and effort is not None and effort not in OLLAMA_EFFORTS:
        raise ValueError(
            "Ollama reasoning_effort must be default, none, low, medium, or high"
        )
