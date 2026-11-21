"""The first-run config.toml and the wizard's Claude preset use current Claude defaults."""

import tomllib

from ayder_cli.core import config as config_module
from ayder_cli.core.config import DEFAULTS
from ayder_cli.core.config_editor import PRESETS
from ayder_cli.core.config_migration import ensure_latest_config


def test_first_run_anthropic_profile(tmp_path, monkeypatch):
    path = tmp_path / ".ayder" / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    ensure_latest_config(path, defaults=DEFAULTS)

    profile = tomllib.loads(path.read_text(encoding="utf-8"))["llm"]["anthropic"]

    assert profile == {
        "driver": "anthropic",
        "api_key": "",
        "model": "claude-sonnet-5-5",
        "num_ctx": 200000,
    }


def test_claude_preset_matches():
    preset = PRESETS["anthropic"]

    assert (preset.model, preset.num_ctx) == ("claude-sonnet-5-5", 200000)
