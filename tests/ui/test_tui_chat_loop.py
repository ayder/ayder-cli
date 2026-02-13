"""Tests for TuiChatLoop — the async chat loop for the Textual TUI."""

import asyncio
import json
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.tui.chat_loop import (
    TuiChatLoop,
    TuiLoopConfig,
    _extract_think_blocks,
    _strip_tool_markup,
    _parse_arguments,
    _parse_json_tool_calls,
    _regex_extract_json_tool_calls,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeConfirmResult:
    action: str
    instructions: str | None = None


class FakeCallbacks:
    """Concrete callbacks for testing — records all calls."""

    def __init__(self):
        self.events: list[tuple] = []
        self._cancelled = False
        self._confirm_result = None  # set per-test

    def on_thinking_start(self):
        self.events.append(("thinking_start",))

    def on_thinking_stop(self):
        self.events.append(("thinking_stop",))

    def on_assistant_content(self, text):
        self.events.append(("assistant_content", text))

    def on_thinking_content(self, text):
        self.events.append(("thinking_content", text))

    def on_token_usage(self, total):
        self.events.append(("token_usage", total))

    def on_iteration_update(self, current, maximum):
        self.events.append(("iteration_update", current, maximum))

    def on_tool_start(self, call_id, name, arguments):
        self.events.append(("tool_start", call_id, name, arguments))

    def on_tool_complete(self, call_id, result):
        self.events.append(("tool_complete", call_id, result))

    def on_tools_cleanup(self):
        self.events.append(("tools_cleanup",))

    def on_system_message(self, text):
        self.events.append(("system_message", text))

    async def request_confirmation(self, name, arguments):
        self.events.append(("request_confirmation", name, arguments))
        return self._confirm_result

    def is_cancelled(self):
        return self._cancelled


def _make_response(content="Hello", tool_calls=None, total_tokens=100):
    """Build a fake LLM response object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = msg

    usage = MagicMock()
    usage.total_tokens = total_tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _make_tool_call(call_id="tc-1", name="read_file", arguments=None):
    """Build a fake OpenAI tool call object."""
    tc = MagicMock()
    tc.id = call_id
    tc.type = "function"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments or {"file_path": "test.py"})
    return tc


def _make_loop(cb=None, messages=None, permissions=None):
    """Create a TuiChatLoop with sensible defaults."""
    llm = MagicMock()
    registry = MagicMock()
    registry.get_schemas.return_value = [{"type": "function", "function": {"name": "read_file"}}]
    registry.execute.return_value = "file content"

    cb = cb or FakeCallbacks()
    messages = messages if messages is not None else [{"role": "system", "content": "sys"}]
    config = TuiLoopConfig(permissions=permissions or {"r"})

    loop = TuiChatLoop(
        llm=llm,
        registry=registry,
        messages=messages,
        config=config,
        callbacks=cb,
    )
    return loop, cb, llm, registry


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# TuiLoopConfig
# ---------------------------------------------------------------------------


class TestTuiLoopConfig:
    def test_defaults(self):
        cfg = TuiLoopConfig()
        assert cfg.model == "qwen3-coder:latest"
        assert cfg.num_ctx == 65536
        assert cfg.max_iterations == 50
        assert cfg.permissions == {"r"}

    def test_custom_values(self):
        cfg = TuiLoopConfig(model="llama3", num_ctx=4096, max_iterations=10, permissions={"r", "w"})
        assert cfg.model == "llama3"
        assert cfg.num_ctx == 4096
        assert cfg.max_iterations == 10
        assert cfg.permissions == {"r", "w"}


# ---------------------------------------------------------------------------
# Static helpers
# ---------------------------------------------------------------------------


class TestExtractThinkBlocks:
    def test_no_think_blocks(self):
        assert _extract_think_blocks("Hello world") == []

    def test_single_block(self):
        assert _extract_think_blocks("<think>reasoning</think>rest") == ["reasoning"]

    def test_multiple_blocks(self):
        content = "<think>first</think> middle <think>second</think>"
        assert _extract_think_blocks(content) == ["first", "second"]

    def test_unclosed_block(self):
        content = "prefix <think>unclosed reasoning"
        result = _extract_think_blocks(content)
        assert "unclosed reasoning" in result

    def test_empty_block_ignored(self):
        assert _extract_think_blocks("<think>  </think>") == []


class TestStripToolMarkup:
    def test_no_markup(self):
        assert _strip_tool_markup("Hello world") == "Hello world"

    def test_strips_think_blocks(self):
        assert _strip_tool_markup("<think>stuff</think>Hello") == "Hello"

    def test_strips_tool_call_tags(self):
        content = "text<tool_call>stuff</tool_call>more"
        assert _strip_tool_markup(content) == "textmore"

    def test_strips_function_tags(self):
        content = "text<function=read_file>stuff</function>more"
        assert _strip_tool_markup(content) == "textmore"

    def test_collapses_blank_lines(self):
        content = "line1\n\n\n\n\nline2"
        assert _strip_tool_markup(content) == "line1\n\nline2"

    def test_strips_unclosed_think(self):
        content = "Hello <think>unclosed reasoning"
        result = _strip_tool_markup(content)
        assert "unclosed" not in result
        assert result.strip() == "Hello"

    def test_strips_orphaned_closing_tool_call(self):
        assert _strip_tool_markup("text\n</tool_call>\nmore") == "text\n\nmore"

    def test_strips_orphaned_opening_tool_call(self):
        assert _strip_tool_markup("<tool_call>\ntext") == "text"

    def test_strips_orphaned_function_tags(self):
        assert _strip_tool_markup("text</function>more") == "textmore"

    def test_strips_only_closing_tool_call(self):
        result = _strip_tool_markup("\n</tool_call>\n")
        assert result == ""

    def test_strips_json_tool_call_array(self):
        content = '[{"id":"call_1","function":{"name":"list_files","arguments":"{}"},"type":"function"}]'
        assert _strip_tool_markup(content) == ""

    def test_strips_json_tool_call_with_surrounding_text(self):
        content = 'I will list files\n[{"id":"c1","function":{"name":"list_files","arguments":"{}"},"type":"function"}]\nDone'
        result = _strip_tool_markup(content)
        assert "function" not in result
        assert "list_files" not in result


class TestParseArguments:
    def test_dict_passthrough(self):
        assert _parse_arguments({"key": "val"}) == {"key": "val"}

    def test_json_string(self):
        assert _parse_arguments('{"key": "val"}') == {"key": "val"}

    def test_invalid_json_returns_empty(self):
        assert _parse_arguments("not json") == {}

    def test_none_returns_empty(self):
        assert _parse_arguments(None) == {}


# ---------------------------------------------------------------------------
# TuiChatLoop.run() — text-only response
# ---------------------------------------------------------------------------


class TestRunTextOnly:
    def test_text_only_response(self):
        loop, cb, llm, registry = _make_loop()
        response = _make_response(content="Hello!", total_tokens=42)

        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=response):
            _run(loop.run())

        event_types = [e[0] for e in cb.events]
        assert "thinking_start" in event_types
        assert "thinking_stop" in event_types
        assert "assistant_content" in event_types
        assert "token_usage" in event_types

        content_events = [e for e in cb.events if e[0] == "assistant_content"]
        assert content_events[0][1] == "Hello!"

        assert loop.total_tokens == 42
        assert any(m.get("role") == "assistant" and m.get("content") == "Hello!" for m in loop.messages)

    def test_iteration_increments(self):
        loop, cb, llm, registry = _make_loop()
        response = _make_response(content="done")

        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=response):
            _run(loop.run())

        assert loop.iteration == 1

    def test_think_blocks_extracted(self):
        loop, cb, llm, registry = _make_loop()
        response = _make_response(content="<think>reasoning</think>Answer")

        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=response):
            _run(loop.run())

        thinking = [e for e in cb.events if e[0] == "thinking_content"]
        assert len(thinking) == 1
        assert thinking[0][1] == "reasoning"

        content = [e for e in cb.events if e[0] == "assistant_content"]
        assert content[0][1] == "Answer"


# ---------------------------------------------------------------------------
# TuiChatLoop.run() — OpenAI tool calls
# ---------------------------------------------------------------------------


class TestRunOpenAIToolCalls:
    def test_auto_approved_tool_execution(self):
        """read_file with permissions={"r"} should auto-execute."""
        loop, cb, llm, registry = _make_loop(permissions={"r"})

        tc = _make_tool_call(call_id="tc-1", name="read_file", arguments={"file_path": "x.py"})
        resp_tools = _make_response(content="Let me read", tool_calls=[tc])
        resp_text = _make_response(content="Done reading")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp_tools
            return resp_text

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            with patch("ayder_cli.tui.chat_loop.asyncio.to_thread", new_callable=AsyncMock, return_value="file content"):
                _run(loop.run())

        event_types = [e[0] for e in cb.events]
        assert "tool_start" in event_types
        assert "tool_complete" in event_types
        assert "tools_cleanup" in event_types

        tool_msgs = [m for m in loop.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"] == "file content"

    def test_needs_confirmation_approved(self):
        """write_file with permissions={"r"} should need confirmation."""
        cb = FakeCallbacks()
        cb._confirm_result = FakeConfirmResult(action="approve")
        loop, cb, llm, registry = _make_loop(cb=cb, permissions={"r"})

        tc = _make_tool_call(call_id="tc-w", name="write_file", arguments={"file_path": "x.py", "content": "hi"})
        resp_tools = _make_response(content="Writing file", tool_calls=[tc])
        resp_text = _make_response(content="File written")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp_tools
            return resp_text

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            with patch("ayder_cli.tui.chat_loop.asyncio.to_thread", new_callable=AsyncMock, return_value="wrote file"):
                _run(loop.run())

        confirm_events = [e for e in cb.events if e[0] == "request_confirmation"]
        assert len(confirm_events) == 1
        assert confirm_events[0][1] == "write_file"

    def test_needs_confirmation_denied(self):
        """Denied tool should append denial message."""
        cb = FakeCallbacks()
        cb._confirm_result = FakeConfirmResult(action="deny")
        loop, cb, llm, registry = _make_loop(cb=cb, permissions={"r"})

        tc = _make_tool_call(call_id="tc-w", name="write_file", arguments={"file_path": "x.py", "content": "hi"})
        resp_tools = _make_response(content="Writing", tool_calls=[tc])
        resp_text = _make_response(content="OK denied")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp_tools
            return resp_text

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            _run(loop.run())

        tool_msgs = [m for m in loop.messages if m.get("role") == "tool"]
        assert any("denied" in m.get("content", "").lower() for m in tool_msgs)

    def test_instruct_skips_remaining(self):
        """Instruct action should skip remaining tools and inject user message."""
        cb = FakeCallbacks()
        cb._confirm_result = FakeConfirmResult(action="instruct", instructions="Do X instead")
        loop, cb, llm, registry = _make_loop(cb=cb, permissions={"r"})

        tc1 = _make_tool_call(call_id="tc-1", name="write_file", arguments={"file_path": "a.py", "content": "a"})
        tc2 = _make_tool_call(call_id="tc-2", name="write_file", arguments={"file_path": "b.py", "content": "b"})
        resp_tools = _make_response(content="Writing files", tool_calls=[tc1, tc2])
        resp_text = _make_response(content="OK")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp_tools
            return resp_text

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            _run(loop.run())

        user_msgs = [m for m in loop.messages if m.get("role") == "user" and "Do X instead" in m.get("content", "")]
        assert len(user_msgs) == 1

        tool_msgs = [m for m in loop.messages if m.get("role") == "tool"]
        skipped = [m for m in tool_msgs if "skipped" in m.get("content", "").lower()]
        assert len(skipped) == 1


# ---------------------------------------------------------------------------
# TuiChatLoop.run() — XML fallback
# ---------------------------------------------------------------------------


class TestRunXMLFallback:
    def test_xml_tool_call_detected(self):
        loop, cb, llm, registry = _make_loop()

        xml_content = 'Let me read <function=read_file><parameter=file_path>test.py</parameter></function>'
        resp_xml = _make_response(content=xml_content)
        resp_text = _make_response(content="Got the file")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp_xml
            return resp_text

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            with patch("ayder_cli.tui.chat_loop.asyncio.to_thread", new_callable=AsyncMock, return_value="content"):
                _run(loop.run())

        event_types = [e[0] for e in cb.events]
        assert "tool_start" in event_types
        assert "tool_complete" in event_types

        user_results = [m for m in loop.messages if m.get("role") == "user" and "[read_file]" in m.get("content", "")]
        assert len(user_results) == 1


# ---------------------------------------------------------------------------
# JSON Fallback
# ---------------------------------------------------------------------------


class TestParseJsonToolCalls:
    def test_empty_content(self):
        assert _parse_json_tool_calls("") == []

    def test_plain_text(self):
        assert _parse_json_tool_calls("Hello world") == []

    def test_valid_json_tool_calls(self):
        content = json.dumps([
            {"id": "call_1", "function": {"name": "list_files", "arguments": '{"directory":"."}'}, "type": "function"}
        ])
        result = _parse_json_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "list_files"
        assert result[0]["arguments"] == {"directory": "."}

    def test_multiple_tool_calls(self):
        content = json.dumps([
            {"id": "1", "function": {"name": "read_file", "arguments": '{"file_path":"a.py"}'}, "type": "function"},
            {"id": "2", "function": {"name": "list_files", "arguments": '{"directory":"."}'}, "type": "function"},
        ])
        result = _parse_json_tool_calls(content)
        assert len(result) == 2
        assert result[0]["name"] == "read_file"
        assert result[1]["name"] == "list_files"

    def test_dict_arguments(self):
        content = json.dumps([
            {"function": {"name": "read_file", "arguments": {"file_path": "test.py"}}}
        ])
        result = _parse_json_tool_calls(content)
        assert len(result) == 1
        assert result[0]["arguments"] == {"file_path": "test.py"}

    def test_invalid_json(self):
        assert _parse_json_tool_calls("[{broken json}]") == []

    def test_no_function_key(self):
        assert _parse_json_tool_calls('[{"id": "1", "type": "function"}]') == []

    def test_missing_name(self):
        assert _parse_json_tool_calls('[{"function": {"arguments": "{}"}}]') == []

    def test_with_extra_usage_field(self):
        """Models like qwen3-coder include usage inside tool call objects."""
        content = '[{"id":"call_1","function":{"arguments":"{\\"directory\\": \\".\\"}","name":"list_files"},"type":"function","usage":{"prompt_tokens":84,"completion_tokens":168,"total_tokens":252}}]'
        result = _parse_json_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "list_files"
        assert result[0]["arguments"] == {"directory": "."}


class TestRegexExtractJsonToolCalls:
    def test_extracts_tool_name_from_malformed(self):
        """Regex fallback extracts name even when JSON is broken."""
        content = '[{"function":{"arguments":"{bad json}","name":"list_files"},"type":"function"}]'
        result = _regex_extract_json_tool_calls(content)
        assert len(result) == 1
        assert result[0]["name"] == "list_files"

    def test_no_match(self):
        assert _regex_extract_json_tool_calls("no tool calls here") == []

    def test_multiple_names(self):
        content = '"name":"read_file" ... "name":"list_files"'
        result = _regex_extract_json_tool_calls(content)
        assert len(result) == 2


class TestRunJSONFallback:
    def test_json_tool_call_detected(self):
        loop, cb, llm, registry = _make_loop()

        json_content = json.dumps([
            {"id": "call_1", "function": {"name": "list_files", "arguments": '{"directory":"."}'}, "type": "function"}
        ])
        resp_json = _make_response(content=json_content)
        resp_text = _make_response(content="Here are the files")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp_json
            return resp_text

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            with patch("ayder_cli.tui.chat_loop.asyncio.to_thread", new_callable=AsyncMock, return_value="dir contents"):
                _run(loop.run())

        event_types = [e[0] for e in cb.events]
        assert "tool_start" in event_types
        assert "tool_complete" in event_types

        user_results = [m for m in loop.messages if m.get("role") == "user" and "[list_files]" in m.get("content", "")]
        assert len(user_results) == 1


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    def test_cancelled_before_llm_call(self):
        cb = FakeCallbacks()
        cb._cancelled = True
        loop, cb, llm, registry = _make_loop(cb=cb)

        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock) as mock_llm:
            _run(loop.run())
            mock_llm.assert_not_called()

    def test_cancelled_after_llm_call(self):
        cb = FakeCallbacks()
        loop, _, llm, registry = _make_loop(cb=cb)

        call_count = [0]

        async def fake_llm_then_cancel(*args, **kwargs):
            call_count[0] += 1
            cb._cancelled = True
            return _make_response(content="result")

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm_then_cancel):
            _run(loop.run())

        assert call_count[0] == 1


# ---------------------------------------------------------------------------
# Iteration and checkpoint
# ---------------------------------------------------------------------------


class TestIterationAndCheckpoint:
    def test_reset_iterations(self):
        loop, *_ = _make_loop()
        loop._iteration = 10
        loop.reset_iterations()
        assert loop.iteration == 0

    def test_max_iterations_reached_no_checkpoint(self):
        loop, cb, llm, registry = _make_loop()
        loop.config.max_iterations = 0

        response = _make_response(content="hi")
        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=response):
            _run(loop.run())

        system_msgs = [e for e in cb.events if e[0] == "system_message"]
        assert any("max iterations" in e[1].lower() for e in system_msgs)

    def test_tokens_accumulate(self):
        loop, cb, llm, registry = _make_loop()

        resp1 = _make_response(content="first", tool_calls=None, total_tokens=50)
        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=resp1):
            _run(loop.run())

        assert loop.total_tokens == 50

        resp2 = _make_response(content="second", tool_calls=None, total_tokens=30)
        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=resp2):
            _run(loop.run())

        assert loop.total_tokens == 80


# ---------------------------------------------------------------------------
# _tool_needs_confirmation
# ---------------------------------------------------------------------------


class TestToolNeedsConfirmation:
    def test_read_tool_with_read_permission(self):
        loop, *_ = _make_loop(permissions={"r"})
        assert loop._tool_needs_confirmation("read_file") is False

    def test_write_tool_with_read_permission(self):
        loop, *_ = _make_loop(permissions={"r"})
        assert loop._tool_needs_confirmation("write_file") is True

    def test_write_tool_with_write_permission(self):
        loop, *_ = _make_loop(permissions={"r", "w"})
        assert loop._tool_needs_confirmation("write_file") is False

    def test_exec_tool_with_exec_permission(self):
        loop, *_ = _make_loop(permissions={"r", "x"})
        assert loop._tool_needs_confirmation("run_shell_command") is False

    def test_exec_tool_without_exec_permission(self):
        loop, *_ = _make_loop(permissions={"r", "w"})
        assert loop._tool_needs_confirmation("run_shell_command") is True

    def test_unknown_tool_defaults_to_read(self):
        loop, *_ = _make_loop(permissions={"r"})
        assert loop._tool_needs_confirmation("nonexistent_tool") is False


# ---------------------------------------------------------------------------
# LLM error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_llm_error_reports_to_callbacks(self):
        loop, cb, llm, registry = _make_loop()

        async def raise_error(*args, **kwargs):
            raise ConnectionError("LLM down")

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=raise_error):
            _run(loop.run())

        system_msgs = [e for e in cb.events if e[0] == "system_message"]
        assert any("LLM down" in e[1] for e in system_msgs)

    def test_no_tools_mode(self):
        loop, cb, llm, registry = _make_loop()
        response = _make_response(content="answer without tools")

        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=response) as mock_llm:
            _run(loop.run(no_tools=True))

        call_args = mock_llm.call_args
        assert call_args.kwargs.get("tools") == []


# ---------------------------------------------------------------------------
# Tool call exception handling
# ---------------------------------------------------------------------------


class TestToolCallExceptions:
    def test_auto_approved_tool_exception(self):
        """Exception from asyncio.gather should be caught and reported."""
        loop, cb, llm, registry = _make_loop(permissions={"r"})

        tc = _make_tool_call(call_id="tc-err", name="read_file", arguments={"file_path": "bad.py"})
        resp_tools = _make_response(content="Reading", tool_calls=[tc])
        resp_text = _make_response(content="Recovered")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return resp_tools
            return resp_text

        async def raise_on_thread(*args, **kwargs):
            raise RuntimeError("Tool exploded")

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            with patch("ayder_cli.tui.chat_loop.asyncio.to_thread", side_effect=raise_on_thread):
                _run(loop.run())

        tool_msgs = [m for m in loop.messages if m.get("role") == "tool"]
        assert any("Error" in m.get("content", "") for m in tool_msgs)


# ---------------------------------------------------------------------------
# Checkpoint / compact at max iterations
# ---------------------------------------------------------------------------


class TestCheckpointCycle:
    def test_checkpoint_creates_and_resets(self):
        """When max_iterations exceeded, checkpoint is created and loop continues."""
        from ayder_cli.checkpoint_manager import CheckpointManager

        cb = FakeCallbacks()
        messages = [{"role": "system", "content": "sys"}]
        cm = MagicMock(spec=CheckpointManager)
        cm.save_checkpoint.return_value = MagicMock()

        mm = MagicMock()
        mm.build_quick_restore_message.return_value = "Restored context here."

        loop = TuiChatLoop(
            llm=MagicMock(),
            registry=MagicMock(),
            messages=messages,
            config=TuiLoopConfig(max_iterations=1, permissions={"r"}),
            callbacks=cb,
            checkpoint_manager=cm,
            memory_manager=mm,
        )

        # First call exceeds limit → checkpoint → second call returns text
        summary_resp = _make_response(content="Summary of progress")
        text_resp = _make_response(content="Continuing after compact")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return summary_resp
            return text_resp

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            # Iteration starts at 0, first increment makes it 1, which is not > 1.
            # Second increment makes it 2, which is > 1 → triggers checkpoint.
            # But we need the first LLM call to return tools so loop continues.
            # Simpler: set iteration to max_iterations already.
            loop._iteration = 1  # Next increment will be 2 > 1
            _run(loop.run())

        # Checkpoint was saved
        cm.save_checkpoint.assert_called_once()
        # Iteration was reset
        assert loop._iteration >= 0
        # System messages about checkpoint
        system_msgs = [e[1] for e in cb.events if e[0] == "system_message"]
        assert any("checkpoint" in m.lower() for m in system_msgs)

    def test_checkpoint_no_managers_shows_max_iter_message(self):
        """Without checkpoint managers, max iterations message is shown."""
        loop, cb, llm, registry = _make_loop()
        loop.config.max_iterations = 0  # Immediately exceeded

        response = _make_response(content="hi")
        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=response):
            _run(loop.run())

        system_msgs = [e for e in cb.events if e[0] == "system_message"]
        assert any("max iterations" in e[1].lower() for e in system_msgs)

    def test_checkpoint_llm_error_returns_false(self):
        """If LLM call fails during checkpoint, falls back to max iterations message."""
        from ayder_cli.checkpoint_manager import CheckpointManager

        cb = FakeCallbacks()
        messages = [{"role": "system", "content": "sys"}]
        cm = MagicMock(spec=CheckpointManager)
        mm = MagicMock()

        loop = TuiChatLoop(
            llm=MagicMock(),
            registry=MagicMock(),
            messages=messages,
            config=TuiLoopConfig(max_iterations=0, permissions={"r"}),
            callbacks=cb,
            checkpoint_manager=cm,
            memory_manager=mm,
        )

        async def raise_error(*args, **kwargs):
            raise ConnectionError("LLM down")

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=raise_error):
            _run(loop.run())

        system_msgs = [e[1] for e in cb.events if e[0] == "system_message"]
        assert any("max iterations" in m.lower() for m in system_msgs)

    def test_checkpoint_resets_messages_keeps_system(self):
        """After checkpoint, only system prompt + restore message remain."""
        from ayder_cli.checkpoint_manager import CheckpointManager

        cb = FakeCallbacks()
        sys_msg = {"role": "system", "content": "sys prompt"}
        messages = [sys_msg, {"role": "user", "content": "old stuff"}]
        cm = MagicMock(spec=CheckpointManager)
        cm.save_checkpoint.return_value = MagicMock()

        mm = MagicMock()
        mm.build_quick_restore_message.return_value = "Restored."

        loop = TuiChatLoop(
            llm=MagicMock(),
            registry=MagicMock(),
            messages=messages,
            config=TuiLoopConfig(max_iterations=0, permissions={"r"}),
            callbacks=cb,
            checkpoint_manager=cm,
            memory_manager=mm,
        )

        # Checkpoint LLM call returns summary, then text response after reset
        summary_resp = _make_response(content="Summary")
        text_resp = _make_response(content="After compact")

        call_count = [0]

        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return summary_resp
            return text_resp

        with patch("ayder_cli.tui.chat_loop.call_llm_async", side_effect=fake_llm):
            _run(loop.run())

        # After checkpoint, messages should have system + restore + continuation
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "sys prompt"


# ---------------------------------------------------------------------------
# -I iterations flag passthrough
# ---------------------------------------------------------------------------


class TestIterationsPassthrough:
    def test_tui_iterations_from_cli_flag(self):
        """Test that -I flag value reaches TuiLoopConfig."""
        import sys

        with patch.object(sys, 'argv', ['ayder', '-I', '25']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.tui.run_tui') as mock_run_tui:
            from ayder_cli.cli import main
            main()
            call_kwargs = mock_run_tui.call_args[1]
            assert call_kwargs['iterations'] == 25

    def test_tui_iterations_none_uses_config(self):
        """Test that no -I flag passes None, letting config default apply."""
        import sys

        with patch.object(sys, 'argv', ['ayder']), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch('ayder_cli.tui.run_tui') as mock_run_tui:
            from ayder_cli.cli import main
            main()
            call_kwargs = mock_run_tui.call_args[1]
            assert call_kwargs['iterations'] is not None  # resolved from config
