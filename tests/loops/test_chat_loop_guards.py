"""The chat loop always ends, and flags repeats, huge echoes and repaired
arguments (audit P1-6, P2-23, P2-24).

No network (environment: local-faked).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from ayder_cli.agents.config import AgentConfig
from ayder_cli.core.config import Config
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig
from ayder_cli.providers.base import NormalizedStreamChunk, ToolCallDef


class _Provider:
    """Replays one scripted reply per LLM call; the last reply repeats."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    async def stream_with_tools(self, *a, **k):
        # Yield to the event loop, so a loop that never ends still lets the
        # test's wait_for time out instead of hanging the suite.
        await asyncio.sleep(0)
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        chunk = NormalizedStreamChunk()
        chunk.content = reply.get("content", "")
        chunk.reasoning = reply.get("reasoning", "")
        if "tool" in reply:
            name, args = reply["tool"]
            chunk.tool_calls = [ToolCallDef(id=f"c{self.calls}", name=name, arguments=args)]
        yield chunk


def _tool(name="read_file", args='{"file_path": "a.py"}'):
    return {"tool": (name, args)}


class _Registry:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return "ok"

    def get_schemas(self, tags=None):
        return []


class _Callbacks:
    def __init__(self):
        self.system: list[str] = []

    def on_thinking_start(self): ...
    def on_thinking_stop(self): ...
    def on_assistant_content(self, text): ...
    def on_thinking_content(self, text): ...
    def on_token_usage(self, total_tokens): ...
    def on_tool_start(self, call_id, name, arguments): ...
    def on_tool_complete(self, call_id, result): ...
    def on_tools_cleanup(self): ...
    def on_system_message(self, text):
        self.system.append(text)
    async def request_confirmation(self, name, arguments):
        return SimpleNamespace(action="approve")
    def is_cancelled(self):
        return False


class _Context:
    session_id = None
    run_id = None

    def prepare_messages(self, messages, max_history=0):
        return list(messages)

    def update_from_response(self, usage):
        pass


def _loop(provider, registry=None, **config):
    return ChatLoop(
        llm=provider,
        registry=registry or _Registry(),
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}],
        config=ChatLoopConfig(permissions={"r", "w", "x", "http"}, **config),
        callbacks=_Callbacks(),
        context_manager=_Context(),
    )


def _tool_messages(loop):
    return [m["content"] for m in loop.messages if m["role"] == "tool"]


# --- P1-6: iteration cap -----------------------------------------------------


def test_tool_loop_stops_at_max_iterations():
    """New interface: a model that always calls a tool used to loop forever."""
    provider = _Provider(_tool())
    loop = _loop(provider, max_iterations=3)
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    assert provider.calls == 3
    assert any("max_iterations = 3" in s and s.startswith("Error:") for s in loop.cb.system)


def test_zero_means_unlimited():
    """Preservation: with no cap the loop runs until the text-only reply."""
    provider = _Provider(_tool(), _tool(), _tool(), _tool(), {"content": "done"})
    loop = _loop(provider, max_iterations=0)
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    assert provider.calls == 5 and loop.cb.system == []


def test_reasoning_only_stops_after_two_retries():
    """Baseline regression: reasoning-only replies were retried forever."""
    provider = _Provider({"reasoning": "hmm"})
    loop = _loop(provider)
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    assert provider.calls == 3
    assert any("only reasoning" in s for s in loop.cb.system)
    assert loop.messages[-1]["role"] == "assistant"


def test_reasoning_then_text_completes():
    """Preservation: one retry prompt, then the final answer."""
    provider = _Provider({"reasoning": "hmm"}, {"content": "answer"})
    loop = _loop(provider)
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    assert provider.calls == 2 and loop.cb.system == []
    assert loop.messages[-1] == {"role": "assistant", "content": "answer"}


def test_config_max_iterations():
    """New interface: [app] max_iterations, default 200, 0 = unlimited."""
    assert Config().max_iterations == 200
    assert Config(**{"app": {"max_iterations": 50}}).max_iterations == 50
    assert Config(**{"app": {"max_iterations": 0}}).max_iterations == 0
    with pytest.raises(ValidationError):
        Config(**{"app": {"max_iterations": -1}})


def test_agent_config_max_iterations():
    """New interface: [agents.<name>] max_iterations, numeric strings coerced."""
    assert AgentConfig(name="a").max_iterations is None
    assert AgentConfig(name="a", max_iterations="7").max_iterations == 7


@pytest.mark.parametrize("configured, expected", [(None, 100), (7, 7), (0, 0)])
def test_agent_runner_passes_max_iterations(configured, expected):
    """New interface: an agent run uses its own cap, or 100."""
    from ayder_cli.agents.runner import AgentRunner

    parent = MagicMock(model="m", num_ctx=4096, max_output_tokens=2048, stop_sequences=[],
                       tool_tags=["core"], provider="openai", max_history_messages=0)
    runner = AgentRunner(
        agent_config=AgentConfig(name="a", max_iterations=configured),
        parent_config=parent, project_ctx=MagicMock(), process_manager=MagicMock(),
        permissions={"r"}, timeout=10,
    )
    rt = MagicMock(config=parent, system_prompt="s")
    with patch("ayder_cli.agents.runner.create_agent_runtime", return_value=rt), \
         patch("ayder_cli.agents.runner.ChatLoop") as MockLoop, \
         patch.object(runner, "_persist_note", return_value=None):
        MockLoop.return_value.run = AsyncMock()
        asyncio.run(runner.run("task"))
    assert MockLoop.call_args.kwargs["config"].max_iterations == expected


# --- P1-6: repetition note ---------------------------------------------------

from ayder_cli.providers.base import _FunctionCall, _ToolCall  # noqa: E402

READ_A = '{"file_path": "a.py"}'
NOTE = "[harness] identical call repeated"


def _call(name, arguments, call_id):
    return _ToolCall(id=call_id, type="function",
                     function=_FunctionCall(name=name, arguments=arguments))


def _batch(loop, *calls):
    asyncio.run(loop._execute_tool_calls(list(calls)))
    return {m["tool_call_id"]: m["content"] for m in loop.messages if m["role"] == "tool"}


def test_third_identical_call_gets_note_in_one_batch():
    """Baseline regression: nothing told the model it was repeating itself."""
    out = _batch(_loop(None), *(_call("read_file", READ_A, f"c{i}") for i in (1, 2, 3)))
    assert NOTE not in out["c1"] and NOTE not in out["c2"]
    assert f"{NOTE} 3 times in a row" in out["c3"]


def test_identical_calls_across_iterations_get_note():
    """Baseline regression: the same call in every iteration, with no note."""
    loop = _loop(_Provider(_tool(args=READ_A)), max_iterations=4)
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    notes = [NOTE in c for c in _tool_messages(loop)]
    assert notes == [False, False, True, True]
    assert "repeated 4 times" in _tool_messages(loop)[3]


def test_two_identical_calls_no_note():
    """Preservation: a repeat, or a changed argument, is not flagged."""
    out = _batch(_loop(None), _call("read_file", READ_A, "c1"), _call("read_file", READ_A, "c2"),
                 _call("read_file", '{"file_path": "b.py"}', "c3"),
                 _call("read_file", READ_A, "c4"))
    assert not any(NOTE in v for v in out.values())


# --- P2-23: bounded argument echo ---------------------------------------------


def test_missing_arg_echo_is_bounded():
    """Baseline regression: a 100 KB argument came back whole in the error."""
    raw = json.dumps({"operation": "write", "content": "x" * 100_000})
    out = _batch(_loop(None), _call("file_editor", raw, "c1"))["c1"]
    assert "missing required arguments: file_path" in out
    assert len(out) < 1000 and f"({len(repr(raw))} chars)" in out


def test_short_missing_arg_echo_unchanged():
    """Preservation: a short echo is shown whole."""
    raw = '{"operation": "write"}'
    out = _batch(_loop(None), _call("file_editor", raw, "c1"))["c1"]
    assert f"Raw arguments received: {raw!r}." in out


# --- P2-24: repaired-argument prefix -------------------------------------------

REPAIRED = "[harness] arguments were truncated and repaired"


def test_repaired_read_gets_prefix():
    """Baseline regression: a read ran on cut-off arguments without a word."""
    out = _batch(_loop(None), _call("read_file", '{"file_path": "a.py", "start_line": 1', "c1"))
    assert out["c1"].startswith(REPAIRED)


def test_ok_read_has_no_prefix():
    """Preservation."""
    assert REPAIRED not in _batch(_loop(None), _call("read_file", READ_A, "c1"))["c1"]


# --- final review fixes --------------------------------------------------------


@pytest.mark.parametrize("run_id, where", [(None, "[app] max_iterations"),
                                           (1, "[agents.<name>] max_iterations")])
def test_cap_message_says_how_to_continue(run_id, where):
    """Review (I2): the stop named the setting but gave no next step."""
    loop = _loop(_Provider(_tool()), max_iterations=2, run_id=run_id)
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    (msg,) = loop.cb.system
    assert msg.startswith("Error: stopped after 2 LLM calls (max_iterations = 2).")
    assert where in msg and "0 = unlimited" in msg
    assert ("Send a message to continue" in msg) == (run_id is None)


class _RaisingRegistry(_Registry):
    def execute(self, name, arguments):
        raise RuntimeError("boom")


def test_repaired_read_that_raises_gets_prefix():
    """Review (M2): the warning was missing when the tool raised."""
    loop = _loop(None, registry=_RaisingRegistry())
    out = _batch(loop, _call("read_file", '{"file_path": "a.py", "start_line": 1', "c1"))
    assert "boom" in out["c1"] and out["c1"].startswith(REPAIRED)
