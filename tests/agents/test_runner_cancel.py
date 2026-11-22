"""AgentRunner.cancel() wakes the turn, and a cancelled run settles ``cancelled`` (plan step 18, R8).

``cancel()`` only set an event. A turn blocked on a stalled stream stayed blocked until the stream
yielded or the deadline fired, and the run then settled ``error`` with the timeout text (and was
nudged). A run cancelled before its first request, or between replies, settled ``error`` ("Agent
produced no deliverable...") or ``done`` with its last text (and, for a branch run, was relabelled
"no commit on branch"). Now ``cancel()`` also cancels the task that runs the turn (the registry's
run task), once per run. When that cancellation reaches the runner it calls ``uncancel()`` once, and
settles ``cancelled`` unless another request is pending, which is the parent's and propagates. A
cancelled run is not nudged, and the registry's no-commit relabel applies to ``done`` only.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider, tool registry and context manager are the fakes in ``turn_fakes``, and the
agent runtime is replaced by one that uses them; the real ``ChatLoop``, runner and registry run).
Layer: unit.
"""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import MagicMock, patch

import pytest

import ayder_cli.agents.runner as runner_module
from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.core.context import ProjectContext
from tests.loops.turn_fakes import (
    FakeContext,
    HeldRegistry,
    RecordingRegistry,
    ScriptedProvider,
    Stall,
    chunk,
    delta,
)

_CANCELLED_CONTENT = "Agent cancelled before finishing."
_CANCELLED_ERROR = "Agent cancelled by request."


@pytest.fixture
def anyio_backend():
    return "asyncio"


# -- Helpers -----------------------------------------------------------------------------------------


def _runtime(provider, registry=None):
    """The agent runtime the runner builds, with fakes where it would talk to a provider."""
    rt = MagicMock()
    rt.system_prompt = "sys"
    rt.config = MagicMock(
        model="m", provider="p", num_ctx=1, max_output_tokens=1,
        stop_sequences=[], tool_tags=None, max_history_messages=30,
    )
    rt.llm_provider = provider
    rt.tool_registry = registry or RecordingRegistry()
    rt.context_manager = FakeContext()
    return rt


def _runner(tmp_path, *, timeout=1.0) -> AgentRunner:
    return AgentRunner(
        agent_config=AgentConfig(name="coder", system_prompt="x"),
        parent_config=MagicMock(),
        project_ctx=ProjectContext(str(tmp_path)),
        process_manager=MagicMock(),
        permissions=set(),
        timeout=timeout,
        run_id=1,
        generation=0,
    )


def _stalled_stream():
    """A provider whose stream never yields, and the stall that tells a test it is waiting."""
    stall = Stall()
    return ScriptedProvider([stall]), stall


async def _a_run_stalls(runner, stall, rt):
    """Start ``runner.run`` in a task and wait until its provider is awaiting."""
    with patch.object(runner_module, "create_agent_runtime", return_value=rt):
        task = asyncio.create_task(runner.run("do it"))
        await asyncio.wait_for(stall.entered.wait(), 5)
        return task


async def _cancel_the_stalled_run(runner, stall, rt, *, times=1):
    """Cancel the stalled run ``times`` times; return its task, outcome and seconds to settle."""
    task = await _a_run_stalls(runner, stall, rt)
    started = time.monotonic()
    for _ in range(times):
        runner.cancel()
    outcome = await asyncio.wait_for(task, 5)
    return task, outcome, time.monotonic() - started


# -- E26: cancel() while the stream is stalled --------------------------------------------------------


@pytest.mark.anyio
async def test_cancelling_a_stalled_run_settles_it_cancelled(tmp_path):
    """Baseline regression, E26: the run settles ``error`` with the timeout text at the deadline.

    Driven by a stream that never yields, a 1 s deadline, and ``cancel()`` once the provider is
    awaiting. A status that is neither ``done`` nor ``error`` is not nudged.
    """
    provider, stall = _stalled_stream()
    _, outcome, _ = await _cancel_the_stalled_run(_runner(tmp_path), stall, _runtime(provider))

    assert outcome.status == "cancelled"


@pytest.mark.anyio
async def test_cancelling_a_stalled_run_settles_it_well_before_the_deadline(tmp_path):
    """Baseline regression, E26: the turn stays pending until the 1 s deadline fires today."""
    provider, stall = _stalled_stream()
    _, _, seconds = await _cancel_the_stalled_run(_runner(tmp_path), stall, _runtime(provider))

    assert seconds < 0.5


@pytest.mark.anyio
async def test_a_cancelled_run_is_not_labelled_a_timeout(tmp_path):
    """Baseline regression, E26: the runner's status ends as ``timeout`` today."""
    provider, stall = _stalled_stream()
    runner = _runner(tmp_path)
    await _cancel_the_stalled_run(runner, stall, _runtime(provider))

    assert runner.status == "cancelled"


@pytest.mark.anyio
async def test_a_cancelled_run_reports_the_fixed_content_and_error(tmp_path):
    """Baseline regression, E26 (spec R8): with no assistant text yet, the content is the fixed one."""
    provider, stall = _stalled_stream()
    _, outcome, _ = await _cancel_the_stalled_run(_runner(tmp_path), stall, _runtime(provider))

    assert (outcome.content, outcome.error) == (_CANCELLED_CONTENT, _CANCELLED_ERROR)


@pytest.mark.anyio
async def test_a_cancelled_run_leaves_its_task_with_no_cancel_request(tmp_path):
    """Preservation (guards the new ``uncancel()``): the task that ran the turn is not left cancelling.

    Holds today, where nothing cancels it. After, its own cancellation must be taken back.
    """
    provider, stall = _stalled_stream()
    task, _, _ = await _cancel_the_stalled_run(_runner(tmp_path), stall, _runtime(provider))

    assert task.cancelling() == 0


@pytest.mark.anyio
async def test_cancelling_twice_settles_the_stalled_run_cancelled(tmp_path):
    """Baseline regression: a repeated ``cancel()`` (the registry can reach a runner twice).

    On the parent the run settles at the deadline. After: ``cancelled``.
    """
    provider, stall = _stalled_stream()
    _, outcome, _ = await _cancel_the_stalled_run(
        _runner(tmp_path), stall, _runtime(provider), times=2
    )

    assert outcome.status == "cancelled"


@pytest.mark.anyio
async def test_cancelling_twice_adds_no_second_cancel_request(tmp_path):
    """Preservation (guards idempotence): ``task.cancel()`` is called at most once per run, so
    taking back one request leaves the task at zero. Holds today."""
    provider, stall = _stalled_stream()
    task, _, _ = await _cancel_the_stalled_run(
        _runner(tmp_path), stall, _runtime(provider), times=2
    )

    assert task.cancelling() == 0


# -- A cancellation of the runner's parent task propagates ---------------------------------------------


@pytest.mark.anyio
async def test_a_cancellation_of_the_parent_task_propagates_out_of_run(tmp_path):
    """Preservation: the registry task's own cancellation is not turned into an outcome."""
    provider, stall = _stalled_stream()
    task = await _a_run_stalls(_runner(tmp_path), stall, _runtime(provider))

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.anyio
async def test_the_parents_cancellation_in_the_same_loop_turn_as_cancel_still_propagates(tmp_path):
    """Preservation (guards ``uncancel()`` against swallowing the parent's request).

    The registry task is cancelled and ``cancel()`` is called in the same event-loop turn, so the
    task carries two requests; the runner takes back its own and re-raises for the other.
    """
    provider, stall = _stalled_stream()
    runner = _runner(tmp_path)
    task = await _a_run_stalls(runner, stall, _runtime(provider))

    task.cancel()
    runner.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


# -- N2, E9: cancel() before the first request -----------------------------------------------------------


async def _run_cancelled_before_it_started(tmp_path):
    provider = ScriptedProvider([chunk(content="a reply the run never asks for")])
    runner = _runner(tmp_path)
    runner.cancel()
    with patch.object(runner_module, "create_agent_runtime", return_value=_runtime(provider)):
        outcome = await runner.run("do it")
    return provider, outcome


@pytest.mark.anyio
async def test_a_run_cancelled_before_its_first_request_settles_cancelled(tmp_path):
    """Baseline regression, N2 and E9: it settles ``error`` ("Agent produced no deliverable...")."""
    _, outcome = await _run_cancelled_before_it_started(tmp_path)

    assert outcome.status == "cancelled"


@pytest.mark.anyio
async def test_a_run_cancelled_before_its_first_request_says_so(tmp_path):
    """Baseline regression, N2 and E9: the content and error are the fixed cancelled ones."""
    _, outcome = await _run_cancelled_before_it_started(tmp_path)

    assert (outcome.content, outcome.error) == (_CANCELLED_CONTENT, _CANCELLED_ERROR)


@pytest.mark.anyio
async def test_a_run_cancelled_before_its_first_request_never_asks_the_provider(tmp_path):
    """Preservation: the loop stops at its first cancel check. Holds today."""
    provider, _ = await _run_cancelled_before_it_started(tmp_path)

    assert provider.calls == 0


# -- cancel() before run(), then a stall before the loop's first cancel check ---------------------------


class _ContextThatStallsDetectingItsWindow(FakeContext):
    """A context manager whose ``detect_context_length`` waits on an event that is never set.

    ``ChatLoop.run`` awaits it before its first ``is_cancelled()`` check. The Ollama context manager
    makes a network call there, so it can stall; this stands in for that collaborator at its
    interface, and nothing touches the network.
    """

    async def detect_context_length(self) -> None:
        await asyncio.Event().wait()


async def _cancelled_before_run_then_the_loop_stalls(tmp_path):
    """``cancel()`` is called before ``run()``, so no wake is made (there is no turn task yet).
    The loop then stalls before its first cancel check, and the 0.3 s deadline fires."""
    rt = _runtime(ScriptedProvider([chunk(content="a reply the run never asks for")]))
    rt.context_manager = _ContextThatStallsDetectingItsWindow()
    runner = _runner(tmp_path, timeout=0.3)
    runner.cancel()
    with patch.object(runner_module, "create_agent_runtime", return_value=rt):
        outcome = await runner.run("do it")
    return runner, outcome


@pytest.mark.anyio
async def test_cancel_beats_a_deadline_that_fires_before_the_loops_first_cancel_check(tmp_path):
    """Baseline regression: the deadline's timeout result wins today, as ``error``.

    After: the run was cancelled before the deadline, so it settles ``cancelled``.
    """
    _, outcome = await _cancelled_before_run_then_the_loop_stalls(tmp_path)

    assert outcome.status == "cancelled"


@pytest.mark.anyio
async def test_a_run_cancelled_before_the_deadline_is_not_labelled_a_timeout(tmp_path):
    """Baseline regression: the runner's status ends as ``timeout`` today."""
    runner, _ = await _cancelled_before_run_then_the_loop_stalls(tmp_path)

    assert runner.status != "timeout"


@pytest.mark.anyio
async def test_a_run_cancelled_before_the_deadline_reports_the_cancelled_content_and_error(tmp_path):
    """Baseline regression: the content and error are the timeout's today."""
    _, outcome = await _cancelled_before_run_then_the_loop_stalls(tmp_path)

    assert (outcome.content, outcome.error) == (_CANCELLED_CONTENT, _CANCELLED_ERROR)


# -- A stale cancel count on the task that runs the turn (Codex #4) ---------------------------------------


class _RecoversATaskGroupFailureThenStalls:
    """A provider whose stream recovers a real ``TaskGroup`` child failure, yields control, then
    stalls.

    On Python 3.12.9 that recovery leaves the cancel count of the task running the stream at 1 with
    nothing pending. The stream is collaborator code at its interface; the ``TaskGroup`` is real.
    """

    def __init__(self) -> None:
        self.stall = Stall()

    async def stream_with_tools(self, messages, model=None, tools=None, options=None, verbose=False):
        async def child():
            await asyncio.sleep(0.01)
            raise ValueError("child failed")

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(child())
        except* ValueError:
            pass
        await asyncio.sleep(0)
        self.stall.entered.set()
        await self.stall.release.wait()  # never released
        yield chunk(content="never reached")


async def _result_of(task):
    """The outcome ``task`` returned, or ``"CancelledError"`` when it ended cancelled."""
    try:
        return await asyncio.wait_for(asyncio.shield(task), 5)
    except asyncio.CancelledError:
        if task.cancelled():
            return "CancelledError"
        raise


@pytest.mark.anyio
async def test_an_agents_own_cancel_settles_the_run_cancelled_despite_a_stale_cancel_count(tmp_path):
    """Baseline regression, Codex #4: the runner mistakes the stale count for the parent's request.

    The provider recovers a ``TaskGroup`` failure (leaving a count of 1), yields, then stalls. The
    test calls only ``AgentRunner.cancel()``. Today the runner takes back its own request, finds
    the count still above 0, and lets ``CancelledError`` out with no outcome. After: ``cancelled``.
    """
    provider = _RecoversATaskGroupFailureThenStalls()
    runner = _runner(tmp_path)
    task = await _a_run_stalls(runner, provider.stall, _runtime(provider))

    runner.cancel()
    outcome = await _result_of(task)

    assert getattr(outcome, "status", outcome) == "cancelled"


@pytest.mark.anyio
async def test_the_registry_shows_a_run_cancelled_not_working_after_a_stale_cancel_count(
    tmp_path, monkeypatch
):
    """Baseline regression, Codex #4: the registry writes a terminal status only when it gets an
    outcome, so the run stays ``working`` today.

    The run goes through the registry's real dispatch (``create_run`` and ``cancel``), with the
    agent runtime replaced by one that uses the stalling provider.
    """
    provider = _RecoversATaskGroupFailureThenStalls()
    monkeypatch.setattr(
        runner_module, "create_agent_runtime", lambda **kwargs: _runtime(provider)
    )
    registry = AgentRegistry(
        agents={"coder": AgentConfig(name="coder", system_prompt="x")},
        parent_config=MagicMock(),
        project_ctx=ProjectContext(str(tmp_path)),
        process_manager=MagicMock(),
        permissions={"r"},
        agent_timeout=30,
        max_concurrent_agents=1,
    )
    registry.set_loop(asyncio.get_running_loop())
    run_id = registry.create_run("coder", "do it")
    await asyncio.wait_for(provider.stall.entered.wait(), 5)

    registry.cancel("coder")
    await asyncio.wait_for(registry._runs[run_id].done_event.wait(), 5)

    assert registry._runs[run_id].status == "cancelled"


@pytest.mark.anyio
async def test_a_cancellation_of_the_parent_task_still_propagates_despite_a_stale_cancel_count(tmp_path):
    """Preservation: the registry task's own cancellation is not turned into an outcome."""
    provider = _RecoversATaskGroupFailureThenStalls()
    runner = _runner(tmp_path)
    task = await _a_run_stalls(runner, provider.stall, _runtime(provider))

    task.cancel()

    assert await _result_of(task) == "CancelledError"


@pytest.mark.anyio
async def test_the_parents_cancellation_at_the_same_moment_as_cancel_still_propagates_despite_a_stale_count(
    tmp_path,
):
    """Preservation: both requests land in one loop turn, the stale count is there too, and the
    parent's cancellation wins."""
    provider = _RecoversATaskGroupFailureThenStalls()
    runner = _runner(tmp_path)
    task = await _a_run_stalls(runner, provider.stall, _runtime(provider))

    task.cancel()
    runner.cancel()

    assert await _result_of(task) == "CancelledError"


# -- A branch run cancelled while its call runs -----------------------------------------------------------


class _BranchRun:
    """A branch run through the real registry and runner.

    The worktree creation, its removal and the branch-head check are faked (they shell out to git);
    the head never moves, so a run that settles ``done`` is relabelled "no commit on branch". The
    first reply has substantive text and a tool call, which a held registry keeps running; the
    provider never stalls.
    """

    def __init__(self, tmp_path, monkeypatch):
        import ayder_cli.agents.registry as registry_module

        self.tool = HeldRegistry()
        provider = ScriptedProvider(
            [chunk(content="Working on it. ", calls=[delta("c1", "read_file", '{"file_path": "a.py"}')])],
            [chunk(content="done")],
        )
        monkeypatch.setattr(registry_module, "is_git_repo", lambda root: True)
        monkeypatch.setattr(registry_module, "detect_base_branch", lambda root: "main")
        monkeypatch.setattr(
            registry_module, "add_worktree",
            lambda root, wt_dir, branch, base: os.makedirs(wt_dir, exist_ok=True),
        )
        monkeypatch.setattr(registry_module, "branch_head", lambda root, branch: "abc123")
        monkeypatch.setattr(registry_module, "remove_worktree", lambda root, wt: None)
        monkeypatch.setattr(
            runner_module, "create_agent_runtime", lambda **kwargs: _runtime(provider, self.tool)
        )
        self.registry = AgentRegistry(
            agents={"coder": AgentConfig(name="coder", system_prompt="x")},
            parent_config=MagicMock(),
            project_ctx=ProjectContext(str(tmp_path)),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=30,
            max_concurrent_agents=1,
        )

    async def cancelled_while_its_call_runs(self) -> int:
        self.registry.set_loop(asyncio.get_running_loop())
        run_id = self.registry.create_run("coder", "do it", branch_name="agent/cancel-me")
        deadline = time.monotonic() + 5
        while not self.tool.entered.is_set():
            assert time.monotonic() < deadline, "the call never started"
            await asyncio.sleep(0.01)
        self.registry.cancel("coder")
        self.tool.release.set()  # the held call ends; the run is already cancelled
        # Not await_run: reading the result drains it, which would hide it from pending_nudge().
        await asyncio.wait_for(self.registry._runs[run_id].done_event.wait(), 10)
        return run_id


@pytest.mark.anyio
async def test_a_branch_run_cancelled_while_its_call_runs_settles_cancelled(tmp_path, monkeypatch):
    """Baseline regression: the flag stops the loop before the next request, the runner settles
    ``done`` with the reply's text, and the registry relabels it ``error``."""
    branch = _BranchRun(tmp_path, monkeypatch)
    run_id = await branch.cancelled_while_its_call_runs()

    assert branch.registry._runs[run_id].status == "cancelled"


@pytest.mark.anyio
async def test_a_cancelled_branch_run_is_not_relabelled_no_commit(tmp_path, monkeypatch):
    """Baseline regression: the no-commit relabel applies to ``done`` only."""
    branch = _BranchRun(tmp_path, monkeypatch)
    run_id = await branch.cancelled_while_its_call_runs()

    assert branch.registry._runs[run_id].error != "no commit on branch"


@pytest.mark.anyio
async def test_a_cancelled_branch_run_is_not_nudged(tmp_path, monkeypatch):
    """Baseline regression: the relabelled ``error`` is unread and unnudged today."""
    branch = _BranchRun(tmp_path, monkeypatch)
    run_id = await branch.cancelled_while_its_call_runs()

    assert run_id not in [run.run_id for run in branch.registry.pending_nudge()]
