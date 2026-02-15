import tomllib
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Any, Dict

CONFIG_DIR = Path("~/.ayder").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.toml"

# Maintained for test compatibility and initial file generation
DEFAULTS: Dict[str, Any] = {
    "provider": "openai",
    "openai": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "model": "qwen3-coder:latest",
        "num_ctx": 65536,
    },
    "anthropic": {
        "api_key": "",
        "model": "claude-sonnet-4-5-20250929",
        "num_ctx": 8192,
    },
    "gemini": {
        "api_key": "",
        "model": "gemini-2.0-flash",
        "num_ctx": 65536,
    },
    "editor": "vim",
    "verbose": False,
    "max_background_processes": 5,
    "max_iterations": 50,
}

_PROVIDER_SECTIONS = ("openai", "anthropic", "gemini")

_DEFAULT_TOML = """\
# Active provider: "openai", "anthropic", or "gemini"
provider = "{provider}"

[openai]
base_url = "{openai_base_url}"
api_key = "{openai_api_key}"
model = "{openai_model}"
num_ctx = {openai_num_ctx}

[anthropic]
api_key = "{anthropic_api_key}"
model = "{anthropic_model}"
num_ctx = {anthropic_num_ctx}

[gemini]
api_key = "{gemini_api_key}"
model = "{gemini_model}"
num_ctx = {gemini_num_ctx}

[editor]
# Editor to use for /task-edit command (vim, nano, pico, etc.)
editor = "{editor}"

[ui]
# Show written file contents after write_file tool calls (true/false)
verbose = {verbose_str}

[agent]
# Maximum agentic iterations (tool calls) per user message
max_iterations = {max_iterations}
"""


class Config(BaseModel):
    """Unified configuration model with validation."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    provider: str = Field(default="openai")
    base_url: str | None = Field(default="http://localhost:11434/v1")
    api_key: str = Field(default="ollama")
    model: str = Field(default="qwen3-coder:latest")
    num_ctx: int = Field(default=65536)
    editor: str = Field(default="vim")
    verbose: bool = Field(default=False)
    max_background_processes: int = Field(default=5)
    max_iterations: int = Field(default=50)

    @model_validator(mode="before")
    @classmethod
    def flatten_nested_sections(cls, data: Any) -> Any:
        """Flatten nested TOML sections into flat fields.

        Handles provider sections ([openai], [anthropic], [gemini]),
        legacy [llm] section, and utility sections ([editor], [ui], [agent]).
        The active provider section's fields are merged into the top level.
        """
        if not isinstance(data, dict):
            return data

        new_data = data.copy()

        # Determine active provider
        provider = new_data.get("provider", "openai")

        # Merge active provider section into flat config
        if provider in _PROVIDER_SECTIONS and provider in data and isinstance(data[provider], dict):
            new_data.update(new_data.pop(provider))

        # Discard non-active provider sections
        for p in _PROVIDER_SECTIONS:
            new_data.pop(p, None)

        # Backward compat: flatten legacy [llm] section
        if "llm" in data and isinstance(data["llm"], dict):
            section_data = new_data.pop("llm")
            new_data.update(section_data)

        # Flatten utility sections
        for section in ["editor", "ui", "agent"]:
            if section in data and isinstance(data[section], dict):
                section_data = new_data.pop(section)
                new_data.update(section_data)

        return new_data

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in ("openai", "anthropic", "gemini"):
            raise ValueError("provider must be 'openai', 'anthropic', or 'gemini'")
        return v

    @field_validator("num_ctx")
    @classmethod
    def validate_num_ctx(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("num_ctx must be positive")
        return v

    @field_validator("max_background_processes")
    @classmethod
    def validate_max_background_processes(cls, v: int) -> int:
        if v < 1 or v > 20:
            raise ValueError("max_background_processes must be between 1 and 20")
        return v

    @field_validator("max_iterations")
    @classmethod
    def validate_max_iterations(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("max_iterations must be between 1 and 100")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


def load_config_for_provider(provider: str) -> Config:
    """Load config from ~/.ayder/config.toml with a specific provider active.

    Re-reads the TOML file and overrides the provider key before flattening,
    so the returned Config has the chosen provider's settings merged in.
    """
    if not CONFIG_PATH.exists():
        return Config(provider=provider)

    with open(CONFIG_PATH, "rb") as f:
        try:
            data = tomllib.load(f)
        except Exception:
            return Config(provider=provider)

    data["provider"] = provider
    return Config(**data)


def load_config() -> Config:
    """Load config from ~/.ayder/config.toml, creating it with defaults if missing."""
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fmt: Dict[str, Any] = {
            "provider": DEFAULTS["provider"],
            "editor": DEFAULTS["editor"],
            "verbose_str": str(DEFAULTS["verbose"]).lower(),
            "max_iterations": DEFAULTS["max_iterations"],
        }
        for p in _PROVIDER_SECTIONS:
            for k, v in DEFAULTS[p].items():
                fmt[f"{p}_{k}"] = v
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_TOML.format(**fmt))
        return Config()

    with open(CONFIG_PATH, "rb") as f:
        try:
            data = tomllib.load(f)
            return Config(**data)
        except Exception:
            return Config()
