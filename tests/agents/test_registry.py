"""Tests for AgentRegistry — lifecycle management for agents."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.run import AgentRun
from ayder_cli.agents.runner import AgentRunOutcome


@pytest.fixture
def agent_configs():
    return {
        "reviewer": AgentConfig(name="reviewer", system_prompt="You review code."),
        "writer": AgentConfig(name="writer", system_prompt="You write tests."),
    }


@pytest.fixture
def registry(agent_configs):
    parent_config = MagicMock()
    parent_config.model = "parent-model"
    return AgentRegistry(
        agents=agent_configs,
        parent_config=parent_config,
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
        assert "list_agents" in prompts
        assert "call_agent" in prompts
        assert "reviewer" not in prompts
        assert "writer" not in prompts

    def test_list_agents_returns_structured_status(self, registry):
        agents = registry.list_agents()
        assert agents == [
            {
                "name": "reviewer",
                "description": "You review code.",
                "model": "parent-model",
                "status": "idle",
                "running_count": 0,
            },
            {
                "name": "writer",
                "description": "You write tests.",
                "model": "parent-model",
                "status": "idle",
                "running_count": 0,
            },
        ]

    def test_list_agents_prefers_agent_model_override(self):
        agents = {
            "custom": AgentConfig(
                name="custom",
                system_prompt="custom",
                model="agent-specific-model",
            ),
        }
        parent_config = MagicMock()
        parent_config.model = "parent-model"
        reg = AgentRegistry(
            agents=agents,
            parent_config=parent_config,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        listed = reg.list_agents()
        assert listed[0]["model"] == "agent-specific-model"

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

    def test_list_agents_description_truncation(self):
        """System prompts exposed through list_agents are bounded."""
        agents = {
            "verbose": AgentConfig(
                name="verbose",
                system_prompt="A" * 250,
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
        listed = reg.list_agents()
        assert listed[0]["description"] == "A" * 200

    def test_capability_prompts_mention_batch_behavior(self, registry):
        """Capability prompts explain batch completion and no-retry for failures."""
        prompts = registry.get_capability_prompts()
        assert "all agents complete" in prompts.lower() or "batch" in prompts.lower()
        assert "failed" in prompts.lower() or "error" in prompts.lower()

    def test_create_run_unknown_agent(self, registry):
        """create_run on an unknown agent returns error string with discovery guidance."""
        result = registry.create_run("nonexistent", "do something")
        assert "not found" in result.lower()
        assert "reviewer" in result
        assert "writer" in result
        assert "list_agents" in result

    @pytest.mark.anyio
    async def test_create_run_allows_same_agent_twice(self, registry):
        """Same agent can be created concurrently — no duplicate guard, distinct run_ids."""
        registry.set_loop(asyncio.get_running_loop())

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentRunOutcome(
                "done", "ok", None, None,
            ))

            run1 = registry.create_run("reviewer", "task 1")
            run2 = registry.create_run("reviewer", "task 2")

        assert isinstance(run1, int)
        assert isinstance(run2, int)
        assert run1 != run2
        # Both scheduled and still working until their tasks run
        assert registry.active_count == 2
        # Let scheduled tasks complete so the test loop has no pending work
        await registry._runs[run1].done_event.wait()
        await registry._runs[run2].done_event.wait()

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

    def test_active_count_counts_working_runs(self, registry):
        """active_count derives from working runs in the current generation."""
        registry._runs = {
            1: AgentRun(1, 0, "reviewer", 0.0, status="working"),
            2: AgentRun(2, 0, "writer", 0.0, status="working"),
            3: AgentRun(3, 0, "reviewer", 0.0, status="done"),
        }
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
        """on_complete callback fires with (run_id, AgentRun) after the agent finishes."""
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
        reg.set_loop(asyncio.get_running_loop())

        outcome = AgentRunOutcome("done", "Done.", None, ".ayder/notes/n.md")

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=outcome)

            rid = reg.create_run("reviewer", "Review code")
            await reg._runs[rid].done_event.wait()

        callback.assert_called_once()
        called_run_id, called_run = callback.call_args.args
        assert called_run_id == rid
        assert isinstance(called_run, AgentRun)
        assert called_run.status == "done"
        assert called_run.result == "Done."
        # Agent should be removed from _active
        assert rid not in reg._active

    def test_settled_blocks_failed_agent_redispatch(self, registry):
        """Cannot re-create a run for an agent that errored in this cycle."""
        registry._settled = {"reviewer": "error"}
        result = registry.create_run("reviewer", "try again")
        assert "failed in this cycle" in result.lower() and "handle the task directly" in result.lower()

    def test_settled_blocks_timed_out_agent_redispatch(self, registry):
        """Cannot re-create a run for an agent that timed out in this cycle."""
        registry._settled = {"reviewer": "timeout"}
        result = registry.create_run("reviewer", "try again")
        assert "failed in this cycle" in result.lower() and "handle the task directly" in result.lower()

    @pytest.mark.anyio
    async def test_settled_allows_completed_agent_redispatch(self, registry):
        """Can re-create a run for an agent that completed successfully."""
        registry._settled = {"reviewer": "completed"}
        registry.set_loop(asyncio.get_running_loop())

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentRunOutcome(
                "done", "ok", None, None,
            ))
            result = registry.create_run("reviewer", "run again")
            assert isinstance(result, int)
            await registry._runs[result].done_event.wait()

    def test_reset_settled(self, registry):
        """reset_settled clears the settled tracker."""
        registry._settled = {"reviewer": "error", "writer": "completed"}
        registry.reset_settled()
        assert registry._settled == {}


@pytest.mark.anyio
async def test_create_run_then_snapshot_and_read(registry):
    registry.set_loop(asyncio.get_running_loop())
    rid = registry.create_run("reviewer", "do it")
    assert isinstance(rid, int)
    # simulate completion
    run = registry._runs[rid]
    run.status, run.result, run.drained = "done", "THE RESULT", False
    run.done_event.set()
    snap = registry.snapshot()
    assert snap[0]["run_id"] == rid and snap[0]["has_unread_result"] is True
    assert "result" not in snap[0]                 # status omits the body
    payload = registry.read_result(rid)
    assert payload["result"] == "THE RESULT"
    assert registry._runs[rid].drained is True     # read marks drained
    assert registry.read_result(rid)["result"] == "THE RESULT"  # idempotent read


def test_new_generation_keeps_runs_but_filters(registry):
    from ayder_cli.agents.run import AgentRun
    registry._runs[1] = AgentRun(run_id=1, generation=0, agent_name="x", started_at=0.0,
                                 status="done", result="STALE")
    registry._current_generation = 0
    registry._run_counter = 1
    registry.new_generation()
    assert registry.snapshot() == []               # old-gen filtered out
    assert registry.read_result(1) is None
    assert registry.pending_nudge() == []
    assert 1 in registry._runs                      # but NOT dropped


def test_pending_nudge_excludes_drained_and_nudged(registry):
    from ayder_cli.agents.run import AgentRun
    registry._current_generation = 1
    registry._runs = {
        1: AgentRun(1, 1, "a", 0.0, status="done"),
        2: AgentRun(2, 1, "b", 0.0, status="done", drained=True),
        3: AgentRun(3, 1, "c", 0.0, status="done", nudged=True),
        4: AgentRun(4, 1, "d", 0.0, status="working"),
    }
    ids = [r.run_id for r in registry.pending_nudge()]
    assert ids == [1]
    registry.mark_nudged(registry.pending_nudge())
    assert registry.pending_nudge() == []


def test_read_while_working_does_not_drain_then_completion_still_nudges(registry):
    # finding 1 regression: a non-blocking read of a WORKING run must not drain it,
    # or the later completion would have no unread result and never nudge.
    from ayder_cli.agents.run import AgentRun
    registry._current_generation = 1
    run = AgentRun(run_id=5, generation=1, agent_name="x", started_at=0.0, status="working")
    registry._runs[5] = run
    payload = registry.read_result(5)
    assert payload["status"] == "working"
    assert run.drained is False                       # NOT drained while working
    # agent completes:
    run.status, run.result = "done", "DELIVERABLE"
    assert [r.run_id for r in registry.pending_nudge()] == [5]   # still nudge-eligible
    assert registry.read_result(5)["result"] == "DELIVERABLE"
    assert run.drained is True                          # terminal read drains


def test_create_run_returns_error_when_loop_unset(registry):
    # single-loop invariant: create_run must refuse to schedule off-loop.
    assert registry._loop is None
    result = registry.create_run("reviewer", "do it")
    assert isinstance(result, str)
    assert "not initialized" in result and "event loop not set" in result


def test_on_loop_raises_when_loop_unset(registry):
    # _on_loop must raise (never run fn locally) when the owning loop is unset.
    assert registry._loop is None
    with pytest.raises(RuntimeError, match="loop not set"):
        registry._on_loop(lambda: "should not run")
