"""Runtime effort changes are discoverable, deferred, and provider-aware."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ayder_cli.core.config import Config
from ayder_cli.providers.impl.openai import OpenAIProvider
from ayder_cli.providers.impl.ollama import OllamaProvider
from ayder_cli.providers.retry import RetryingProvider, RetryConfig
from ayder_cli.tui.commands import COMMAND_MAP, handle_effort, handle_help


def app_for(driver="openai", wrapped=True):
    cfg = Config(driver=driver, reasoning_effort="medium")
    cls = OllamaProvider if driver == "ollama" else OpenAIProvider
    inner = cls.__new__(cls)
    inner.config = cfg
    provider = RetryingProvider(inner, RetryConfig()) if wrapped else inner
    return SimpleNamespace(
        config=cfg,
        llm=provider,
        chat_loop=SimpleNamespace(llm=provider),
        request_turn=MagicMock(),
        push_screen=MagicMock(),
        query_one=MagicMock(),
        _agent_registry=MagicMock(),
    ), inner


def apply_queued(app):
    app.request_turn.call_args.kwargs["prepare"]()


def test_effort_command_discoverable_in_help():
    assert COMMAND_MAP["/effort"] is handle_effort
    view = MagicMock()
    handle_help(None, "", view)
    assert "/effort" in view.add_assistant_message.call_args.args[0]


@pytest.mark.parametrize(
    "driver,value,expected,think",
    [
        ("openai", "high", "high", True),
        ("openai", "none", "none", True),
        ("openai", "default", None, True),
        ("openai", "max", "max", True),
        ("ollama", "high", "high", True),
        ("ollama", "off", None, False),
        ("ollama", "false", None, False),
        ("ollama", "none", None, False),
        ("ollama", "on", None, True),
        ("ollama", "true", None, True),
        ("ollama", "default", None, None),
    ],
)
@pytest.mark.parametrize("wrapped", [True, False])
def test_effort_updates_current_provider_between_turns(
    driver, value, expected, think, wrapped
):
    app, inner = app_for(driver, wrapped)
    old_config = app.config
    original_provider = app.llm
    view = MagicMock()
    handle_effort(app, value, view)
    assert app.config is old_config
    assert inner.config is old_config
    assert app.request_turn.call_args.kwargs["run_loop"] is False
    apply_queued(app)
    assert app.config.reasoning_effort == expected
    assert app.config.think == think
    assert inner.config is app.config
    assert app.llm is original_provider
    assert app.chat_loop.llm is original_provider
    assert old_config.reasoning_effort == "medium"
    app._agent_registry.set_parent_config.assert_called_once_with(app.config)


@pytest.mark.parametrize(
    "driver,value",
    [("openai", "bogus"), ("openai", "true"), ("ollama", "xhigh"), ("ollama", "max")],
)
def test_invalid_value_preserves_current_effort(driver, value):
    app, inner = app_for(driver)
    old_config = app.config
    view = MagicMock()
    handle_effort(app, value, view)
    apply_queued(app)
    assert app.config is old_config
    assert inner.config is old_config
    assert "Unsupported effort" in view.add_system_message.call_args.args[0]


def test_picker_uses_driver_values_and_cancel_does_nothing():
    app, inner = app_for("ollama")
    handle_effort(app, "", MagicMock())
    screen, callback = app.push_screen.call_args.args
    assert screen.current_value == "medium"
    assert "xhigh" not in {value for value, _ in screen.items}
    callback(None)
    app.request_turn.assert_not_called()
    callback("low")
    apply_queued(app)
    assert inner.config.reasoning_effort == "low"


def test_queued_effort_rechecks_active_driver():
    app, inner = app_for("openai")
    view = MagicMock()
    handle_effort(app, "xhigh", view)
    app.config = Config(driver="ollama")
    apply_queued(app)
    assert app.config.reasoning_effort is None
    assert "Unsupported effort for ollama" in view.add_system_message.call_args.args[0]


def test_unsupported_driver_reports_without_mutation():
    app, _ = app_for()
    app.config = Config(driver="anthropic")
    view = MagicMock()
    handle_effort(app, "high", view)
    app.request_turn.assert_not_called()
    assert "supported" in view.add_system_message.call_args.args[0]


@pytest.mark.parametrize(
    "think,expected", [(True, "on"), (False, "off"), ("low", "low"), (None, "default")]
)
def test_picker_reports_effective_legacy_think(think, expected):
    app, inner = app_for("ollama")
    app.config = Config(driver="ollama", think=think)
    handle_effort(app, "", MagicMock())
    screen, _ = app.push_screen.call_args.args
    assert screen.current_value == expected
