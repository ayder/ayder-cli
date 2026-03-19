"""AgentConfig — Pydantic model for agent definitions."""

from pydantic import BaseModel, ConfigDict


class AgentConfig(BaseModel):
    """Configuration for a single agent, parsed from [agents.<name>] TOML sections."""

    model_config = ConfigDict(frozen=True)

    name: str
    provider: str | None = None      # None = inherit from main config
    model: str | None = None         # None = inherit from main config
    system_prompt: str = ""
