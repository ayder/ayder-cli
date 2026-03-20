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

    def test_capability_prompts_mention_batch_behavior(self, registry):
        """Capability prompts explain batch completion and no-retry for failures."""
        prompts = registry.get_capability_prompts()
        assert "all agents complete" in prompts.lower() or "batch" in prompts.lower()
        assert "failed" in prompts.lower() or "error" in prompts.lower()

    def test_dispatch_unknown_agent(self, registry):
        """Dispatching unknown agent returns error string."""
        result = registry.dispatch("nonexistent", "do something")
        assert "not found" in result.lower()

    def test_dispatch_returns_run_id(self, registry):
        """dispatch() returns int run_id on success."""
        mock_loop = MagicMock()
        registry.set_loop(mock_loop)

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner, \
             patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe"):
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"

            result = registry.dispatch("reviewer", "Review this")

        assert isinstance(result, int)
        assert result == 1  # first dispatch

    def test_dispatch_allows_same_agent_twice(self, registry):
        """Same agent can be dispatched concurrently — no duplicate guard."""
        mock_loop = MagicMock()
        registry.set_loop(mock_loop)

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner, \
             patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe"):
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"

            run1 = registry.dispatch("reviewer", "task 1")
            run2 = registry.dispatch("reviewer", "task 2")

        assert isinstance(run1, int)
        assert isinstance(run2, int)
        assert run1 != run2
        assert registry.active_count == 2

    def test_cancel_all_by_name(self, registry):
        """cancel() cancels all instances with the given name."""
        mock1 = MagicMock()
        mock1.agent_name = "reviewer"
        mock1.cancel.return_value = True
        mock2 = MagicMock()
        mock2.agent_name = "reviewer"
        mock2.cancel.return_value = True

        registry._active[1] = mock1
        registry._active[2] = mock2

        assert registry.cancel("reviewer") is True
        mock1.cancel.assert_called_once()
        mock2.cancel.assert_called_once()

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
        mock1 = MagicMock()
        mock1.agent_name = "reviewer"
        mock2 = MagicMock()
        mock2.agent_name = "writer"
        registry._active[1] = mock1
        registry._active[2] = mock2
        assert registry.active_count == 2

    def test_get_running_count(self, registry):
        """get_running_count returns count of active instances by name."""
        mock1 = MagicMock()
        mock1.agent_name = "reviewer"
        mock2 = MagicMock()
        mock2.agent_name = "reviewer"
        registry._active[1] = mock1
        registry._active[2] = mock2
        assert registry.get_running_count("reviewer") == 2
        assert registry.get_running_count("writer") == 0

    def test_get_status_running_aggregate(self, registry):
        """get_status returns 'running' if any instance is active."""
        mock1 = MagicMock()
        mock1.agent_name = "reviewer"
        registry._active[1] = mock1
        assert registry.get_status("reviewer") == "running"

    def test_get_status_settled(self, registry):
        """get_status returns settled status when not running."""
        registry._settled["reviewer"] = "error"
        assert registry.get_status("reviewer") == "error"

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

        callback.assert_called_once_with(1, summary)
        # Agent should be removed from _active
        assert 1 not in reg._active

    def test_settled_blocks_failed_agent_redispatch(self, registry):
        """Cannot re-dispatch an agent that errored in this cycle."""
        registry._settled = {"reviewer": "error"}
        result = registry.dispatch("reviewer", "try again")
        assert "failed in this cycle" in result.lower() and "handle the task directly" in result.lower()

    def test_settled_blocks_timed_out_agent_redispatch(self, registry):
        """Cannot re-dispatch an agent that timed out in this cycle."""
        registry._settled = {"reviewer": "timeout"}
        result = registry.dispatch("reviewer", "try again")
        assert "failed in this cycle" in result.lower() and "handle the task directly" in result.lower()

    def test_settled_allows_completed_agent_redispatch(self, registry):
        """Can re-dispatch an agent that completed successfully."""
        registry._settled = {"reviewer": "completed"}
        mock_loop = MagicMock()
        registry.set_loop(mock_loop)

        with patch("ayder_cli.agents.registry.AgentRunner"), \
             patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe"):
            result = registry.dispatch("reviewer", "run again")

        assert isinstance(result, int)

    def test_reset_settled(self, registry):
        """reset_settled clears the settled tracker."""
        registry._settled = {"reviewer": "error", "writer": "completed"}
        registry.reset_settled()
        assert registry._settled == {}
