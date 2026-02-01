import tomllib
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

CONFIG_DIR = Path("~/.ayder").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.toml"

# Backwards compatibility: Keep DEFAULTS dictionary
DEFAULTS = {
    "base_url": "http://localhost:11434/v1",
    "api_key": "ollama",
    "model": "qwen3-coder:latest",
    "num_ctx": 65536,
    "editor": "vim",
    "verbose": False,
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
"""


class Config(BaseModel):
    """Configuration model with validation."""
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen3-coder:latest"
    num_ctx: int = 65536
    editor: str = "vim"
    verbose: bool = False

    @field_validator("num_ctx")
    @classmethod
    def validate_num_ctx(cls, v: int) -> int:
        """Validate that num_ctx is positive."""
        if v <= 0:
            raise ValueError("num_ctx must be positive")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate that base_url looks like a valid URL."""
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
        data = tomllib.load(f)

    # Build config dict from loaded data
    config_dict = {}

    llm = data.get("llm", {})
    for key in ["base_url", "api_key", "model", "num_ctx"]:
        if key in llm:
            config_dict[key] = llm[key]

    editor = data.get("editor", {})
    if "editor" in editor:
        config_dict["editor"] = editor["editor"]

    ui = data.get("ui", {})
    if "verbose" in ui:
        config_dict["verbose"] = bool(ui["verbose"])

    # Create Config instance with loaded values, defaults will be used for missing values
    return Config(**config_dict)
