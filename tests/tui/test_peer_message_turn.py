"""A peer message becomes an ordinary queued user turn.

The socket half is covered in tests/services/test_messaging_inbox.py; this
pins the other half — what the inbox callback does to the app.
"""

import asyncio

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _app(monkeypatch):
    from ayder_cli.tui.app import AyderApp

    app = AyderApp.__new__(AyderApp)
    app._requests = asyncio.Queue()
    app._run_task = None
    app._agent_registry = None
    app._inbox = None
    app._transcript_id = "0000-0000"
    app.messages = []
    monkeypatch.setattr(app, "query_one", lambda *a, **k: _Boom(), raising=False)
    return app


class _Boom:
    """Stands in for the chat view; echoing must be optional."""

    def add_user_message(self, _text):
        raise RuntimeError("no chat view mounted")


def test_peer_message_enqueues_a_turn_even_if_echo_fails(monkeypatch):
    app = _app(monkeypatch)
    app._on_peer_message("run the mysql post-mortem")

    assert app._requests.qsize() == 1
    req = app._requests.get_nowait()
    # The append is deferred into prepare, matching a typed submission.
    assert app.messages == []
    req.prepare()
    assert app.messages == [
        {"role": "user", "content": "run the mysql post-mortem"}
    ]
    assert req.run_loop is True


def test_peer_message_does_not_interrupt_an_active_turn(monkeypatch):
    """It queues; the consumer runs it when quiescent."""
    app = _app(monkeypatch)
    sentinel = object()
    app._run_task = sentinel
    app._cancel_event = asyncio.Event()

    app._on_peer_message("later please")

    assert app._run_task is sentinel, "the active turn was cancelled"
    assert not app._cancel_event.is_set()
    assert app._requests.qsize() == 1


def test_status_hook_tolerates_a_missing_inbox(monkeypatch):
    app = _app(monkeypatch)
    del app._inbox
    app._set_inbox_status("busy")  # must not raise


def test_status_hook_forwards_to_the_inbox(monkeypatch):
    app = _app(monkeypatch)
    seen = []
    app._inbox = type("I", (), {"set_status": lambda _s, v: seen.append(v)})()
    app._set_inbox_status("busy")
    assert seen == ["busy"]


# ---------------------------------------------------------------------------
# Session naming
# ---------------------------------------------------------------------------


def test_session_name_falls_back_to_the_transcript_id(monkeypatch):
    app = _app(monkeypatch)
    app._session_name = ""
    assert app.session_name() == "ayder-0000-0000"


def test_rename_without_an_inbox_still_takes_effect(monkeypatch):
    app = _app(monkeypatch)
    assert app.rename_session("mysql-agent") == "mysql-agent"
    assert app.session_name() == "mysql-agent"


def test_rename_republishes_through_the_inbox(monkeypatch):
    app = _app(monkeypatch)
    seen = []

    class _Inbox:
        name = "old"

        def set_name(self, value, source="user"):
            seen.append((value, source))
            self.name = value

    app._inbox = _Inbox()
    assert app.rename_session("mysql-agent") == "mysql-agent"
    assert seen == [("mysql-agent", "user")]
    assert app.session_name() == "mysql-agent"


def test_rename_command_rejects_unpublishable_names(monkeypatch):
    from ayder_cli.tui.commands import handle_rename

    app = _app(monkeypatch)
    said = []
    view = type("V", (), {"add_system_message": lambda _s, m: said.append(m)})()

    handle_rename(app, 'has"quote', view)
    assert "Invalid name" in said[-1]
    handle_rename(app, "x" * 65, view)
    assert "Invalid name" in said[-1]
    handle_rename(app, "with<angle>", view)
    assert "Invalid name" in said[-1]
    assert app.session_name() != 'has"quote'


def test_rename_command_reports_current_name_when_bare(monkeypatch):
    from ayder_cli.tui.commands import handle_rename

    app = _app(monkeypatch)
    app.rename_session("current-one")
    said = []
    view = type("V", (), {"add_system_message": lambda _s, m: said.append(m)})()
    handle_rename(app, "   ", view)
    assert "current-one" in said[-1] and "/rename <name>" in said[-1]


def test_rename_command_sets_the_name(monkeypatch):
    from ayder_cli.tui.commands import handle_rename

    app = _app(monkeypatch)
    said = []
    view = type("V", (), {"add_system_message": lambda _s, m: said.append(m)})()
    handle_rename(app, "  mysql-agent  ", view)
    assert app.session_name() == "mysql-agent"
    assert "mysql-agent" in said[-1]


def test_rename_is_discoverable_in_help():
    from ayder_cli.tui.commands import COMMAND_MAP

    assert "/rename" in COMMAND_MAP
    assert COMMAND_MAP["/rename"].__doc__.strip().startswith("Rename this session")


# ---------------------------------------------------------------------------
# Real construction — session_name must never reach Textual's App.__init__
# ---------------------------------------------------------------------------


def test_app_constructs_with_a_session_name():
    """Regression: session_name leaked to super() and raised

        TypeError: App.__init__() got an unexpected keyword argument 'session_name'

    which made `ayder` unstartable. Every other test builds the app with
    __new__ or mocks it, so only real construction catches this.
    """
    from ayder_cli.tui.app import AyderApp

    app = AyderApp(session_name="probe-name")
    assert app.session_name() == "probe-name"


def test_app_constructs_without_a_session_name():
    """The name is optional; a handle is still produced."""
    import re

    from ayder_cli.tui.app import AyderApp

    app = AyderApp()
    assert re.fullmatch(r"ayder-[0-9a-f]{4}-[0-9a-f]{4}", app.session_name())


def test_the_default_handle_is_the_resumable_id():
    """The handle a peer addresses is the id `ayder --resume` takes."""
    from ayder_cli.tui.app import AyderApp

    app = AyderApp()
    assert app.session_name() == f"ayder-{app._transcript_id}"


def test_resuming_keeps_the_handle_stable():
    from ayder_cli.tui.app import AyderApp

    app = AyderApp(resume_session_id="6fa2-b71b")
    assert app._transcript_id == "6fa2-b71b"
    assert app.session_name() == "ayder-6fa2-b71b"
