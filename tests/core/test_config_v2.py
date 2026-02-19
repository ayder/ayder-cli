"""Tests for v2 configuration parsing."""

import pytest

from ayder_cli.core.config import Config, load_config, load_config_for_provider


def test_load_v2_parses_app_and_logging_sections(tmp_path, monkeypatch):
    config_dir = tmp_path / ".ayder"
    config_path = config_dir / "config.toml"
    config_dir.mkdir()
    config_path.write_text(
        """config_version = "2.0"

[app]
provider = "deepseek"
editor = "nano"
verbose = true
max_background_processes = 9
max_iterations = 42

[logging]
file_enabled = false
file_path = "logs/ayder.log"
rotation = "5 MB"
retention = "14 days"

[llm.deepseek]
driver = "openai"
base_url = "https://api.deepseek.com/v1"
api_key = "sk-deepseek"
model = "deepseek-chat"
num_ctx = 65536
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", config_path)

    cfg = load_config()
    assert cfg.provider == "deepseek"
    assert cfg.driver == "openai"
    assert cfg.editor == "nano"
    assert cfg.verbose is True
    assert cfg.max_background_processes == 9
    assert cfg.max_iterations == 42
    assert cfg.logging_file_enabled is False
    assert cfg.logging_file_path == "logs/ayder.log"
    assert cfg.model == "deepseek-chat"


def test_invalid_driver_raises_descriptive_error():
    with pytest.raises(ValueError, match="driver must be one of"):
        Config(
            app={"provider": "broken"},
            llm={
                "broken": {
                    "driver": "not-a-driver",
                    "api_key": "x",
                    "model": "m",
                    "num_ctx": 1024,
                }
            },
        )


def test_load_config_for_provider_uses_v2_profile(tmp_path, monkeypatch):
    config_dir = tmp_path / ".ayder"
    config_path = config_dir / "config.toml"
    config_dir.mkdir()
    config_path.write_text(
        """config_version = "2.0"

[app]
provider = "openai"
editor = "vim"
verbose = false
max_background_processes = 5
max_iterations = 50

[llm.openai]
driver = "openai"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "qwen3-coder:latest"
num_ctx = 65536

[llm.anthropic]
driver = "anthropic"
api_key = "sk-ant"
model = "claude-sonnet-4-5-20250929"
num_ctx = 8192
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", config_path)

    cfg = load_config_for_provider("anthropic")
    assert cfg.provider == "anthropic"
    assert cfg.driver == "anthropic"
    assert cfg.api_key == "sk-ant"
    assert cfg.model == "claude-sonnet-4-5-20250929"
