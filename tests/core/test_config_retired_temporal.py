"""A config.toml written before the Temporal removal keeps loading.

Every config ayder generated before the removal carries [temporal],
[temporal.timeouts] and [temporal.retry]. The section is now ignored: it must
never stop the rest of the file from loading, and a legacy migration must keep
every other override.
"""

import tomllib

import pytest

from ayder_cli.core import config as config_module
from ayder_cli.core.config import DEFAULTS, load_config, load_config_for_provider
from ayder_cli.core.config_migration import ensure_latest_config

# What render_v2_config wrote into every generated config before the removal.
AS_GENERATED = """\
[temporal]
enabled = false
host = "localhost:7233"
namespace = "default"
metadata_dir = ".ayder/temporal"

[temporal.timeouts]
workflow_schedule_to_close_seconds = 7200
activity_start_to_close_seconds = 900
activity_heartbeat_seconds = 30

[temporal.retry]
initial_interval_seconds = 5
backoff_coefficient = 2.0
maximum_interval_seconds = 60
maximum_attempts = 3
"""

# Values the removed TemporalConfig validators rejected.
STALE = """\
[temporal]
enabled = true
host = ""
namespace = "prod"
metadata_dir = ".ayder/temporal"

[temporal.timeouts]
workflow_schedule_to_close_seconds = 0

[temporal.retry]
backoff_coefficient = 0.5
"""


def _v2_config(temporal_block: str) -> str:
    return f'''config_version = "2.0"

[app]
provider = "deepseek"
editor = "nano"

[logging]
file_enabled = false
file_path = "logs/custom.log"

{temporal_block}
[llm.deepseek]
driver = "openai"
base_url = "https://api.deepseek.com/v1"
api_key = "sk-test"
model = "deepseek-chat"
num_ctx = 65536
'''


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / ".ayder" / "config.toml"
    path.parent.mkdir()
    monkeypatch.setattr(config_module, "CONFIG_DIR", path.parent)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    return path


@pytest.mark.parametrize(
    "temporal_block", [AS_GENERATED, STALE], ids=["as-generated", "stale"]
)
def test_temporal_section_does_not_reset_the_rest_of_the_config(
    config_path, temporal_block
):
    text = _v2_config(temporal_block)
    config_path.write_text(text, encoding="utf-8")

    cfg = load_config()

    assert (cfg.provider, cfg.model, cfg.editor) == ("deepseek", "deepseek-chat", "nano")
    assert cfg.logging_file_enabled is False
    assert cfg.logging_file_path == "logs/custom.log"
    # The user's file is left as written: no rewrite, no backup.
    assert config_path.read_text(encoding="utf-8") == text
    assert not config_path.with_name("config.toml.bak").exists()


def test_provider_switch_loads_despite_a_stale_temporal_section(config_path):
    config_path.write_text(_v2_config(STALE), encoding="utf-8")

    cfg = load_config_for_provider("deepseek")

    assert (cfg.provider, cfg.model) == ("deepseek", "deepseek-chat")


def test_legacy_migration_drops_temporal_and_keeps_every_other_override(config_path):
    legacy = """provider = "openai"

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

[temporal]
enabled = true
host = "temporal.example.local:7233"

[temporal.timeouts]
workflow_schedule_to_close_seconds = "2h"
"""
    config_path.write_text(legacy, encoding="utf-8")

    ensure_latest_config(config_path, defaults=DEFAULTS)

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["llm"]["openai"]["model"] == "legacy-model"
    assert data["llm"]["openai"]["num_ctx"] == 12345
    assert data["app"]["editor"] == "nano"
    assert data["logging"]["file_path"] == "logs/custom.log"
    assert "temporal" not in data
    # The retired values survive only in the backup the migration always writes.
    backup = config_path.with_name("config.toml.bak")
    assert backup.read_text(encoding="utf-8") == legacy


def test_first_run_config_has_no_temporal_section(config_path):
    ensure_latest_config(config_path, defaults=DEFAULTS)

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["config_version"] == "2.0"
    assert "temporal" not in data
