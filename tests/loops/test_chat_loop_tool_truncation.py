"""Tool result truncation: generic tools are bounded by the chat-loop, while
tools that paginate their own output (``max_result_chars=0``) pass through
unmodified.

Opus47 finding #1 (the original regression this file guards): full
untruncated tool output was landing in ``self.messages``, defeating
KV-cache reuse and violating the Ollama immutability contract. That guard
is preserved here for non-exempt tools.
"""
import pytest
from unittest.mock import MagicMock

from ayder_cli.core.context_manager import truncate_tool_result
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig


class _Chunk:
    """Minimal stream chunk that ChatLoop understands."""

    def __init__(self, content="", reasoning="", tool_calls=None, usage=None):
        self.content = content
        self.reasoning = reasoning
        self.tool_calls = tool_calls or []
        self.usage = usage


class _ToolCallChunk:
    """Shape expected by ChatLoop inner loop (matches providers.base ToolCallDef)."""

    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.name = name
        self.arguments = arguments
        self._stream_index = 0


def _make_provider(tool_name: str, arguments: str = '{}'):
    class _FakeProvider:
        def __init__(self):
            self._turn = 0

        async def stream_with_tools(self, messages, model, tools, options, verbose):
            if self._turn == 0:
                self._turn += 1
                yield _Chunk(
                    tool_calls=[_ToolCallChunk("call_1", tool_name, arguments)],
                    usage={"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5},
                )
            else:
                yield _Chunk(
                    content="Done.",
                    usage={"total_tokens": 20, "prompt_tokens": 15, "completion_tokens": 5},
                )

    return _FakeProvider()


class FakeCallbacks:
    def __init__(self):
        self._calls = 0

    def on_thinking_start(self): pass
    def on_thinking_stop(self): pass
    def on_assistant_content(self, text): pass
    def on_thinking_content(self, text): pass
    def on_token_usage(self, total_tokens): pass
    def on_tool_start(self, call_id, name, arguments): pass
    def on_tool_complete(self, call_id, result): pass
    def on_tools_cleanup(self): pass
    def on_system_message(self, text): pass

    async def request_confirmation(self, name, arguments):
        approval = MagicMock()
        approval.action = "approve"
        return approval

    def is_cancelled(self):
        self._calls += 1
        return self._calls > 4


def _run_loop(
    tool_name: str, fake_result: str, arguments: str = '{}', *, verbose: bool = False,
    messages: list[dict] | None = None,
) -> tuple[list[dict], ChatLoop]:
    registry = MagicMock()
    registry.get_schemas.return_value = [
        {"type": "function", "function": {"name": tool_name, "parameters": {}}}
    ]
    registry.execute.return_value = fake_result

    if messages is None:
        messages = [{"role": "system", "content": "test"}]
    loop = ChatLoop(
        llm=_make_provider(tool_name, arguments=arguments),
        registry=registry,
        messages=messages,
        config=ChatLoopConfig(permissions={"r", "w", "x"}, verbose=verbose),
        callbacks=FakeCallbacks(),
    )
    return messages, loop


@pytest.mark.anyio
async def test_generic_tool_result_truncated_in_message_history():
    """Tools without ``max_result_chars`` go through the loop's default
    truncation once they exceed the cap. Guards against Opus47 finding #1."""
    huge = "x" * 100_000  # exceeds the 65535-char default cap

    messages, loop = _run_loop(
        "search_codebase", huge, arguments='{"pattern": "x"}'
    )
    await loop.run()

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "expected at least one tool message in history"

    stored = tool_msgs[0]["content"]
    expected_truncated = truncate_tool_result(huge)

    assert stored == expected_truncated, (
        f"Stored length={len(stored)}, expected length={len(expected_truncated)}, "
        f"raw length={len(huge)}."
    )
    assert len(stored) < len(huge)


@pytest.mark.anyio
async def test_generic_tool_result_under_new_cap_passes_through():
    """The default cap is 65535: a generic result under it reaches history
    untruncated (the bump from the old 8192 cap)."""
    payload = "x" * 50_000  # > old 8192 cap, < new 65535 cap

    messages, loop = _run_loop(
        "search_codebase", payload, arguments='{"pattern": "x"}'
    )
    await loop.run()

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "expected at least one tool message in history"

    stored = tool_msgs[0]["content"]
    assert stored == payload, (
        f"a {len(payload)}-char result must pass through under the 65535 cap; "
        f"got {len(stored)} chars."
    )


@pytest.mark.anyio
async def test_malformed_tool_arguments_do_not_leak_raw_content(loguru_caplog):
    """A malformed tool-call argument string must never appear verbatim in
    the warnings logged while parsing or repairing it -- only its length.

    Regression for three chat_loop.py leaks found in security review of
    commit 38676b2: the history-repair warning, ``_parse_arguments``'s own
    parse-failure warning, and the missing-required-args warning -- all of
    which used to interpolate the raw (or ``{!r:.200}``-truncated -- still
    raw) argument string/dict directly into the log message.
    """
    secret = "sk-proj-SENTINEL-DO-NOT-LOG-1234567890"
    malformed = '{"value": "' + secret + '"'  # unterminated -> invalid JSON

    _messages, loop = _run_loop("manage_environment_vars", "ok", arguments=malformed)
    await loop.run()

    warnings = loguru_caplog.only("WARNING")
    assert warnings, "expected at least one warning while parsing the malformed arguments"
    assert secret not in loguru_caplog.text, "raw argument content must never reach the log"
    assert any(str(len(malformed)) in msg for msg in warnings.messages), (
        "expected the char count to be logged in place of the raw content"
    )


@pytest.mark.anyio
async def test_tool_result_and_exception_history_trace_do_not_leak_raw_content(loguru_caplog):
    """The TRACE records logged when a tool result (or a raised exception) is
    appended to history must carry a length, not the content itself.

    Found while writing the test above: a missing-required-arg tool call
    produces an error message that legitimately echoes the raw arguments
    back to the LLM (by design, so it can self-correct) -- but that same
    string used to also reach the log verbatim via the "Appending Tool
    Result" TRACE call. This test drives both the success path (a `result`
    containing caller content) and the exception path (a raised error
    containing caller content) and asserts neither leaks.
    """
    secret = "sk-proj-SENTINEL-DO-NOT-LOG-1234567890"

    # Success path: the mocked registry "result" itself carries the secret,
    # simulating a tool result (or an echoed-argument error string) that
    # contains caller-supplied content.
    messages, loop = _run_loop(
        "manage_environment_vars", f"leaked result containing {secret}",
        arguments='{"mode": "set", "variable_name": "OPENAI_API_KEY", "value": "x"}',
    )
    await loop.run()
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert any(secret in m["content"] for m in tool_msgs), (
        "test setup didn't actually exercise the success path with the secret"
    )
    assert secret not in loguru_caplog.text

    # Exception path: the registry raises with the secret in the message.
    messages2, loop2 = _run_loop(
        "manage_environment_vars", "unused",
        arguments='{"mode": "set", "variable_name": "OPENAI_API_KEY", "value": "x"}',
    )
    loop2.registry.execute.side_effect = ValueError(f"boom: {secret}")
    await loop2.run()
    tool_msgs2 = [m for m in messages2 if m.get("role") == "tool"]
    assert any(secret in m["content"] for m in tool_msgs2), (
        "test setup didn't actually exercise the exception path with the secret"
    )
    assert secret not in loguru_caplog.text


@pytest.mark.anyio
async def test_verbose_message_trace_does_not_leak_content(loguru_caplog):
    """The verbose per-message TRACE record must carry only role/type/length
    metadata, never the message content itself -- not even a repr prefix.

    Regression for the chat_loop.py:143 leak found in security review:
    `repr(content)[:200]` truncates but still emits up to 200 raw
    characters, and truncation is not redaction.
    """
    secret = "sk-proj-SENTINEL-DO-NOT-LOG-1234567890"
    seed_messages = [
        {"role": "system", "content": "test"},
        {"role": "user", "content": f"please rotate this key: {secret}"},
    ]

    messages, loop = _run_loop(
        "search_codebase", "ok", arguments='{"pattern": "x"}',
        verbose=True, messages=seed_messages,
    )
    await loop.run()

    # Point 1: prove the secret genuinely reached the seeded conversation
    # that the verbose trace loop iterates over.
    assert any(secret in m.get("content", "") for m in messages), (
        "test setup didn't actually seed the secret into the conversation"
    )

    hits = [r for r in loguru_caplog.records if r["message"].startswith("  Message ")]
    assert hits, "verbose per-message trace record never emitted"
    assert all(h["level"].name == "TRACE" for h in hits)
    assert all(h["extra"]["channel"] == "llm" for h in hits)
    assert any("content_len=" in h["message"] for h in hits), (
        "expected content_type/content_len metadata to be logged"
    )
    assert secret not in loguru_caplog.text


@pytest.mark.anyio
async def test_read_file_result_passes_through_untruncated():
    """``read_file`` declares ``max_result_chars=0`` because it paginates
    internally. The chat loop must not apply head+tail truncation to its
    output — that would silently corrupt the deliberately-bounded page."""
    paginated = "x" * 50_000  # stand-in for a fully-paginated read_file payload

    messages, loop = _run_loop(
        "read_file", paginated, arguments='{"file_path": "big.txt"}'
    )
    await loop.run()

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "expected at least one tool message in history"

    stored = tool_msgs[0]["content"]
    assert stored == paginated, (
        "read_file output must reach message history unmodified — "
        f"got {len(stored)} chars, expected {len(paginated)}."
    )
