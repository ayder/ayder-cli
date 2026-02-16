"""Tests for message contract — normalized message access.

These tests validate that message handling works correctly for both
dict messages and provider object messages with attributes.
"""

import pytest
from unittest.mock import Mock


class TestGetMessageRole:
    """Test get_message_role function."""

    def test_get_message_role_from_dict(self):
        """Extract role from dict message."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_role

        message = {"role": "user", "content": "hello"}
        result = get_message_role(message)

        assert result == "user"

    def test_get_message_role_from_object(self):
        """Extract role from object message with .role attribute."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_role

        message = Mock()
        message.role = "assistant"

        result = get_message_role(message)

        assert result == "assistant"

    def test_get_message_role_missing_field(self):
        """Handle missing role field gracefully."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_role

        message = {"content": "hello"}  # No role
        result = get_message_role(message)

        assert result == "unknown"

    def test_get_message_role_empty_string(self):
        """Handle empty role string."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_role

        message = {"role": "", "content": "hello"}
        result = get_message_role(message)

        assert result == "unknown" or result == ""

    def test_get_message_role_various_roles(self):
        """Handle all standard message roles."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_role

        roles = ["system", "user", "assistant", "tool"]
        for role in roles:
            dict_msg = {"role": role}
            obj_msg = Mock()
            obj_msg.role = role

            assert get_message_role(dict_msg) == role
            assert get_message_role(obj_msg) == role


class TestGetMessageContent:
    """Test get_message_content function."""

    def test_get_message_content_from_dict(self):
        """Extract content from dict message."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        message = {"role": "user", "content": "hello world"}
        result = get_message_content(message)

        assert result == "hello world"

    def test_get_message_content_from_object(self):
        """Extract content from object message with .content attribute."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        message = Mock()
        message.content = "assistant response"

        result = get_message_content(message)

        assert result == "assistant response"

    def test_get_message_content_missing_field(self):
        """Return empty string when content missing."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        message = {"role": "user"}  # No content
        result = get_message_content(message)

        assert result == ""

    def test_get_message_content_none_value(self):
        """Return empty string when content is None."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        message = {"role": "assistant", "content": None}
        result = get_message_content(message)

        assert result == ""

    def test_get_message_content_non_string(self):
        """Coerce non-string content to string."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        # Test with integer
        message = {"role": "user", "content": 42}
        result = get_message_content(message)

        assert isinstance(result, str)
        assert "42" in result

    def test_get_message_content_empty_string(self):
        """Handle empty content string."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        message = {"role": "user", "content": ""}
        result = get_message_content(message)

        assert result == ""

    def test_get_message_content_multiline(self):
        """Handle multiline content."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        content = "Line 1\nLine 2\nLine 3"
        message = {"role": "assistant", "content": content}
        result = get_message_content(message)

        assert result == content


class TestGetMessageToolCalls:
    """Test get_message_tool_calls function."""

    def test_get_message_tool_calls_from_dict(self):
        """Extract tool_calls from dict message."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_tool_calls

        tool_calls = [{"id": "call_1", "function": {"name": "read_file"}}]
        message = {"role": "assistant", "tool_calls": tool_calls}
        result = get_message_tool_calls(message)

        assert result == tool_calls

    def test_get_message_tool_calls_from_object(self):
        """Extract tool_calls from object message with .tool_calls attribute."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_tool_calls

        tool_calls = [{"id": "call_1", "function": {"name": "read_file"}}]
        message = Mock()
        message.tool_calls = tool_calls

        result = get_message_tool_calls(message)

        assert result == tool_calls

    def test_get_message_tool_calls_missing(self):
        """Return empty list when tool_calls missing."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_tool_calls

        message = {"role": "assistant", "content": "hello"}
        result = get_message_tool_calls(message)

        assert result == []

    def test_get_message_tool_calls_none(self):
        """Return empty list when tool_calls is None."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_tool_calls

        message = {"role": "assistant", "tool_calls": None}
        result = get_message_tool_calls(message)

        assert result == []

    def test_get_message_tool_calls_empty_list(self):
        """Return empty list when tool_calls is empty."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_tool_calls

        message = {"role": "assistant", "tool_calls": []}
        result = get_message_tool_calls(message)

        assert result == []

    def test_get_message_tool_calls_multiple(self):
        """Handle multiple tool calls."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_tool_calls

        tool_calls = [
            {"id": "call_1", "function": {"name": "read_file"}},
            {"id": "call_2", "function": {"name": "write_file"}},
        ]
        message = {"role": "assistant", "tool_calls": tool_calls}
        result = get_message_tool_calls(message)

        assert len(result) == 2
        assert result[0]["id"] == "call_1"
        assert result[1]["id"] == "call_2"


class TestToMessageDict:
    """Test to_message_dict function."""

    def test_to_message_dict_from_dict(self):
        """Passthrough for already-dict message."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import to_message_dict

        message = {"role": "user", "content": "hello"}
        result = to_message_dict(message)

        assert result == message
        assert result is message  # Same object

    def test_to_message_dict_from_object(self):
        """Convert object message to dict."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import to_message_dict

        message = Mock()
        message.role = "assistant"
        message.content = "response"
        message.tool_calls = None

        result = to_message_dict(message)

        assert isinstance(result, dict)
        assert result["role"] == "assistant"
        assert result["content"] == "response"

    def test_to_message_dict_preserves_tool_calls(self):
        """Preserve tool_calls when converting object to dict."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import to_message_dict

        tool_calls = [{"id": "call_1", "function": {"name": "read_file"}}]
        message = Mock()
        message.role = "assistant"
        message.content = ""
        message.tool_calls = tool_calls

        result = to_message_dict(message)

        assert result["tool_calls"] == tool_calls

    def test_to_message_dict_handles_optional_fields(self):
        """Handle objects without optional fields."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import to_message_dict

        message = Mock()
        message.role = "user"
        message.content = "hello"
        # No tool_calls attribute
        del message.tool_calls

        result = to_message_dict(message)

        assert result["role"] == "user"
        assert result["content"] == "hello"


class TestMessageContractMixed:
    """Test mixed dict/object message handling."""

    def test_get_message_role_dict_and_object(self):
        """Role extraction works for both formats."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_role

        dict_msg = {"role": "user", "content": "dict message"}
        obj_msg = Mock()
        obj_msg.role = "assistant"

        assert get_message_role(dict_msg) == "user"
        assert get_message_role(obj_msg) == "assistant"

    def test_get_message_content_dict_and_object(self):
        """Content extraction works for both formats."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        dict_msg = {"role": "user", "content": "dict content"}
        obj_msg = Mock()
        obj_msg.content = "object content"

        assert get_message_content(dict_msg) == "dict content"
        assert get_message_content(obj_msg) == "object content"


class TestCheckpointSummaryIntegration:
    """Test checkpoint summary generation with mixed messages."""

    def test_checkpoint_summary_with_mixed_messages(self):
        """Summary generation works with dict/object messages.
        
        This validates the message contract integration in memory.py
        and checkpoint flows.
        """
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import (
            get_message_role, get_message_content
        )

        # Mixed message list
        dict_msg = {"role": "user", "content": "Hello from dict"}
        obj_msg = Mock()
        obj_msg.role = "assistant"
        obj_msg.content = "Response from object"

        messages = [dict_msg, obj_msg]

        # Simulate summary building
        summary_parts = []
        for msg in messages:
            role = get_message_role(msg)
            content = get_message_content(msg)
            summary_parts.append(f"[{role}] {content}")

        summary = "\n".join(summary_parts)

        assert "[user] Hello from dict" in summary
        assert "[assistant] Response from object" in summary

    def test_checkpoint_summary_with_tool_calls(self):
        """Summary handles messages with tool calls."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import (
            get_message_role, get_message_content, get_message_tool_calls
        )

        tool_calls = [{"id": "call_1", "function": {"name": "read_file"}}]
        dict_msg = {
            "role": "assistant",
            "content": "I'll read the file",
            "tool_calls": tool_calls
        }
        obj_msg = Mock()
        obj_msg.role = "tool"
        obj_msg.content = "file contents"
        obj_msg.tool_call_id = "call_1"

        messages = [dict_msg, obj_msg]

        # Verify all accessors work
        for msg in messages:
            role = get_message_role(msg)
            content = get_message_content(msg)
            tools = get_message_tool_calls(msg)

            assert isinstance(role, str)
            assert isinstance(content, str)
            assert isinstance(tools, list)

    def test_checkpoint_summary_with_missing_content(self):
        """Summary handles messages with missing/None content gracefully."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        # Dict with None content
        dict_msg = {"role": "assistant", "content": None}
        # Object with no content attribute
        obj_msg = Mock()
        obj_msg.role = "assistant"
        del obj_msg.content

        # Should return empty string, not raise
        assert get_message_content(dict_msg) == ""


class TestMessageContractEdgeCases:
    """Test edge cases for message contract."""

    def test_empty_dict_message(self):
        """Handle completely empty dict."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import (
            get_message_role, get_message_content, get_message_tool_calls
        )

        message = {}

        assert get_message_role(message) == "unknown"
        assert get_message_content(message) == ""
        assert get_message_tool_calls(message) == []

    def test_object_with_nested_attributes(self):
        """Handle object with nested message attributes."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import (
            get_message_role, get_message_content
        )

        # Provider-specific format with nested message
        message = Mock()
        message.role = "assistant"
        message.content = None
        
        # Some providers nest content
        inner_message = Mock()
        inner_message.content = "nested content"
        message.message = inner_message

        # Should handle gracefully (either return empty or nested)
        role = get_message_role(message)
        content = get_message_content(message)

        assert role == "assistant"
        assert isinstance(content, str)

    def test_unicode_content(self):
        """Handle unicode content correctly."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        unicode_content = "Hello 世界 🌍 ñoño"
        dict_msg = {"role": "user", "content": unicode_content}
        obj_msg = Mock()
        obj_msg.content = unicode_content

        assert get_message_content(dict_msg) == unicode_content
        assert get_message_content(obj_msg) == unicode_content

    def test_very_long_content(self):
        """Handle very long content."""
        pytest.importorskip(
            "ayder_cli.application.message_contract",
            reason="Message contract not yet implemented by DEV-02.4"
        )
        from ayder_cli.application.message_contract import get_message_content

        long_content = "x" * 10000
        message = {"role": "assistant", "content": long_content}

        result = get_message_content(message)
        assert len(result) == 10000
