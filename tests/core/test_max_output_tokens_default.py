"""The built-in max_output_tokens default is 32768.

4096 was too small for agent work: reasoning models spend output tokens on
thinking, and one large ``write_file`` call needs 10-15K tokens. A response
that hits the cap cuts the tool-call arguments off, and write tools refuse
repaired arguments. Explicit values in ``[app]``, ``[llm.<name>]`` and
``[agents.<name>]`` still win.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ayder_cli.core import config as config_module
from ayder_cli.core.config import Config, load_config_for_provider
from ayder_cli.loops.chat_loop import ChatLoopConfig
from ayder_cli.providers.impl.claude import ClaudeProvider

DEFAULT = 32768


def _write_config(tmp_path, monkeypatch, body: str) -> None:
    path = tmp_path / ".ayder" / "config.toml"
    path.parent.mkdir()
    path.write_text(body)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)


_PROFILES = """config_version = "2.0"

[app]
provider = "plain"
{app_extra}

[llm.plain]
driver = "openai"
base_url = "http://localhost:1/v1"
api_key = "x"
model = "m"

[llm.capped]
driver = "openai"
base_url = "http://localhost:1/v1"
api_key = "x"
model = "m"
max_output_tokens = 8192
"""


def test_config_default():
    """Baseline regression: the default is 4096 today."""
    assert Config().max_output_tokens == DEFAULT


def test_chat_loop_config_default():
    """Baseline regression: ChatLoopConfig defaults to 4096 today."""
    assert ChatLoopConfig().max_output_tokens == DEFAULT


def test_profile_without_the_key_gets_the_default(tmp_path, monkeypatch):
    """Baseline regression: a profile that sets no cap resolves to 4096 today."""
    _write_config(tmp_path, monkeypatch, _PROFILES.format(app_extra=""))
    assert load_config_for_provider("plain").max_output_tokens == DEFAULT


class _RecordingStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        return
        yield


def test_claude_stream_fallback_uses_the_default():
    """Baseline regression: a config without the attribute sends 4096 today."""
    seen: dict = {}

    def stream(**kwargs):
        seen.update(kwargs)
        return _RecordingStream()

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.config = SimpleNamespace()
    provider.interaction_sink = None
    provider.client = SimpleNamespace(messages=SimpleNamespace(stream=stream))

    async def drain():
        async for _ in provider.stream_with_tools(
            [{"role": "user", "content": "hi"}], "claude-x"
        ):
            pass

    asyncio.run(drain())
    assert seen["max_tokens"] == DEFAULT


def test_explicit_values_still_win(tmp_path, monkeypatch):
    """Preservation: [app] and profile values override the default."""
    _write_config(
        tmp_path, monkeypatch, _PROFILES.format(app_extra="max_output_tokens = 2048")
    )
    assert load_config_for_provider("plain").max_output_tokens == 2048
    assert load_config_for_provider("capped").max_output_tokens == 8192
    assert Config(max_output_tokens=1024).max_output_tokens == 1024


def test_validator_still_rejects_non_positive():
    """Preservation: zero and negative caps are still refused."""
    for bad in (0, -1):
        with pytest.raises(ValueError):
            Config(max_output_tokens=bad)
