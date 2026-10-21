"""Resume restore + replay for AyderApp."""

from unittest.mock import MagicMock

from ayder_cli.tui.app import AyderApp


def _restored():
    return [
        {"role": "system", "content": "RESTORED SYS"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_init_restores_history_and_rebuilds_system():
    app = AyderApp(
        model="test",
        initial_messages=_restored(),
        resume_session_id="a1b2-c3d4",
    )
    assert app._resuming is True
    assert app.resume_session_id == "a1b2-c3d4"
    assert app.messages[1:] == _restored()[1:]
    assert app.messages[0]["role"] == "system"
    assert app.messages[0]["content"] != "RESTORED SYS"


def test_resume_rebuilds_environment():
    """Baseline regression (audit P0-4): the saved prompt names a dead scratch dir."""
    old = [
        {"role": "system", "content": "SYS\n\n## Environment\nScratch directory: /tmp/ayder-x/old\n"},
        *_restored()[1:],
    ]
    app = AyderApp(model="test", initial_messages=old, resume_session_id="a1b2-c3d4")
    system = app.messages[0]["content"]
    assert app._environment_prompt and app._environment_prompt in system
    assert "/tmp/ayder-x/old" not in system
    assert app.messages[1:] == _restored()[1:]


def test_model_switch_keeps_capability_prompts():
    """New interface: /model used to drop the agent capability prompts."""
    app = AyderApp(model="test")
    app._capability_prompts = "\nCAP\n"
    app.update_system_prompt_model()
    assert app.messages[0]["content"].endswith("\nCAP\n")


def test_init_without_resume_builds_system_prompt():
    app = AyderApp(model="test")
    assert app._resuming is False
    assert app.resume_session_id is None
    assert app.messages and app.messages[0]["role"] == "system"


def test_replay_history_dispatches_to_chat_view():
    app = AyderApp(model="test", initial_messages=_restored(),
                   resume_session_id="a1b2-c3d4")
    chat_view = MagicMock()
    app._replay_history(chat_view)
    chat_view.add_user_message.assert_called_once_with("hi")
    chat_view.add_assistant_message.assert_called_once_with("hello")


class _FakeApp:
    """Stand-in for AyderApp so run_tui can be tested without Textual."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages = kwargs.get("initial_messages") or [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "hi"},
        ]
        self.resume_session_id = kwargs.get("resume_session_id")
        self.model = kwargs.get("model", "test")
        self.safe_mode = kwargs.get("safe_mode", False)
        self.permissions = kwargs.get("permissions") or {"r"}

    def run(self, **kwargs):
        return None


def test_run_tui_saves_session_on_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ayder_cli.tui.AyderApp", _FakeApp)
    from ayder_cli.tui import run_tui

    run_tui(permissions={"r", "w"}, model="m")

    files = list((tmp_path / ".ayder" / "sessions").glob("*.json"))
    assert len(files) == 1


def test_run_tui_reuses_resume_session_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ayder_cli.tui.AyderApp", _FakeApp)
    from ayder_cli.tui import run_tui

    run_tui(
        initial_messages=[
            {"role": "system", "content": "s"},
            {"role": "user", "content": "hi"},
        ],
        resume_session_id="a1b2-c3d4",
    )
    assert (tmp_path / ".ayder" / "sessions" / "a1b2-c3d4.json").exists()


def test_run_tui_saves_custom_system_prompt(tmp_path, monkeypatch):
    """Baseline regression (review): the override was never saved."""
    import json

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ayder_cli.tui.AyderApp", _FakeApp)
    from ayder_cli.tui import run_tui

    run_tui(system_prompt_override="CUSTOM", resume_session_id="a1b2-c3d4")
    data = json.loads((tmp_path / ".ayder" / "sessions" / "a1b2-c3d4.json").read_text())
    assert data["system_prompt_override"] == "CUSTOM"


def test_resumed_custom_prompt_survives_rebuild():
    """Preservation: a resumed app given the override keeps it in messages[0]."""
    app = AyderApp(model="test", initial_messages=_restored(), resume_session_id="a1b2-c3d4",
                   system_prompt_override="CUSTOM PERSONA")
    assert app.messages[0]["content"].startswith("CUSTOM PERSONA")


def test_run_tui_saves_active_provider(tmp_path, monkeypatch):
    """Baseline regression (live test): the provider was never saved."""
    import json
    from types import SimpleNamespace

    class _App(_FakeApp):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.config = SimpleNamespace(provider="anthropic")  # e.g. after /provider

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ayder_cli.tui.AyderApp", _App)
    from ayder_cli.tui import run_tui

    run_tui(resume_session_id="a1b2-c3d4")
    data = json.loads((tmp_path / ".ayder" / "sessions" / "a1b2-c3d4.json").read_text())
    assert data["provider"] == "anthropic"


def test_app_loads_the_given_provider(monkeypatch):
    """New interface: AyderApp(provider=...) builds its runtime from that profile."""
    from ayder_cli.core.config import Config
    from ayder_cli.tui import app as app_module

    seen = []

    def fake_load(provider):
        seen.append(provider)
        return Config()

    monkeypatch.setattr(app_module, "load_config_for_provider", fake_load)
    AyderApp(model="test", provider="anthropic")
    assert seen == ["anthropic"]
