"""Tests for the ChatDriver ABC contract."""

from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


class _StubDriver(ChatDriver):
    name = "stub"
    mode = DriverMode.NATIVE
    supports_families = ("stub_family",)


def test_drivermode_has_two_values():
    assert {m.value for m in DriverMode} == {"native", "in_content"}


def test_default_supports_matches_family_substring():
    info = ModelInfo(family="STUB_FAMILY", capabilities=["tools"])
    assert _StubDriver.supports(info) is True


def test_default_supports_rejects_when_family_does_not_match():
    info = ModelInfo(family="other", capabilities=["tools"])
    assert _StubDriver.supports(info) is False


def test_default_supports_rejects_when_family_is_empty():
    info = ModelInfo(family="", capabilities=[])
    assert _StubDriver.supports(info) is False


def test_default_render_returns_messages_unchanged():
    driver = _StubDriver()
    messages = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(messages, []) == messages


def test_default_parse_returns_empty_list():
    driver = _StubDriver()
    assert driver.parse_tool_calls("any content", "any reasoning") == []


def test_default_display_filter_returns_none():
    driver = _StubDriver()
    assert driver.display_filter() is None


def test_class_metadata_required():
    """Subclasses must set name and mode. The ABC has no defaults."""
    assert _StubDriver.name == "stub"
    assert _StubDriver.mode is DriverMode.NATIVE
    assert _StubDriver.priority == 100
    assert _StubDriver.abstract is False
    assert _StubDriver.fallback_driver is None
