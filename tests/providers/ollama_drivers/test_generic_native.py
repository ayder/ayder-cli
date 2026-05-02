"""GenericNativeDriver smoke tests."""

from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.generic_native import GenericNativeDriver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_generic_native_metadata():
    assert GenericNativeDriver.name == "generic_native"
    assert GenericNativeDriver.mode is DriverMode.NATIVE
    assert GenericNativeDriver.fallback_driver == "generic_xml"
    assert GenericNativeDriver.priority >= 100


def test_generic_native_default_supports_does_not_self_claim():
    driver = GenericNativeDriver()
    assert driver.supports(ModelInfo(family="anything")) is False


def test_generic_native_render_is_passthrough():
    driver = GenericNativeDriver()
    messages = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(messages, [{"type": "function"}]) == messages


def test_generic_native_parse_returns_empty():
    driver = GenericNativeDriver()
    assert driver.parse_tool_calls("any", "any") == []


def test_generic_native_display_filter_is_none():
    driver = GenericNativeDriver()
    assert driver.display_filter() is None
