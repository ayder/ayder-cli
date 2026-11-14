"""The skill label shows the active set a tool batch really ends with.

Every skill call in a batch reads the history from before the batch (ChatLoop
appends the batch's results only after all of them ran), so the label each
call sets can be stale, in parallel or in series. AppCallbacks.on_tools_cleanup
runs after the append and refreshes the label from the final history.

The real skill tool runs through ChatLoop._execute_tool_calls; the TUI is a
fake app object (unit layer, no Textual app). No network (local-faked).
"""
from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.skills import SkillScope, active_skills
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig
from ayder_cli.providers.base import _FunctionCall, _ToolCall
from ayder_cli.tools.builtins.skill import skill
from ayder_cli.tui.app import AppCallbacks


class _Widget:
    """Any widget AppCallbacks touches; records set_skill values."""

    def __init__(self, labels: list):
        self._labels = labels

    def set_skill(self, text):
        self._labels.append(text)

    def __getattr__(self, name):          # set_tools_working, add_tool, ...
        return lambda *a, **k: None


def _fake_app(messages: list) -> SimpleNamespace:
    labels: list = []
    lock = threading.Lock()

    def query_one(selector, cls=None):
        with lock:
            return _Widget(labels)

    return SimpleNamespace(messages=messages, labels=labels, query_one=query_one,
                           call_later=lambda fn, *a, **k: None,
                           set_timer=lambda *a, **k: None,
                           _start_activity_timer=lambda: None)


class _Registry:
    """Runs the real skill tool against the loop's own history."""

    def __init__(self, root: Path, app):
        self.skill_scope = SkillScope(project_root=root)   # ChatLoop binds .messages
        self._ctx, self._app = ProjectContext(str(root)), app

    def execute(self, name, arguments):
        return str(skill(self._ctx, app=self._app, skill_scope=self.skill_scope, **arguments))

    def get_schemas(self, tags=None):
        return []


class _Context:
    session_id = None
    run_id = None

    def prepare_messages(self, messages, max_history=0):
        return list(messages)

    def update_from_response(self, usage):
        pass


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / ".ayder" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\ndescription: {name}\n---\nBody", encoding="utf-8")


def _call(call_id: str, **args) -> _ToolCall:
    return _ToolCall(id=call_id, type="function",
                     function=_FunctionCall(name="skill", arguments=json.dumps(args)))


def _run_batch(tmp_path, preloaded, calls):
    for name in ("alpha", "beta"):
        _write_skill(tmp_path, name)
    messages: list = []
    app = _fake_app(messages)
    registry = _Registry(tmp_path, app)
    loop = ChatLoop(llm=None, registry=registry, messages=messages,
                    config=ChatLoopConfig(permissions={"r"}),
                    callbacks=AppCallbacks(app), context_manager=_Context())
    for name in preloaded:   # a load from an earlier turn, as history holds it
        messages.append({"role": "tool", "tool_call_id": f"pre_{name}", "name": "skill",
                         "content": registry.execute("skill", {"action": "load", "name": name})})
    app.labels.clear()

    async def main():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=8))
        await loop._execute_tool_calls(calls)

    asyncio.run(main())
    return app.labels, [load.name for load in active_skills(messages)]


def test_label_shows_the_final_set_after_load_and_unload_in_one_batch(tmp_path):
    """Baseline regression: load beta + unload alpha left the label at "" or "alpha, beta"."""
    labels, final = _run_batch(tmp_path, ["alpha"], [
        _call("c1", action="load", name="beta"), _call("c2", action="unload", name="alpha")])
    assert final == ["beta"]
    assert labels[-1] == "beta", labels


def test_label_shows_both_skills_loaded_in_one_batch(tmp_path):
    """Baseline regression: two loads in one batch left the label naming only one."""
    labels, final = _run_batch(tmp_path, [], [
        _call("c1", action="load", name="alpha"), _call("c2", action="load", name="beta")])
    assert final == ["alpha", "beta"]
    assert labels[-1] == "alpha, beta", labels
