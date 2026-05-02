"""Tests for DriverRegistry auto-discovery and resolve()."""

from unittest.mock import AsyncMock

import pytest

from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode
from ayder_cli.providers.impl.ollama_drivers.registry import DriverRegistry
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def _stub_inspector(info_or_exc):
    inspector = AsyncMock()
    if isinstance(info_or_exc, Exception):
        inspector.get_model_info.side_effect = info_or_exc
    else:
        inspector.get_model_info.return_value = info_or_exc
    return inspector


@pytest.mark.asyncio
async def test_auto_discovery_constructs_registry():
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)
    assert registry is not None
    assert hasattr(registry, "_drivers")


@pytest.mark.asyncio
async def test_auto_discovery_skips_abstract_bases():
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)
    assert "ChatDriver" not in (d.__class__.__name__ for d in registry._drivers)


@pytest.mark.asyncio
async def test_resolve_uses_user_override_first():
    inspector = _stub_inspector(ModelInfo(family="qwen3"))
    registry = DriverRegistry(inspector)

    class _FakeOverride(ChatDriver):
        name = "fake_override"
        mode = DriverMode.NATIVE

    registry._by_name["fake_override"] = _FakeOverride()
    registry._drivers.append(_FakeOverride())

    driver = await registry.resolve("any-model", override="fake_override")
    assert driver.name == "fake_override"
    inspector.get_model_info.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_caches_on_repeat_call():
    inspector = _stub_inspector(
        ModelInfo(family="llama", name="llama3.1:8b", capabilities=["tools"])
    )
    registry = DriverRegistry(inspector)

    first = await registry.resolve("llama3.1:8b")
    second = await registry.resolve("llama3.1:8b")

    assert first is second
    assert first.name == "generic_native"
    inspector.get_model_info.assert_called_once_with("llama3.1:8b")


@pytest.mark.asyncio
async def test_resolve_falls_back_to_generic_native_when_inspector_fails():
    inspector = _stub_inspector(RuntimeError("boom"))
    registry = DriverRegistry(inspector)

    driver = await registry.resolve("any-model")
    assert driver.name == "generic_native"


@pytest.mark.asyncio
async def test_resolve_uses_driver_self_claim_when_matrix_does_not_match():
    inspector = _stub_inspector(ModelInfo(family="custom-family", name="custom:latest"))
    registry = DriverRegistry(inspector)

    class _CustomDriver(ChatDriver):
        name = "custom_self_claim"
        mode = DriverMode.IN_CONTENT

        @classmethod
        def supports(cls, model_info: ModelInfo) -> bool:
            return model_info.family == "custom-family"

    registry._drivers.insert(0, _CustomDriver())

    driver = await registry.resolve("custom:latest")

    assert driver.name == "custom_self_claim"


@pytest.mark.asyncio
async def test_get_returns_driver_by_name():
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)

    class _FakeDriver(ChatDriver):
        name = "fake_x"
        mode = DriverMode.NATIVE

    registry._by_name["fake_x"] = _FakeDriver()
    assert registry.get("fake_x").name == "fake_x"


@pytest.mark.asyncio
async def test_get_raises_keyerror_on_unknown_name():
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)
    with pytest.raises(KeyError):
        registry.get("not_registered")
