"""AgentConfig — Pydantic model for agent definitions."""

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class AgentConfig(BaseModel):
    """Configuration for a single agent, parsed from [agents.<name>] TOML sections.

    Connection-level fields (base_url, api_key, num_ctx, temperature, think,
    driver) are optional; when set they override the values pulled from the
    parent provider profile. This lets one agent target an entirely different
    endpoint than the main session without needing a separate [llm.<name>]
    profile.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    provider: str | None = None
    model: str | None = None
    system_prompt: str = ""

    base_url: str | None = None
    api_key: str | None = None
    driver: str | None = None
    num_ctx: int | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    think: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_aliases(cls, data: Any) -> Any:
        """Accept ``thinking`` as an alias for ``think`` and coerce numeric strings."""
        if not isinstance(data, dict):
            return data
        new_data = dict(data)
        if "thinking" in new_data and "think" not in new_data:
            new_data["think"] = new_data.pop("thinking")
        for key in ("temperature",):
            val = new_data.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    new_data[key] = float(val)
                except ValueError:
                    pass
        for key in ("num_ctx", "max_output_tokens"):
            val = new_data.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    new_data[key] = int(val)
                except ValueError:
                    pass
        return new_data

    def overrides(self) -> dict[str, Any]:
        """Return non-None connection-level fields suitable for cfg.model_copy()."""
        out: dict[str, Any] = {}
        for field in (
            "model",
            "base_url",
            "api_key",
            "driver",
            "num_ctx",
            "temperature",
            "max_output_tokens",
            "think",
        ):
            value = getattr(self, field)
            if value is not None:
                out[field] = value
        return out
