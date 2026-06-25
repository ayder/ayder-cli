"""Integration test for the multi-agent system end-to-end."""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.runner import AgentRunOutcome
from ayder_cli.agents.tool import create_agent_handler
from ayder_cli.core.config import Config


class TestAgentIntegration:
    @pytest.mark.anyio
    async def test_config_to_create_run_flow(self):
        """End-to-end: parse config → create registry → create_run (background)."""
        # 1. Parse config with agents
        data = {
            "app": {"provider": "openai", "agent_timeout": 10},
            "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}},
            "agents": {
                "reviewer": {"system_prompt": "You review code."},
            },
        }
        cfg = Config(**data)
        assert "reviewer" in cfg.agents
        assert cfg.agent_timeout == 10

        # 2. Create registry
        registry = AgentRegistry(
            agents=cfg.agents,
            parent_config=cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r", "w"},
            agent_timeout=cfg.agent_timeout,
        )

        # 3. Verify generic capability prompts and structured discovery
        prompts = registry.get_capability_prompts()
        assert 'agent(action="list")' in prompts
        assert 'agent(action="call"' in prompts
        assert "reviewer" not in prompts
        agents = registry.list_agents()
        assert agents[0]["name"] == "reviewer"
        assert agents[0]["description"] == "You review code."

        # 4. Create the run via the tool handler (routed onto the loop)
        registry.set_loop(asyncio.get_running_loop())
        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentRunOutcome(
                "done", "Found 2 issues.", None, None,
            ))

            handler = create_agent_handler(registry)
            # _on_loop requires marshaling; the handler runs on the loop in this test,
            # so route synchronously.
            registry._on_loop = lambda fn: fn()
            result = handler(action="call", name="reviewer", task="Review auth.py")

        # create_run returns a run-id-bearing status message
        assert "run #" in result
        assert "reviewer" in result

    def test_config_no_agents_no_capability_prompts(self):
        """When no agents configured, capability prompts are empty."""
        cfg = Config()
        registry = AgentRegistry(
            agents=cfg.agents,
            parent_config=cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        assert registry.get_capability_prompts() == ""
