"""Tests for application.message_contract helpers."""

import pytest

from ayder_cli.application.message_contract import (
    get_message_role,
    get_message_content,
    get_message_tool_calls,
    to_message_dict,
)


# -- dict messages -----------------------------------------------------------


def test_get_role_from_dict():
    assert get_message_role({"role": "user", "content": "hi"}) == "user"


def test_get_role_missing_from_dict():
    assert get_message_role({"content": "hi"}) == "unknown"


def test_get_content_from_dict():
    assert get_message_content({"role": "user", "content": "hello"}) == "hello"


def test_get_content_none_from_dict():
    assert get_message_content({"role": "assistant", "content": None}) == ""


def test_get_content_missing_from_dict():
    assert get_message_content({"role": "user"}) == ""


def test_get_tool_calls_from_dict():
    tc = [{"id": "1", "type": "function"}]
    assert get_message_tool_calls({"role": "assistant", "tool_calls": tc}) == tc


def test_get_tool_calls_missing_from_dict():
    assert get_message_tool_calls({"role": "assistant"}) == []


def test_to_message_dict_from_dict():
    msg = {"role": "user", "content": "hello"}
    result = to_message_dict(msg)
    assert result == {"role": "user", "content": "hello"}


def test_to_message_dict_preserves_tool_calls():
    tc = [{"id": "x"}]
    msg = {"role": "assistant", "content": "", "tool_calls": tc}
    result = to_message_dict(msg)
    assert result["tool_calls"] == tc


# -- object messages ---------------------------------------------------------


class FakeMessage:
    def __init__(self, role=None, content=None, tool_calls=None,
                 tool_call_id=None, name=None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id
        self.name = name


def test_get_role_from_object():
    msg = FakeMessage(role="assistant", content="hi")
    assert get_message_role(msg) == "assistant"


def test_get_role_none_from_object():
    msg = FakeMessage(role=None)
    assert get_message_role(msg) == "unknown"


def test_get_content_from_object():
    msg = FakeMessage(role="user", content="world")
    assert get_message_content(msg) == "world"


def test_get_content_none_from_object():
    msg = FakeMessage(role="assistant", content=None)
    assert get_message_content(msg) == ""


def test_get_tool_calls_from_object():
    tc = [{"id": "1"}]
    msg = FakeMessage(role="assistant", tool_calls=tc)
    assert get_message_tool_calls(msg) == tc


def test_get_tool_calls_none_from_object():
    msg = FakeMessage(role="assistant", tool_calls=None)
    assert get_message_tool_calls(msg) == []


def test_to_message_dict_from_object():
    msg = FakeMessage(role="tool", content="result", tool_call_id="abc")
    result = to_message_dict(msg)
    assert result["role"] == "tool"
    assert result["content"] == "result"
    assert result["tool_call_id"] == "abc"


def test_to_message_dict_skips_none_fields():
    msg = FakeMessage(role="user", content="hi", name=None, tool_call_id=None)
    result = to_message_dict(msg)
    assert "name" not in result
    assert "tool_call_id" not in result


def test_to_message_dict_preserves_name():
    msg = FakeMessage(role="tool", content="ok", name="write_file")
    result = to_message_dict(msg)
    assert result["name"] == "write_file"
