"""Tests for lazy Temporal client adapter."""

import pytest

from ayder_cli.core.config import Config, TemporalConfig
from ayder_cli.services.temporal_client import (
    TemporalClientAdapter,
    TemporalClientUnavailableError,
)


def test_get_client_raises_when_temporal_disabled():
    cfg = Config(temporal=TemporalConfig(enabled=False))
    adapter = TemporalClientAdapter(config=cfg)

    with pytest.raises(TemporalClientUnavailableError) as exc_info:
        adapter.get_client()

    assert "disabled" in str(exc_info.value).lower()


def test_disabled_mode_does_not_import_temporalio(monkeypatch):
    cfg = Config(temporal=TemporalConfig(enabled=False))
    adapter = TemporalClientAdapter(config=cfg)
    called = {"import_attempted": False}

    def _should_not_import():
        called["import_attempted"] = True
        raise AssertionError("temporal import should not be attempted when disabled")

    monkeypatch.setattr(
        "ayder_cli.services.temporal_client._import_temporal_client_class",
        _should_not_import,
    )

    with pytest.raises(TemporalClientUnavailableError):
        adapter.get_client()

    assert called["import_attempted"] is False


def test_get_client_raises_when_temporalio_missing(monkeypatch):
    cfg = Config(temporal=TemporalConfig(enabled=True))
    adapter = TemporalClientAdapter(config=cfg)

    def _raise_import_error():
        raise ImportError("missing temporalio")

    monkeypatch.setattr(
        "ayder_cli.services.temporal_client._import_temporal_client_class",
        _raise_import_error,
    )

    with pytest.raises(TemporalClientUnavailableError) as exc_info:
        adapter.get_client()

    assert "temporalio" in str(exc_info.value).lower()
    assert "install optional dependency" in str(exc_info.value).lower()


def test_client_initialized_lazily_once_and_cached(monkeypatch):
    cfg = Config(
        temporal=TemporalConfig(
            enabled=True,
            host="localhost:7233",
            namespace="default",
        )
    )

    class FakeClientClass:
        pass

    calls = {"count": 0}
    fake_client = object()

    def _fake_connector(client_cls, host, namespace):
        calls["count"] += 1
        assert client_cls is FakeClientClass
        assert host == "localhost:7233"
        assert namespace == "default"
        return fake_client

    monkeypatch.setattr(
        "ayder_cli.services.temporal_client._import_temporal_client_class",
        lambda: FakeClientClass,
    )

    adapter = TemporalClientAdapter(config=cfg, connector=_fake_connector)

    c1 = adapter.get_client()
    c2 = adapter.get_client()

    assert c1 is fake_client
    assert c2 is fake_client
    assert calls["count"] == 1


def test_clear_cache_forces_reconnect(monkeypatch):
    cfg = Config(temporal=TemporalConfig(enabled=True))

    class FakeClientClass:
        pass

    calls = {"count": 0}

    def _fake_connector(client_cls, host, namespace):
        calls["count"] += 1
        return {"idx": calls["count"], "host": host, "ns": namespace}

    monkeypatch.setattr(
        "ayder_cli.services.temporal_client._import_temporal_client_class",
        lambda: FakeClientClass,
    )

    adapter = TemporalClientAdapter(config=cfg, connector=_fake_connector)

    first = adapter.get_client()
    adapter.clear_cache()
    second = adapter.get_client()

    assert first != second
    assert calls["count"] == 2
