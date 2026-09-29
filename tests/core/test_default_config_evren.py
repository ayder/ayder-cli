"""The first-run config.toml ships an evren profile with an empty API key."""

import tomllib

import pytest

from ayder_cli.core import config as config_module
from ayder_cli.core.config import DEFAULTS, load_config_for_provider
from ayder_cli.core.config_migration import ensure_latest_config

EVREN_PROFILE = {
    "driver": "openai",
    "base_url": "https://evren-llmapi.ssyz.org.tr/v1",
    "api_key": "",
    "model": "deepseek-v4-flash",
    "num_ctx": 131072,
}


@pytest.fixture
def fresh_config(tmp_path, monkeypatch):
    path = tmp_path / ".ayder" / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", path.parent)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    ensure_latest_config(path, defaults=DEFAULTS)
    return path


def test_first_run_config_has_evren_profile(fresh_config):
    data = tomllib.loads(fresh_config.read_text())

    assert data["llm"]["evren"] == EVREN_PROFILE
    assert data["app"]["provider"] == "openai"


def test_evren_profile_loads_with_empty_key(fresh_config):
    cfg = load_config_for_provider("evren")

    assert (cfg.driver, cfg.base_url, cfg.api_key, cfg.model) == (
        "openai",
        "https://evren-llmapi.ssyz.org.tr/v1",
        "",
        "deepseek-v4-flash",
    )
