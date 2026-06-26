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
