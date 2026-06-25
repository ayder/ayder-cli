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


def test_set_config_path_redirects_load_config(tmp_path, monkeypatch):
    """set_config_path() makes load_config() read from a custom path (the -c flag)."""
    import ayder_cli.core.config as config_mod

    # Snapshot the module globals so they are restored at teardown even though
    # set_config_path mutates them directly via `global`.
    monkeypatch.setattr(config_mod, "CONFIG_PATH", config_mod.CONFIG_PATH)
    monkeypatch.setattr(config_mod, "CONFIG_DIR", config_mod.CONFIG_DIR)

    custom = tmp_path / "custom-config" / "ayder.toml"
    custom.parent.mkdir()
    custom.write_text(
        """config_version = "2.0"

[app]
provider = "deepseek"

[llm.deepseek]
driver = "openai"
base_url = "https://api.deepseek.com/v1"
api_key = "sk-custom"
model = "deepseek-custom"
num_ctx = 4096
""",
        encoding="utf-8",
    )

    config_mod.set_config_path(custom)

    assert config_mod.CONFIG_PATH == custom.resolve()
    assert config_mod.CONFIG_DIR == custom.resolve().parent

    cfg = config_mod.load_config()
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-custom"
    assert cfg.api_key == "sk-custom"


@pytest.mark.parametrize("drv", ["openai", "ollama", "deepseek", "anthropic",
                                 "google", "qwen", "dashscope", "glm", "zhipu"])
def test_validate_driver_accepts_all_supported(drv):
    assert Config(driver=drv).driver == drv  # preserved verbatim, incl. aliases


def test_validate_driver_rejects_unknown():
    with pytest.raises(Exception):
        Config(driver="not-a-driver")


def test_provider_profile_infers_driver():
    # A [llm.<name>] profile with no explicit driver infers via _DRIVER_BY_PROVIDER.
    cfg = Config(**{"app": {"provider": "qwen"},
                    "llm": {"qwen": {"model": "qwen3-coder", "num_ctx": 4096}}})
    assert cfg.driver == "qwen"
    cfg_glm = Config(**{"app": {"provider": "glm"},
                        "llm": {"glm": {"model": "glm-4.6"}}})
    assert cfg_glm.driver == "glm"
    cfg_ds = Config(**{"app": {"provider": "deepseek"},
                       "llm": {"deepseek": {"model": "deepseek-chat"}}})
    assert cfg_ds.driver == "deepseek"
