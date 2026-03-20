"""Tests for AgentRegistry — lifecycle management for agents."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.summary import AgentSummary


@pytest.fixture
def agent_configs():
    return {
        "reviewer": AgentConfig(name="reviewer", system_prompt="You review code."),
        "writer": AgentConfig(name="writer", system_prompt="You write tests."),
    }


@pytest.fixture
def registry(agent_configs):
    return AgentRegistry(
        agents=agent_configs,
        parent_config=MagicMock(),
        project_ctx=MagicMock(),
        process_manager=MagicMock(),
        permissions={"r", "w"},
        agent_timeout=300,
    )


class TestAgentRegistry:
    def test_init(self, registry, agent_configs):
        assert len(registry.agents) == 2
        assert "reviewer" in registry.agents

    def test_get_status_idle(self, registry):
        assert registry.get_status("reviewer") == "idle"

    def test_get_status_unknown(self, registry):
        assert registry.get_status("nonexistent") is None

    def test_get_capability_prompts(self, registry):
        prompts = registry.get_capability_prompts()
        assert "reviewer" in prompts
        assert "writer" in prompts
        assert "call_agent" in prompts

    def test_get_capability_prompts_empty(self):
        reg = AgentRegistry(
            agents={},
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        assert reg.get_capability_prompts() == ""

    def test_get_capability_prompts_truncation(self):
        """System prompts longer than 100 chars are truncated."""
        agents = {
            "verbose": AgentConfig(
                name="verbose",
                system_prompt="A" * 200,
            ),
        }
        reg = AgentRegistry(
            agents=agents,
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        prompts = reg.get_capability_prompts()
        # Each agent description line should be truncated
        for line in prompts.splitlines():
            if line.startswith("- verbose:"):
                assert len(line) < 120  # name + truncated prompt

    def test_dispatch_unknown_agent(self, registry):
        """Dispatching unknown agent returns error string."""
        result = registry.dispatch("nonexistent", "do something")
        assert "not found" in result.lower()

    def test_dispatch_returns_status_string(self, registry):
        """dispatch() returns immediately with a status string."""
        # Set a mock loop so dispatch doesn't fail
        mock_loop = MagicMock()
        registry.set_loop(mock_loop)

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner, \
             patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe") as mock_rcts:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"

            result = registry.dispatch("reviewer", "Review this")

        assert isinstance(result, str)
        assert "dispatched" in result.lower() or "reviewer" in result.lower()
        mock_rcts.assert_called_once()

    def test_dispatch_rejects_duplicate(self, registry):
        """Cannot dispatch same agent while it's already running."""
        registry._active["reviewer"] = MagicMock()
        result = registry.dispatch("reviewer", "another task")
        assert "already running" in result.lower()

    def test_cancel(self, registry):
        """cancel() delegates to the active AgentRunner."""
        mock_runner = MagicMock()
        mock_runner.cancel.return_value = True
        registry._active["reviewer"] = mock_runner

        assert registry.cancel("reviewer") is True
        mock_runner.cancel.assert_called_once()

    def test_cancel_not_running(self, registry):
        assert registry.cancel("reviewer") is False

    def test_drain_summaries_empty(self, registry):
        """drain_summaries returns empty list when no summaries."""
        assert registry.drain_summaries() == []

    @pytest.mark.anyio
    async def test_drain_summaries_after_completion(self, registry):
        """drain_summaries returns summaries that were queued."""
        summary = AgentSummary(
            agent_name="reviewer", status="completed", summary="Done.", error=None
        )
        await registry._summary_queue.put(summary)
        result = registry.drain_summaries()
        assert len(result) == 1
        assert result[0].agent_name == "reviewer"

    def test_on_complete_callback_received(self, agent_configs):
        """on_complete is stored and accessible."""
        callback = MagicMock()
        reg = AgentRegistry(
            agents=agent_configs,
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
            on_complete=callback,
        )
        assert reg._on_complete is callback

    def test_active_count_empty(self, registry):
        assert registry.active_count == 0

    def test_active_count_with_runners(self, registry):
        registry._active["reviewer"] = MagicMock()
        registry._active["writer"] = MagicMock()
        assert registry.active_count == 2

    @pytest.mark.anyio
    async def test_on_complete_called_after_agent_finishes(self, agent_configs):
        """on_complete callback fires after agent completes and is removed from _active."""
        callback = MagicMock()
        reg = AgentRegistry(
            agents=agent_configs,
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
            on_complete=callback,
        )
        loop = asyncio.get_running_loop()
        reg.set_loop(loop)

        summary = AgentSummary(
            agent_name="reviewer", status="completed", summary="Done.", error=None
        )

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=summary)

            reg.dispatch("reviewer", "Review code")

            # Allow the scheduled coroutine to run
            await asyncio.sleep(0.1)

        callback.assert_called_once_with(summary)
        # Agent should be removed from _active
        assert "reviewer" not in reg._active
