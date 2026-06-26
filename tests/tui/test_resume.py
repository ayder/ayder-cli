"""Resume restore + replay for AyderApp."""

from unittest.mock import MagicMock

from ayder_cli.tui.app import AyderApp


def _restored():
    return [
        {"role": "system", "content": "RESTORED SYS"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_init_seeds_messages_and_skips_system_rebuild():
    app = AyderApp(
        model="test",
        initial_messages=_restored(),
        resume_session_id="a1b2-c3d4",
    )
    assert app._resuming is True
    assert app.resume_session_id == "a1b2-c3d4"
    # No fresh system prompt appended; restored list is used verbatim.
    assert app.messages == _restored()
    assert app.messages[0]["content"] == "RESTORED SYS"


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
