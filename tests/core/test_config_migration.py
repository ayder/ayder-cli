"""Tests for config migration to v2.0."""

import tomllib

from ayder_cli.core.config import DEFAULTS
from ayder_cli.core.config_migration import ensure_latest_config


def test_migrates_legacy_config_and_creates_backup(tmp_path):
    config_dir = tmp_path / ".ayder"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    config_path.write_text(
        """provider = "openai"

[openai]
base_url = "https://example.com/v1"
api_key = "legacy-key"
model = "legacy-model"
num_ctx = 12345

[editor]
editor = "nano"

[logging]
file_enabled = false
file_path = "logs/custom.log"
""",
        encoding="utf-8",
    )

    notices: list[str] = []
    notice = ensure_latest_config(
        config_path,
        defaults=DEFAULTS,
        notify=True,
        output=notices.append,
    )

    backup_path = config_dir / "config.toml.bak"
    assert backup_path.exists()
    assert notice is not None
    assert notices == [notice]

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["config_version"] == "2.0"
    assert data["app"]["provider"] == "openai"
    assert data["app"]["editor"] == "nano"
    assert data["logging"]["file_enabled"] is False
    assert data["logging"]["file_path"] == "logs/custom.log"
    assert data["llm"]["openai"]["driver"] == "openai"
    assert data["llm"]["openai"]["model"] == "legacy-model"
    assert data["llm"]["openai"]["num_ctx"] == 12345


def test_malformed_legacy_config_resets_to_fresh_v2_with_backup(tmp_path):
    config_dir = tmp_path / ".ayder"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    invalid_toml = "provider = \"openai\"\n[openai\napi_key = \"broken\""
    config_path.write_text(invalid_toml, encoding="utf-8")

    notice = ensure_latest_config(config_path, defaults=DEFAULTS, notify=True, output=lambda _: None)

    backup_path = config_dir / "config.toml.bak"
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == invalid_toml
    assert notice is not None

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["config_version"] == "2.0"
    assert "app" in data
    assert "llm" in data


def test_v2_config_is_not_rewritten(tmp_path):
    config_dir = tmp_path / ".ayder"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    config_path.write_text(
        """config_version = "2.0"

[app]
provider = "openai"
editor = "vim"
verbose = false
max_background_processes = 5
max_iterations = 50

[logging]
file_enabled = true
file_path = ".ayder/log/ayder.log"
rotation = "10 MB"
retention = "7 days"

[llm.openai]
driver = "openai"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "qwen3-coder:latest"
num_ctx = 65536
""",
        encoding="utf-8",
    )

    notice = ensure_latest_config(config_path, defaults=DEFAULTS)

    assert notice is None
    assert not (config_dir / "config.toml.bak").exists()

