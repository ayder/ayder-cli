"""_maybe_nudge: nudges once when idle with an unread result; never while busy/looping."""

from unittest.mock import MagicMock

from ayder_cli.agents.run import AgentRun


class FakeReg:
    def __init__(self, runs):
        self._runs = runs

    def pending_nudge(self):
        return [r for r in self._runs if r.status in ("done", "error") and not r.drained and not r.nudged]

    def mark_nudged(self, runs):
        for r in runs:
            r.nudged = True


def _app(reg, processing=False):
    from ayder_cli.tui.app import AyderApp
    app = AyderApp.__new__(AyderApp)            # bypass __init__/Textual
    app._agent_registry = reg
    app._run_task = object() if processing else None   # property derives _is_processing
    app.messages = []
    # _maybe_nudge defers the message append into request_turn's prepare; run it
    # immediately so the test can observe the effect (mirrors the serial consumer).
    def _run_prepare(prepare=None, **kw):
        if prepare is not None:
            prepare()
    app.request_turn = MagicMock(side_effect=_run_prepare)
    return app


def test_nudges_once_when_idle_with_unread():
    run = AgentRun(1, 1, "a", 0.0, status="done", result="R")
    app = _app(FakeReg([run]))
    app._maybe_nudge()
    assert app.request_turn.call_count == 1
    assert "unread" in app.messages[0]["content"]   # nudge text appended via prepare
    app._maybe_nudge()                          # already nudged -> no second wake (no loop)
    assert app.request_turn.call_count == 1


def test_no_nudge_while_processing():
    run = AgentRun(1, 1, "a", 0.0, status="done", result="R")
    app = _app(FakeReg([run]), processing=True)
    app._maybe_nudge()
    app.request_turn.assert_not_called()


def test_no_nudge_without_pending():
    app = _app(FakeReg([AgentRun(1, 1, "a", 0.0, status="working")]))
    app._maybe_nudge()
    app.request_turn.assert_not_called()


def test_do_clear_bumps_generation():
    from unittest.mock import MagicMock, patch
    from ayder_cli.tui.commands import do_clear
    app = MagicMock()
    app._agent_registry = MagicMock()
    app.messages = []
    # do_clear now enqueues via request_turn(prepare=...); run the captured prepare.
    app.request_turn.side_effect = lambda prepare=None, **kw: prepare() if prepare else None
    with patch("ayder_cli.tools.builtins.context.snapshot_conversation_for_clear", return_value=None):
        do_clear(app, MagicMock())
    app._agent_registry.new_generation.assert_called_once()
