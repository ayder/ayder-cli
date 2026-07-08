"""The turn consumer runs one ChatLoop.run() at a time and awaits teardown on interrupt."""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock
import pytest

from ayder_cli.tui.types import ConfirmResult


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _app(monkeypatch):
    from ayder_cli.tui.app import AyderApp
    app = AyderApp.__new__(AyderApp)
    app._requests = asyncio.Queue()
    app._run_task = None
    app._agent_registry = None
    app.messages = []
    monkeypatch.setattr(app, "_after_turn_finished", lambda: None, raising=False)
    monkeypatch.setattr(app, "_report_turn_error", lambda e: None, raising=False)
    return app


class _FakeCallbacks:
    def __init__(self):
        self.events = []

    def on_tool_start(self, call_id, name, arguments):
        self.events.append(("start", name, arguments))

    def on_tool_complete(self, call_id, result):
        self.events.append(("complete", result))

    def on_tools_cleanup(self):
        self.events.append(("cleanup",))


def _shell_app(monkeypatch, *, permissions=None):
    from ayder_cli.tui.app import AyderApp

    granted = {"x"} if permissions is None else set(permissions)
    app = AyderApp.__new__(AyderApp)
    app._requests = asyncio.Queue()
    app._run_task = None
    app._agent_registry = None
    app.messages = []
    app._callbacks = _FakeCallbacks()
    app.registry = MagicMock()
    app.registry.execute.return_value = "Exit Code: 0\nSTDOUT:\nhi\n"
    app.chat_loop = MagicMock()
    app.chat_loop.config.permissions = granted
    app._request_confirmation = AsyncMock(return_value=ConfirmResult("approve"))
    monkeypatch.setattr(app, "_after_turn_finished", lambda: None, raising=False)
    monkeypatch.setattr(app, "_report_turn_error", lambda e: None, raising=False)

    chat = MagicMock()
    thinking = MagicMock()

    def query_one(selector, *args, **kwargs):
        if selector == "#chat-view":
            return chat
        if selector == "#thinking-panel":
            return thinking
        return MagicMock()

    app.query_one = query_one
    app._test_chat = chat
    app._test_thinking = thinking
    return app


@pytest.mark.anyio
async def test_interrupt_is_serialized(monkeypatch):
    app = _app(monkeypatch)
    order = []
    a_in = asyncio.Event()

    class FakeLoop:
        async def run(self, *, no_tools=False):
            if not a_in.is_set():
                a_in.set()
                order.append("A-start")
                try:
                    await asyncio.sleep(3600)
                finally:
                    order.append("A-exit")
            else:
                order.append("B-start")

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn()                                  # A
    await asyncio.wait_for(a_in.wait(), 1)
    app.request_turn(interrupt=True)                    # B interrupts A
    for _ in range(100):
        await asyncio.sleep(0)
        if order[-1:] == ["B-start"]:
            break
    assert order == ["A-start", "A-exit", "B-start"]    # A fully exits BEFORE B starts
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_prepare_runs_only_when_quiescent(monkeypatch):
    app = _app(monkeypatch)
    events = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            events.append("run")
            await asyncio.sleep(0)

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn(prepare=lambda: events.append("prep1"))
    app.request_turn(prepare=lambda: events.append("prep2"))
    for _ in range(50):
        await asyncio.sleep(0)
        if events.count("run") == 2:
            break
    # each prepare immediately precedes its own run; prepares never interleave a run
    assert events == ["prep1", "run", "prep2", "run"]
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_run_loop_false_mutates_without_starting_a_turn(monkeypatch):
    app = _app(monkeypatch)
    ran = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            ran.append(1)

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    done = []
    app.request_turn(prepare=lambda: done.append("mutated"), run_loop=False)
    for _ in range(50):
        await asyncio.sleep(0)
        if done:
            break
    assert done == ["mutated"] and ran == []     # prepare ran; no ChatLoop.run
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_ctrl_c_cancels_active_turn_but_preserves_queue(monkeypatch):
    # finding 4: action_cancel cancels only the active turn; queued requests survive.
    app = _app(monkeypatch)
    monkeypatch.setattr(app, "query_one", lambda *a, **k: MagicMock())
    app._activity_timer = None
    app._cancel_event = None
    started = []
    a_in = asyncio.Event()

    class FakeLoop:
        async def run(self, *, no_tools=False):
            started.append("turn")
            if len(started) == 1:
                a_in.set()
                await asyncio.sleep(3600)        # A blocks until cancelled

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn()                            # A (runs, blocks)
    await asyncio.wait_for(a_in.wait(), 1)
    app.request_turn()                            # B queued behind A
    app.action_cancel()                           # Ctrl+C — must NOT drain B
    for _ in range(100):
        await asyncio.sleep(0)
        if len(started) == 2:
            break
    assert started == ["turn", "turn"]            # B still ran after A was cancelled
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_shell_shortcut_executes_bash_and_appends_before_llm(monkeypatch):
    app = _shell_app(monkeypatch, permissions={"x"})
    events = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            events.append(("run", list(app.messages)))

    app.chat_loop.run = FakeLoop().run
    engine = asyncio.create_task(app._turn_consumer())

    app._handle_shell_shortcut("!echo hi")
    for _ in range(100):
        await asyncio.sleep(0)
        if events:
            break

    app.registry.execute.assert_called_once_with(
        "bash", {"command": "echo hi", "shell": "bash"}
    )
    assert app._test_chat.add_user_message.call_args.args == ("!echo hi",)
    assert app.messages == [
        {
            "role": "user",
            "content": "Shell command executed:\n$ echo hi\n\nResult:\nExit Code: 0\nSTDOUT:\nhi\n",
        }
    ]
    assert events == [("run", list(app.messages))]
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_shell_shortcut_confirmation_denied_does_not_execute_or_run(monkeypatch):
    app = _shell_app(monkeypatch, permissions={"r"})
    app._request_confirmation = AsyncMock(return_value=ConfirmResult("deny"))
    ran = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            ran.append(True)

    app.chat_loop.run = FakeLoop().run
    engine = asyncio.create_task(app._turn_consumer())

    app._handle_shell_shortcut("!echo hi")
    for _ in range(100):
        await asyncio.sleep(0)
        if app._test_chat.add_system_message.called:
            break

    app.registry.execute.assert_not_called()
    assert ran == []
    assert app.messages == []
    app._test_chat.add_system_message.assert_called_with("Shell command skipped.")
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


def test_empty_shell_shortcut_does_not_enqueue(monkeypatch):
    app = _shell_app(monkeypatch)

    app._handle_shell_shortcut("!")

    app.registry.execute.assert_not_called()
    assert app._requests.empty()
    app._test_chat.add_system_message.assert_called_with("Shell command is empty.")


@pytest.mark.anyio
async def test_skill_replacement_keeps_chat_loop_messages_connected(monkeypatch):
    from ayder_cli.tui.app import AyderApp

    app = _app(monkeypatch)
    app.messages = [{"role": "system", "content": "base"}]
    app._active_skill = None
    app.chat_loop = MagicMock(messages=app.messages)
    messages_id = id(app.messages)

    app.inject_skill("alpha", "Alpha body")
    app.inject_skill("beta", "Beta body")

    active = [
        message
        for message in app.chat_loop.messages
        if message["content"].startswith("### ACTIVE SKILL:")
    ]
    assert id(app.messages) == messages_id
    assert app.chat_loop.messages is app.messages
    assert len(active) == 1
    assert "Beta body" in active[0]["content"]
    assert isinstance(app, AyderApp)


@pytest.mark.anyio
async def test_skill_tool_load_visible_before_next_llm_iteration(tmp_path, monkeypatch):
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.tools.builtins.skill import skill

    skill_dir = tmp_path / ".ayder" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Alpha body", encoding="utf-8")

    app = _app(monkeypatch)
    app.messages = [{"role": "system", "content": "base"}]
    app._active_skill = None
    app.query_one = MagicMock(return_value=MagicMock())
    seen = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            seen.append(list(app.messages))

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())

    def _prepare():
        skill(ProjectContext(str(tmp_path)), "load", name="alpha", app=app)

    app.request_turn(prepare=_prepare)
    for _ in range(100):
        await asyncio.sleep(0)
        if seen:
            break

    assert any(
        message["content"].startswith("### ACTIVE SKILL:")
        and "Alpha body" in message["content"]
        for message in seen[0]
    )
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine
