"""The chat loop keeps a tool call's ``thought_signature`` in the stored history (#13).

Kind: baseline regression. The assistant ``tool_calls`` entry the loop builds had no
place for the signature, so a provider that needs it replayed could never get it back.
Other providers' history must not change.

No network (environment: local-faked).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ayder_cli.providers.base import NormalizedStreamChunk, ToolCallDef
from tests.loops.test_chat_loop_guards import _loop


class _OneCallThenText:
    """Turn one yields ``tool_call``; turn two answers in text."""

    def __init__(self, tool_call):
        self.tool_call = tool_call
        self.calls = 0

    async def stream_with_tools(self, *a, **k):
        await asyncio.sleep(0)
        self.calls += 1
        chunk = NormalizedStreamChunk()
        if self.calls == 1:
            chunk.tool_calls = [self.tool_call]
        else:
            chunk.content = "done"
        yield chunk


def _stored_tool_call(tool_call) -> dict:
    loop = _loop(_OneCallThenText(tool_call))
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    (assistant,) = [m for m in loop.messages if m.get("tool_calls")]
    (stored,) = assistant["tool_calls"]
    return stored


def test_the_signature_is_stored_on_the_tool_call_entry():
    """New interface: the entry has no thought_signature today."""
    stored = _stored_tool_call(
        ToolCallDef(
            id="c1",
            name="read_file",
            arguments='{"file_path": "a.py"}',
            thought_signature="c2ln",
        )
    )

    assert stored["thought_signature"] == "c2ln"
    assert stored["function"] == {"name": "read_file", "arguments": '{"file_path": "a.py"}'}


def test_no_signature_means_no_key():
    """Preservation: history for the other providers is unchanged."""
    stored = _stored_tool_call(
        ToolCallDef(id="c1", name="read_file", arguments='{"file_path": "a.py"}')
    )

    assert "thought_signature" not in stored


def test_a_tool_call_object_without_the_attribute_does_not_raise():
    """Preservation: tests and plugins feed SimpleNamespace tool calls."""
    stored = _stored_tool_call(
        SimpleNamespace(id="c1", name="read_file", arguments='{"file_path": "a.py"}')
    )

    assert "thought_signature" not in stored
