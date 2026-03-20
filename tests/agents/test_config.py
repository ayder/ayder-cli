"""Tests for AgentConfig and Config agent parsing."""

import pytest
from ayder_cli.agents.config import AgentConfig
from ayder_cli.core.config import Config


class TestAgentConfig:
    def test_minimal_agent_config(self):
        """AgentConfig with only name and system_prompt."""
        cfg = AgentConfig(name="test-agent", system_prompt="You are a test agent.")
        assert cfg.name == "test-agent"
        assert cfg.provider is None
        assert cfg.model is None
        assert cfg.system_prompt == "You are a test agent."

    def test_full_agent_config(self):
        """AgentConfig with all fields set."""
        cfg = AgentConfig(
            name="code-reviewer",
            provider="anthropic",
            model="claude-sonnet-4-5",
            system_prompt="You review code.",
        )
        assert cfg.name == "code-reviewer"
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-5"

    def test_agent_config_is_frozen(self):
        """AgentConfig should be immutable."""
        cfg = AgentConfig(name="test", system_prompt="test")
        with pytest.raises(Exception):
            cfg.name = "changed"

    def test_empty_system_prompt_default(self):
        """system_prompt defaults to empty string."""
        cfg = AgentConfig(name="test")
        assert cfg.system_prompt == ""


class TestConfigAgentParsing:
    def test_config_default_no_agents(self):
        """Config has empty agents dict by default."""
        cfg = Config()
        assert cfg.agents == {}
        assert cfg.agent_timeout == 300

    def test_config_agent_timeout_custom(self):
        """agent_timeout can be set via app section."""
        cfg = Config(**{"app": {"agent_timeout": 600}, "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}}})
        assert cfg.agent_timeout == 600

    def test_config_parses_agents_section(self):
        """Agents parsed from [agents.*] TOML sections."""
        data = {
            "app": {"provider": "openai"},
            "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}},
            "agents": {
                "code-reviewer": {
                    "system_prompt": "You review code.",
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-5",
                },
                "test-writer": {
                    "system_prompt": "You write tests.",
                },
            },
        }
        cfg = Config(**data)
        assert len(cfg.agents) == 2
        assert "code-reviewer" in cfg.agents
        assert cfg.agents["code-reviewer"].name == "code-reviewer"
        assert cfg.agents["code-reviewer"].provider == "anthropic"
        assert cfg.agents["code-reviewer"].model == "claude-sonnet-4-5"
        assert cfg.agents["test-writer"].name == "test-writer"
        assert cfg.agents["test-writer"].provider is None

    def test_config_agent_name_from_key(self):
        """Agent name is derived from TOML key, overriding explicit name."""
        data = {
            "app": {"provider": "openai"},
            "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}},
            "agents": {
                "my-agent": {
                    "name": "wrong-name",
                    "system_prompt": "test",
                },
            },
        }
        cfg = Config(**data)
        assert cfg.agents["my-agent"].name == "my-agent"

    def test_config_agent_timeout_validation(self):
        """agent_timeout must be positive."""
        with pytest.raises(Exception):
            Config(**{"app": {"agent_timeout": 0}})
