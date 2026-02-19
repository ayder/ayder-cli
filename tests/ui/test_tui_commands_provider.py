"""Tests for /provider TUI command."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ayder_cli.core.config import Config
from ayder_cli.tui.commands import COMMAND_MAP, _apply_provider_switch, handle_provider
from ayder_cli.tui.screens import CLISelectScreen


def _make_app() -> SimpleNamespace:
    status_bar = MagicMock()
    app = SimpleNamespace(
        config=Config(provider="openai"),
        llm=MagicMock(),
        model="qwen3-coder:latest",
        push_screen=MagicMock(),
        query_one=MagicMock(return_value=status_bar),
        update_system_prompt_model=MagicMock(),
        chat_loop=SimpleNamespace(
            llm=MagicMock(),
            config=SimpleNamespace(model="qwen3-coder:latest", num_ctx=65536),
        ),
    )
    return app


def test_provider_command_registered():
    assert "/provider" in COMMAND_MAP


def test_handle_provider_accepts_dynamic_profile_name():
    app = _make_app()
    chat_view = MagicMock()

    with (
        patch(
            "ayder_cli.tui.commands.list_provider_profiles",
            return_value=["openai", "deepseek"],
        ),
        patch("ayder_cli.tui.commands._apply_provider_switch") as mock_apply,
    ):
        handle_provider(app, "deepseek", chat_view)

    mock_apply.assert_called_once_with(app, "deepseek", chat_view)


def test_handle_provider_rejects_unknown_profile():
    app = _make_app()
    chat_view = MagicMock()

    with patch(
        "ayder_cli.tui.commands.list_provider_profiles",
        return_value=["openai", "deepseek"],
    ):
        handle_provider(app, "unknown", chat_view)

    chat_view.add_system_message.assert_called_once()
    message = chat_view.add_system_message.call_args[0][0]
    assert "Unknown provider: unknown" in message
    assert "openai" in message
    assert "deepseek" in message


def test_handle_provider_opens_selector_with_dynamic_profiles():
    app = _make_app()
    chat_view = MagicMock()

    with (
        patch(
            "ayder_cli.tui.commands.list_provider_profiles",
            return_value=["openai", "deepseek"],
        ),
        patch("ayder_cli.tui.commands._apply_provider_switch") as mock_apply,
    ):
        handle_provider(app, "", chat_view)
        app.push_screen.assert_called_once()
        screen, callback = app.push_screen.call_args[0]
        assert isinstance(screen, CLISelectScreen)
        callback("deepseek")

    mock_apply.assert_called_once_with(app, "deepseek", chat_view)


def test_apply_provider_switch_updates_runtime_for_dynamic_profile():
    app = _make_app()
    chat_view = MagicMock()
    status_bar = app.query_one.return_value

    new_config = Config(
        provider="deepseek",
        driver="openai",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-deepseek",
        model="deepseek-chat",
        num_ctx=32768,
    )
    new_llm = MagicMock()

    with (
        patch(
            "ayder_cli.core.config.load_config_for_provider",
            return_value=new_config,
        ),
        patch(
            "ayder_cli.services.llm.create_llm_provider",
            return_value=new_llm,
        ),
    ):
        _apply_provider_switch(app, "deepseek", chat_view)

    assert app.config is new_config
    assert app.llm is new_llm
    assert app.chat_loop.llm is new_llm
    assert app.model == "deepseek-chat"
    assert app.chat_loop.config.model == "deepseek-chat"
    assert app.chat_loop.config.num_ctx == 32768
    app.update_system_prompt_model.assert_called_once()
    status_bar.set_model.assert_called_once_with("deepseek-chat")
    chat_view.add_system_message.assert_called_once_with(
        "Switched to provider: deepseek (model: deepseek-chat)"
    )


def test_apply_provider_switch_rolls_back_on_invalid_driver():
    app = _make_app()
    old_config = app.config
    chat_view = MagicMock()

    with (
        patch(
            "ayder_cli.core.config.load_config_for_provider",
            return_value=SimpleNamespace(model="x", num_ctx=1),
        ),
        patch(
            "ayder_cli.services.llm.create_llm_provider",
            side_effect=ValueError("Unsupported LLM driver 'bad'"),
        ),
    ):
        _apply_provider_switch(app, "broken", chat_view)

    assert app.config is old_config
    chat_view.add_system_message.assert_called_once()
    assert "Cannot switch to broken" in chat_view.add_system_message.call_args[0][0]
