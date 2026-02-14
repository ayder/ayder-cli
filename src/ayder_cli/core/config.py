import tomllib
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Any, Dict, Optional

CONFIG_DIR = Path("~/.ayder").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.toml"

# Maintained for test compatibility and initial file generation
DEFAULTS: Dict[str, Any] = {
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "qwen3-coder:latest",
    "num_ctx": 65536,
    "editor": "vim",
    "verbose": False,
    "max_background_processes": 5,
    "max_iterations": 50,
}

_DEFAULT_TOML = """\
[llm]
base_url = "{base_url}"
api_key = "{api_key}"
model = "{model}"
num_ctx = {num_ctx}

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

    base_url: str = Field(default="http://localhost:11434/v1")
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
        """Flatten nested TOML sections ([llm], [editor], [ui]) into flat fields."""
        if not isinstance(data, dict):
            return data

        new_data = data.copy()
        # Pull values from known sections
        for section in ["llm", "editor", "ui", "agent"]:
            if section in data and isinstance(data[section], dict):
                section_data = new_data.pop(section)
                new_data.update(section_data)

        return new_data

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
    def validate_base_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


def load_config() -> Config:
    """Load config from ~/.ayder/config.toml, creating it with defaults if missing."""
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fmt = {**DEFAULTS, "verbose_str": str(DEFAULTS["verbose"]).lower()}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_TOML.format(**fmt))
        return Config()

    with open(CONFIG_PATH, "rb") as f:
        try:
            data = tomllib.load(f)
            return Config(**data)
        except Exception:
            return Config()
