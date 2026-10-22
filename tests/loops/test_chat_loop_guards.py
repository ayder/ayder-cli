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
