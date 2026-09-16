"""Reasoning defaults, profile loading, and agent override validation."""

import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from ayder_cli.agents.config import AgentConfig
from ayder_cli.application import runtime_factory
from ayder_cli.core import config as config_module
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.reasoning import OPENAI_EFFORTS


@pytest.mark.parametrize("effort", OPENAI_EFFORTS)
def test_openai_effort_in_config_and_agent(effort):
    assert Config(reasoning_effort=effort).reasoning_effort == effort
    assert (
        AgentConfig(name="reviewer", reasoning_effort=effort).overrides()[
            "reasoning_effort"
        ]
        == effort
    )


@pytest.mark.parametrize("effort", ["extreme", True, 4, ""])
def test_invalid_effort_rejected(effort):
    for cls, kwargs in [(Config, {}), (AgentConfig, {"name": "reviewer"})]:
        with pytest.raises(ValidationError):
            cls(**kwargs, reasoning_effort=effort)


@pytest.mark.parametrize("effort", ["minimal", "xhigh", "max"])
def test_ollama_rejects_unsupported_sdk_effort(effort):
    with pytest.raises(ValidationError, match="Ollama reasoning_effort"):
        Config(driver="ollama", reasoning_effort=effort)


def test_default_effort_and_normalization():
    assert Config().reasoning_effort is None
    assert Config(reasoning_effort="DEFAULT").reasoning_effort is None
    assert Config(reasoning_effort=" HIGH ").reasoning_effort == "high"
    assert AgentConfig(name="inherit").overrides() == {}
    assert AgentConfig(name="reset", reasoning_effort="default").overrides() == {
        "reasoning_effort": None
    }


@pytest.mark.parametrize("think", [True, False, "low", "medium", "high"])
def test_legacy_agent_think_overrides_profile_effort(think):
    agent = AgentConfig(name="legacy", think=think)
    assert agent.overrides() == {"think": think, "reasoning_effort": None}
    alias = AgentConfig(name="alias", thinking=think)
    assert alias.think == think


def test_profile_effort_loaded_from_toml(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text("""
config_version = "2.0"
[app]
provider = "local"
[llm.local]
driver = "ollama"
reasoning_effort = "low"
[llm.remote]
driver = "openai"
reasoning_effort = "xhigh"
[agents.reviewer]
reasoning_effort = "high"
""")
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    local = config_module.load_config_for_provider("local")
    remote = config_module.load_config_for_provider("remote")
    assert local.reasoning_effort == "low"
    assert remote.reasoning_effort == "xhigh"
    assert local.agents["reviewer"].reasoning_effort == "high"


@pytest.mark.parametrize(
    "agent_values,expected",
    [
        ({}, "medium"),
        ({"reasoning_effort": "high"}, "high"),
        ({"reasoning_effort": "default"}, None),
        ({"think": False}, None),
        ({"provider": "other"}, "low"),
    ],
)
def test_agent_runtime_inheritance(tmp_path, monkeypatch, agent_values, expected):
    parent = Config(driver="ollama", reasoning_effort="medium")
    other = Config(driver="ollama", reasoning_effort="low")
    monkeypatch.setattr(runtime_factory, "load_config_for_provider", lambda name: other)
    factory = MagicMock()
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", factory)
    monkeypatch.setattr(runtime_factory.context_manager_factory, "create", MagicMock())
    monkeypatch.setattr(runtime_factory, "create_default_registry", MagicMock())
    runtime = runtime_factory.create_agent_runtime(
        agent_config=AgentConfig(name="reviewer", **agent_values),
        parent_config=parent,
        project_ctx=ProjectContext(str(tmp_path)),
        process_manager=MagicMock(),
        permissions={"r"},
    )
    assert runtime.config.reasoning_effort == expected
    assert factory.call_args.args[0].reasoning_effort == expected
    assert parent.reasoning_effort == "medium"


def test_agent_override_validated_after_driver_resolution(tmp_path, monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", factory)
    with pytest.raises(ValueError, match="Ollama reasoning_effort"):
        runtime_factory.create_agent_runtime(
            agent_config=AgentConfig(name="reviewer", reasoning_effort="xhigh"),
            parent_config=Config(driver="ollama"),
            project_ctx=ProjectContext(str(tmp_path)),
            process_manager=MagicMock(),
            permissions={"r"},
        )
    factory.assert_not_called()


def test_example_config_parses():
    path = Path(__file__).parents[2] / "docs/config.toml.example"
    cfg = Config(**tomllib.loads(path.read_text()))
    assert cfg.agents["pm_spec"].reasoning_effort == "high"
