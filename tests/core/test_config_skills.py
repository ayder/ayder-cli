"""The skills setting for sessions, profiles and agents (spec 4.10).

Kind: new interface. Kept out of tests/core/test_config.py, which poe test
ignores.
"""

from __future__ import annotations

import pytest

from ayder_cli.agents.config import AgentConfig
from ayder_cli.core import config as config_module
from ayder_cli.core.config import Config, load_config_for_provider


def _write_config(tmp_path, monkeypatch, body: str) -> None:
    path = tmp_path / ".ayder" / "config.toml"
    path.parent.mkdir()
    path.write_text(body)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)


_TOML = """config_version = "2.0"

[app]
provider = "plain"
{app_extra}

[llm.plain]
driver = "openai"
base_url = "http://localhost:1/v1"
api_key = "x"
model = "m"
{plain_extra}

[llm.other]
driver = "openai"
base_url = "http://localhost:1/v1"
api_key = "x"
model = "m"
skills = ["design"]
"""


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("none", "none"), ("NONE", "none"), ([], "none"), ([" eng "], ["eng"])],
)
def test_setting_is_normalized(value, expected):
    assert Config(skills=value).skills == expected
    assert AgentConfig(name="a", skills=value).skills == expected


@pytest.mark.parametrize("value", ["all", "", [""], [1]])
def test_invalid_setting_is_a_config_error(value):
    with pytest.raises(ValueError):
        Config(skills=value)
    with pytest.raises(ValueError):
        AgentConfig(name="a", skills=value)


def test_profile_wins_over_app_for_the_session(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, _TOML.format(
        app_extra='skills = "none"', plain_extra='skills = ["engineering"]'))
    cfg = load_config_for_provider("plain")
    assert (cfg.skills, cfg.profile_skills) == ("none", ["engineering"])
    assert cfg.session_skills() == ["engineering"]


def test_app_applies_when_the_profile_is_silent(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, _TOML.format(app_extra='skills = "none"', plain_extra=""))
    cfg = load_config_for_provider("plain")
    assert (cfg.profile_skills, cfg.session_skills()) == (None, "none")


def test_not_set_anywhere_is_none(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, _TOML.format(app_extra="", plain_extra=""))
    assert load_config_for_provider("plain").session_skills() is None
