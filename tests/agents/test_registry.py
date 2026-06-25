"""Tests for AgentRegistry — lifecycle management for agents."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry, _compose_agent_prompt
from ayder_cli.agents.run import AgentRun
from ayder_cli.agents.runner import AgentRunOutcome


class TestComposeAgentPrompt:
    """The agent's user turn is built from task / task_id file / branch_name."""

    def test_plain_task_unchanged(self):
        # No task_id and no branch -> identical to the raw task (backward compatible).
        assert _compose_agent_prompt("Review auth.py", None, None) == "Review auth.py"

    def test_embeds_task_file_and_branch_and_directive(self):
        out = _compose_agent_prompt(
            "focus on the edge cases",
            ("TASK-003", ".ayder/tasks/TASK-003-add-auth.md", "SPEC BODY"),
            "agent/add-auth",
        )
        assert "TASK-003" in out
        assert "SPEC BODY" in out                         # file embedded in full
        assert ".ayder/tasks/TASK-003-add-auth.md" in out  # provenance for re-reads
        assert "agent/add-auth" in out and "COMMIT" in out
        assert "focus on the edge cases" in out

    def test_branch_only(self):
        out = _compose_agent_prompt("do the thing", None, "agent/x")
        assert "do the thing" in out and "agent/x" in out

    def test_task_id_without_free_text(self):
        out = _compose_agent_prompt("", ("TASK-009", "p.md", "BODY"), None)
        assert "TASK-009" in out and "BODY" in out


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
        assert 'agent(action="list")' in prompts
        assert 'agent(action="call"' in prompts
        assert "reviewer" not in prompts
        assert "writer" not in prompts

    def test_capability_prompt_is_pull(self, registry):
        p = registry.get_capability_prompts()
        assert 'action="status"' in p and 'action="read_result"' in p
        assert "after all agents complete" not in p
        assert "Batch behavior" not in p
        assert "pull" in p.lower()
        assert "note_path" in p          # points the model at the saved deliverable

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

    def test_create_run_unknown_agent(self, registry):
        """create_run on an unknown agent returns error string with discovery guidance."""
        result = registry.create_run("nonexistent", "do something")
        assert "not found" in result.lower()
        assert "reviewer" in result
        assert "writer" in result
        assert 'action="list"' in result

    @pytest.mark.parametrize("task", ["", "   ", "\n\t  \n"])
    def test_create_run_rejects_empty_task(self, registry, task):
        """An empty/blank task (and no task_id) is rejected — never dispatched.

        The prompt is the agent's ENTIRE user turn; a blank one makes the agent
        reply 'I don't have a task assigned yet'. Guard it at the boundary
        (the golden rule: no concrete task -> no dispatch) instead of wasting a run.
        """
        result = registry.create_run("reviewer", task)
        assert isinstance(result, str)
        assert "empty task" in result.lower()
        # Nothing was scheduled: no run record, no active runner, counter untouched.
        assert registry._runs == {}
        assert registry._active == {}
        assert registry._run_counter == 0

    def test_create_run_unknown_task_id_fails_fast(self, registry, monkeypatch):
        """task_id that resolves to no task file fails fast — no dispatch."""
        monkeypatch.setattr("ayder_cli.agents.registry.read_task", lambda ctx, ident: None)
        monkeypatch.setattr("ayder_cli.agents.registry.list_task_ids",
                            lambda ctx: ["TASK-001", "TASK-002"])
        result = registry.create_run("reviewer", "do it", task_id="TASK-009")
        assert isinstance(result, str)
        assert "task_id 'TASK-009'" in result and "not found" in result.lower()
        assert "TASK-001" in result  # lists what does exist
        assert registry._runs == {} and registry._run_counter == 0

    @pytest.mark.anyio
    async def test_create_run_task_id_embeds_file_and_records(self, registry, monkeypatch):
        """A resolved task_id embeds the file in the prompt and is recorded on the run."""
        registry.set_loop(asyncio.get_running_loop())
        monkeypatch.setattr(
            "ayder_cli.agents.registry.read_task",
            lambda ctx, ident: ("TASK-003", ".ayder/tasks/TASK-003-add-auth.md", "DO THE AUTH WORK"),
        )
        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentRunOutcome("done", "ok", None, None))
            # task may be empty when task_id carries the work.
            rid = registry.create_run("reviewer", "", task_id="3", branch_name="agent/add-auth")
            assert isinstance(rid, int)
            await registry._runs[rid].done_event.wait()

        prompt = mock_runner.run.call_args.args[0]
        assert "TASK-003" in prompt
        assert "DO THE AUTH WORK" in prompt          # the file is embedded, not just referenced
        assert "agent/add-auth" in prompt            # branch directive folded in
        assert registry._runs[rid].task_id == "TASK-003"
        assert registry._runs[rid].branch_name == "agent/add-auth"

    @pytest.mark.anyio
    async def test_create_run_records_task_preview_and_run_label(self, registry):
        """The free-text task is previewed on the run and surfaced via run_label."""
        registry.set_loop(asyncio.get_running_loop())
        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentRunOutcome("done", "ok", None, None))
            rid = registry.create_run("reviewer", "Refactor auth.py to use JWT tokens")
            await registry._runs[rid].done_event.wait()
        assert registry._runs[rid].task_preview == "Refactor auth.py to use JWT tokens"
        assert registry.run_label(rid) == "Refactor auth.py to use JWT tokens"
        assert registry.run_label(9999) is None  # unknown run

    @pytest.mark.anyio
    async def test_result_payload_carries_task_binding_for_correlation(self, registry, monkeypatch):
        """read_result exposes task_id + task_preview so the orchestrator can tell
        whether the deliverable matches the task it dispatched."""
        registry.set_loop(asyncio.get_running_loop())
        monkeypatch.setattr(
            "ayder_cli.agents.registry.read_task",
            lambda ctx, ident: ("TASK-010", ".ayder/tasks/TASK-010-x.md", "BODY"),
        )
        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentRunOutcome("done", "ok", None, None))
            rid = registry.create_run("reviewer", "write the integration tests", task_id="10")
            await registry._runs[rid].done_event.wait()
        payload = registry.read_result(rid)
        assert payload["task_id"] == "TASK-010"
        assert payload["task_preview"] == "write the integration tests"

    @pytest.mark.anyio
    async def test_create_run_backward_compatible_prompt_unchanged(self, registry):
        """With no task_id and no branch_name, the prompt is exactly the task string."""
        registry.set_loop(asyncio.get_running_loop())
        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentRunOutcome("done", "ok", None, None))
            rid = registry.create_run("reviewer", "Review auth.py")
            await registry._runs[rid].done_event.wait()
        assert mock_runner.run.call_args.args[0] == "Review auth.py"
        assert registry._runs[rid].task_id is None
        assert registry._runs[rid].branch_name is None

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
            # Just scheduled: the runner is built inside _run_and_queue once a slot
            # frees, so a freshly-created run is queued with no runner in _active yet.
            assert run1 not in registry._active and run2 not in registry._active
            assert {registry._runs[run1].status, registry._runs[run2].status} <= {"queued", "working"}
            # Let scheduled tasks complete (inside the patch, so the mock runner is used).
            await registry._runs[run1].done_event.wait()
            await registry._runs[run2].done_event.wait()

        assert registry._runs[run1].status == "done"
        assert registry._runs[run2].status == "done"

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
