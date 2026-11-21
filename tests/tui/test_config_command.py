"""/config opens the config wizard; its switches go through _apply_provider_switch."""

from types import SimpleNamespace

import pytest

from ayder_cli.core import config as config_module
from ayder_cli.core.config import DEFAULTS
from ayder_cli.core.config_migration import ensure_latest_config
from ayder_cli.tui import commands
from ayder_cli.tui.config_wizard import ConfigWizardScreen


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / ".ayder" / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", path.parent)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    ensure_latest_config(path, defaults=DEFAULTS)
    return path


def test_config_is_a_slash_command():
    assert commands.COMMAND_MAP["/config"] is commands.handle_config


def test_help_lists_config():
    shown = []
    chat_view = SimpleNamespace(add_assistant_message=shown.append)

    commands.handle_help(SimpleNamespace(), "", chat_view)

    assert "`/config` — Add, edit or delete provider profiles" in shown[0]


def test_autocomplete_offers_config(config_path):
    from ayder_cli.tui.app import AyderApp

    app = AyderApp(model="test")

    assert "/config" in app.commands


def test_handle_config_pushes_the_wizard_wired_to_the_app(monkeypatch):
    pushed = []
    switched = []
    app = SimpleNamespace(
        config=SimpleNamespace(provider="openai"),
        push_screen=lambda screen, *a: pushed.append(screen),
    )
    chat_view = object()
    monkeypatch.setattr(
        commands, "_apply_provider_switch", lambda a, name, cv: switched.append((a, name, cv))
    )

    commands.handle_config(app, "", chat_view)

    [screen] = pushed
    assert isinstance(screen, ConfigWizardScreen)
    assert screen._first_run is False
    assert screen._session_provider() == "openai"
    app.config = SimpleNamespace(provider="anthropic")  # a /provider switch
    assert screen._session_provider() == "anthropic"
    screen._on_switch("evren")
    assert switched == [(app, "evren", chat_view)]


def test_open_config_wizard_first_run():
    pushed = []
    app = SimpleNamespace(
        config=SimpleNamespace(provider="openai"),
        push_screen=lambda screen, *a: pushed.append(screen),
    )

    commands.open_config_wizard(app, object(), first_run=True)

    assert pushed[0]._first_run is True
