import tomllib
from pathlib import Path

CONFIG_DIR = Path("~/.ayder").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.toml"

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


def load_config() -> dict:
    """Load config from ~/.ayder/config.toml, creating it with defaults if missing."""
    config = dict(DEFAULTS)

    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fmt = {**DEFAULTS, "verbose_str": str(DEFAULTS["verbose"]).lower()}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(_DEFAULT_TOML.format(**fmt))
        return config

    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    llm = data.get("llm", {})
    for key in ["base_url", "api_key", "model", "num_ctx"]:
        if key in llm:
            config[key] = llm[key]
    
    editor = data.get("editor", {})
    if "editor" in editor:
        config["editor"] = editor["editor"]

    ui = data.get("ui", {})
    if "verbose" in ui:
        config["verbose"] = bool(ui["verbose"])

    return config
