"""First run: no config.toml at startup opens the config wizard in the TUI."""

import sys
from unittest.mock import patch

import pytest

import ayder_cli.tui as tui
from ayder_cli import cli
from ayder_cli.core import config as config_module
from ayder_cli.core.config import DEFAULTS
from ayder_cli.core.config_migration import ensure_latest_config
from ayder_cli.tui.config_wizard import ConfigWizardScreen


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / ".ayder" / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", path.parent)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    return path


@pytest.fixture
def quiet_startup(monkeypatch, tmp_path):
    """main() without touching the real logging setup, hooks or the repo's log dir."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "setup_logging", lambda settings: None)
    monkeypatch.setattr(cli, "install_exception_hooks", lambda: None)
    monkeypatch.setattr(cli, "set_log_dir", lambda path: None)


def run_main(argv):
    with patch.object(sys, "argv", argv), \
         patch.object(sys.stdin, "isatty", return_value=True), \
         patch("ayder_cli.tui.run_tui") as run_tui:
        cli.main()
    return run_tui


def test_main_flags_first_run_when_no_config(config_path, quiet_startup):
    run_tui = run_main(["ayder"])

    assert run_tui.call_args.kwargs["first_run"] is True
    assert config_path.exists()  # the template is still written


def test_main_no_first_run_when_config_exists(config_path, quiet_startup):
    ensure_latest_config(config_path, defaults=DEFAULTS)

    run_tui = run_main(["ayder"])

    assert run_tui.call_args.kwargs["first_run"] is False


def test_main_no_first_run_with_dash_c(config_path, quiet_startup, tmp_path):
    other = tmp_path / "other.toml"
    ensure_latest_config(other, defaults=DEFAULTS)

    run_tui = run_main(["ayder", "-c", str(other)])

    assert run_tui.call_args.kwargs["first_run"] is False


def test_command_mode_first_run_still_writes_the_template(config_path, quiet_startup):
    with patch.object(sys, "argv", ["ayder", "hello"]), \
         patch.object(sys.stdin, "isatty", return_value=True), \
         patch("ayder_cli.cli_runner.run_command", return_value=0) as run_command, \
         patch("ayder_cli.tui.run_tui") as run_tui:
        with pytest.raises(SystemExit):
            cli.main()

    run_command.assert_called_once()
    run_tui.assert_not_called()
    assert config_path.exists()


def test_run_tui_passes_first_run_to_the_app(monkeypatch, tmp_path):
    seen = {}

    class FakeApp:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.return_code = 0
            self.messages = []

        def run(self, **kwargs):
            pass

    monkeypatch.setattr(tui, "AyderApp", FakeApp)
    monkeypatch.setattr(tui, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr("ayder_cli.core.session.persist_and_announce", lambda *a, **k: None)

    tui.run_tui(permissions=set(), first_run=True)

    assert seen["first_run"] is True


@pytest.mark.anyio
async def test_app_opens_the_wizard_on_first_run(config_path):
    from ayder_cli.tui.app import AyderApp

    ensure_latest_config(config_path, defaults=DEFAULTS)  # what load_config did
    app = AyderApp(model="test", first_run=True)
    async with app.run_test(size=(110, 50)) as pilot:
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, ConfigWizardScreen)
        assert app.screen._first_run is True
        assert app.screen._session_provider() == "openai"


@pytest.mark.anyio
async def test_app_without_first_run_shows_no_wizard(config_path):
    from ayder_cli.tui.app import AyderApp

    ensure_latest_config(config_path, defaults=DEFAULTS)
    app = AyderApp(model="test")
    async with app.run_test(size=(110, 50)) as pilot:
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, ConfigWizardScreen)
