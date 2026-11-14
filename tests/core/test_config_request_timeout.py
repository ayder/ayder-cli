"""The ``request_timeout_seconds`` setting.

Kind: new interface. How long the LLM stream may stay silent (before its first chunk or
between chunks) before the attempt fails and is retried. It is the user's choice, not
ayder's: the default is 0, which means no timeout. Kept out of
tests/core/test_config.py, which poe test ignores.

No network (environment: local-faked).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from ayder_cli.application.runtime_factory import _maybe_wrap_with_retry
from ayder_cli.core import config as config_module
from ayder_cli.core.config import Config, RetryConfigSection, load_config_for_provider
from ayder_cli.providers.base import NormalizedStreamChunk
from ayder_cli.providers.retry import ProviderStallTimeout, RetryingProvider


def _write_config(tmp_path, monkeypatch, body: str) -> None:
    path = tmp_path / ".ayder" / "config.toml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(body)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)


_TOML = """config_version = "2.0"

[app]
provider = "plain"
{app_extra}

[llm.plain]
driver = "openai"
base_url = "http://localhost:1/v1"
api_key = "x"
model = "m"
{plain_extra}

[llm.other]
driver = "openai"
base_url = "http://localhost:1/v1"
api_key = "x"
model = "m"
request_timeout_seconds = 7
"""


def test_default_is_zero_which_means_no_timeout():
    assert Config().request_timeout_seconds == 0


def test_a_profile_value_is_read_for_that_profile(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, _TOML.format(
        app_extra="", plain_extra="request_timeout_seconds = 5"))

    assert load_config_for_provider("plain").request_timeout_seconds == 5
    assert load_config_for_provider("other").request_timeout_seconds == 7


def test_the_app_section_is_a_default_and_the_profile_wins(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, _TOML.format(
        app_extra="request_timeout_seconds = 30", plain_extra=""))
    assert load_config_for_provider("plain").request_timeout_seconds == 30

    _write_config(tmp_path, monkeypatch, _TOML.format(
        app_extra="request_timeout_seconds = 30", plain_extra="request_timeout_seconds = 5"))
    assert load_config_for_provider("plain").request_timeout_seconds == 5


def test_an_unset_profile_stays_at_the_default(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, _TOML.format(app_extra="", plain_extra=""))

    assert load_config_for_provider("plain").request_timeout_seconds == 0


@pytest.mark.parametrize("value", [0, 0.0, 2.5, 300])
def test_zero_and_positive_values_are_accepted(value):
    assert Config(request_timeout_seconds=value).request_timeout_seconds == value


def test_a_negative_value_is_rejected():
    with pytest.raises(ValueError, match="request_timeout_seconds must be >= 0"):
        Config(request_timeout_seconds=-1)


# --- the default pins "no watchdog" end to end --------------------------------------


def test_the_default_config_runs_no_stall_watchdog():
    """The cap is the user's choice: with nothing set, a silent stream is never cut.

    Retry off and no timeout: the provider is not wrapped at all. Retry on (its
    default) and no timeout: the wrapper carries 0, and a stream that goes silent is
    still waiting after 0.2 s instead of failing with ProviderStallTimeout.
    """
    provider = MagicMock()
    off = Config(retry=RetryConfigSection(enabled=False))
    assert _maybe_wrap_with_retry(provider, off, None) is provider

    wrapped = _maybe_wrap_with_retry(provider, Config(), None)
    assert isinstance(wrapped, RetryingProvider)
    assert wrapped._request_timeout == 0

    class _Silent:
        async def stream_with_tools(self, *args, **kwargs):
            await asyncio.Event().wait()
            yield NormalizedStreamChunk()

    silent = _maybe_wrap_with_retry(_Silent(), Config(), None)

    async def drain() -> None:
        async for _ in silent.stream_with_tools([], "m"):
            pass

    async def go() -> None:
        await asyncio.wait_for(drain(), timeout=0.2)

    with pytest.raises(TimeoutError) as caught:
        asyncio.run(go())
    assert not isinstance(caught.value, ProviderStallTimeout)
