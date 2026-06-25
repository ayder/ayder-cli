"""Worktree isolation lifecycle (spec 05, Task 5)."""

import asyncio
import os
import shutil
import subprocess

import pytest

from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.runner import AgentRunOutcome
from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.notes import write_agent_note

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


class _Cfg:
    name = "coder"
    model = "test-model"
    system_prompt = "x"


def _init_repo(path):
    root = str(path)
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", root],
                   capture_output=True, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    with open(os.path.join(root, "README.md"), "w") as f:
        f.write("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=root, capture_output=True, check=True)
    return root


def _registry(pctx, cap=2):
    return AgentRegistry(
        agents={"coder": _Cfg()}, parent_config=_Cfg(), project_ctx=pctx,
        process_manager=None, permissions={"r", "w", "x"},
        agent_timeout=30, max_concurrent_agents=cap,
    )


def _committing_runner():
    """Fake runner: writes+commits a file in its (worktree) project_ctx, and
    persists a note via notes_ctx — proving both the cwd swap and note routing."""
    class _R:
        def __init__(self, *a, **k):
            self.agent_name = "coder"
            self.status = "idle"
            self._project_ctx = k["project_ctx"]
            self._notes_ctx = k["notes_ctx"]
            self.run_id = k["run_id"]

        def cancel(self):
            self.status = "cancelled"
            return True

        async def run(self, task):
            root = str(self._project_ctx.root)
            with open(os.path.join(root, f"file_{self.run_id}.txt"), "w") as f:
                f.write("work")
            subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"work {self.run_id}"],
                           cwd=root, capture_output=True)
            note = write_agent_note(
                self._notes_ctx, agent_name="coder", run_id=self.run_id,
                generation=0, status="done", task=task, content="did it",
                timestamp=f"t{self.run_id}",
            )
            return AgentRunOutcome("done", "did it", None, note)
    return _R


@needs_git
@pytest.mark.asyncio
async def test_two_coders_isolated_committed_and_cleaned(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    reg = _registry(ProjectContext(repo), cap=2)
    reg.set_loop(asyncio.get_running_loop())
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _committing_runner())

    r1 = reg.create_run("coder", "a", branch_name="agent/a")
    r2 = reg.create_run("coder", "b", branch_name="agent/b")
    await reg.await_run(r1, timeout_s=10)
    await reg.await_run(r2, timeout_s=10)

    assert reg._runs[r1].status == "done" and reg._runs[r2].status == "done"
    # each commit landed on its own branch (object store survives worktree removal)
    log_a = subprocess.run(["git", "log", "--oneline", "agent/a"], cwd=repo,
                           capture_output=True, text=True).stdout
    log_b = subprocess.run(["git", "log", "--oneline", "agent/b"], cwd=repo,
                           capture_output=True, text=True).stdout
    assert "work 1" in log_a and "work 2" in log_b
    # worktrees removed; git knows only the main worktree
    assert not os.path.isdir(os.path.join(repo, ".ayder", "worktrees", "a"))
    assert not os.path.isdir(os.path.join(repo, ".ayder", "worktrees", "b"))
    wl = subprocess.run(["git", "worktree", "list"], cwd=repo,
                        capture_output=True, text=True).stdout
    assert ".ayder/worktrees" not in wl
    # parent status clean of worktree files
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                            capture_output=True, text=True).stdout
    assert ".ayder/worktrees" not in status
    # deliverable notes survive at the parent
    notes_dir = os.path.join(repo, ".ayder", "notes")
    assert os.path.isdir(notes_dir) and os.listdir(notes_dir)


@needs_git
@pytest.mark.asyncio
async def test_worktree_path_in_payload(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    reg = _registry(ProjectContext(repo), cap=2)
    reg.set_loop(asyncio.get_running_loop())
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _committing_runner())

    rid = reg.create_run("coder", "a", branch_name="agent/feat")
    await reg.await_run(rid, timeout_s=10)
    payload = reg.read_result(rid)
    assert payload["worktree_path"].endswith(os.path.join(".ayder", "worktrees", "feat"))


@needs_git
@pytest.mark.asyncio
async def test_base_branch_param_used(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    subprocess.run(["git", "branch", "dev"], cwd=repo, check=True)
    # put a marker commit on dev so we can prove the worktree forked from it
    subprocess.run(["git", "switch", "dev"], cwd=repo, capture_output=True, check=True)
    with open(os.path.join(repo, "DEVMARK"), "w") as f:
        f.write("x")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "devmark"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "switch", "main"], cwd=repo, capture_output=True, check=True)

    seen = {}
    class _R:
        def __init__(self, *a, **k):
            self.agent_name = "coder"; self.status = "idle"
            seen["root"] = str(k["project_ctx"].root)
        def cancel(self): return True
        async def run(self, task):
            return AgentRunOutcome("done", "ok", None, None)
    reg = _registry(ProjectContext(repo), cap=1)
    reg.set_loop(asyncio.get_running_loop())
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _R)

    rid = reg.create_run("coder", "x", branch_name="agent/fromdev", base_branch="dev")
    await reg.await_run(rid, timeout_s=10)
    # the worktree forked from dev -> DEVMARK present in the worktree checkout
    # (captured before cleanup via the marker file having existed). Assert the
    # branch's base contains the dev commit:
    base = subprocess.run(["git", "log", "--oneline", "agent/fromdev"], cwd=repo,
                          capture_output=True, text=True).stdout
    assert "devmark" in base


@pytest.mark.asyncio
async def test_non_git_dir_fails_fast(tmp_path, monkeypatch):
    # A plain (non-git) project dir: a branch-carrying call must settle error and
    # create no worktree. No runner should ever run.
    ran = {"n": 0}
    class _R:
        def __init__(self, *a, **k): self.agent_name = "coder"; self.status = "idle"
        def cancel(self): return True
        async def run(self, task):
            ran["n"] += 1
            return AgentRunOutcome("done", "ok", None, None)
    reg = _registry(ProjectContext(str(tmp_path)), cap=1)
    reg.set_loop(asyncio.get_running_loop())
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _R)

    rid = reg.create_run("coder", "x", branch_name="agent/x")
    await reg.await_run(rid, timeout_s=10)
    assert reg._runs[rid].status == "error"
    assert "git" in (reg._runs[rid].error or "").lower()
    assert ran["n"] == 0
    assert not os.path.isdir(os.path.join(str(tmp_path), ".ayder", "worktrees", "x"))


@pytest.mark.asyncio
async def test_queued_branch_run_cancelled_creates_no_worktree(tmp_path, monkeypatch):
    # cap=1: run1 holds the slot; run2 (branch-carrying) is queued then cancelled.
    # add_worktree must never be called for run2.
    adds = []
    monkeypatch.setattr("ayder_cli.agents.registry.add_worktree",
                        lambda repo, wt, br, base: adds.append(br))
    monkeypatch.setattr("ayder_cli.agents.registry.remove_worktree",
                        lambda repo, wt: None)
    monkeypatch.setattr("ayder_cli.agents.registry.is_git_repo", lambda root: True)

    gate = asyncio.Event()
    class _R:
        def __init__(self, *a, **k): self.agent_name = "coder"; self.status = "idle"
        def cancel(self): self.status = "cancelled"; return True
        async def run(self, task):
            await gate.wait()
            return AgentRunOutcome("done", "ok", None, None)
    reg = _registry(ProjectContext(str(tmp_path)), cap=1)
    reg.set_loop(asyncio.get_running_loop())
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _R)

    reg.create_run("coder", "first", branch_name="agent/first")  # takes slot, blocks
    rid2 = reg.create_run("coder", "second", branch_name="agent/second")  # queued
    await asyncio.sleep(0.05)
    reg.cancel("coder")
    gate.set()
    for rid in list(reg._runs):
        await reg.await_run(rid, timeout_s=5)
    assert reg._runs[rid2].status == "cancelled"
    assert "agent/second" not in adds  # cancelled-while-queued never made a worktree


def test_call_threads_base_branch_to_create_run(monkeypatch):
    # tool.py: base_branch flows from the call into create_run.
    from ayder_cli.agents.tool import create_agent_handler

    captured = {}
    class _Reg:
        _loop = None
        def _on_loop(self, fn): return fn()
        def create_run(self, name, task, task_id=None, branch_name=None, base_branch=None):
            captured.update(name=name, branch_name=branch_name, base_branch=base_branch)
            return 1
        def run_label(self, rid): return None
    handler = create_agent_handler(_Reg())
    handler(action="call", name="coder", task="x",
            branch_name="agent/x", base_branch="dev")
    assert captured["base_branch"] == "dev"
