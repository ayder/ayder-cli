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
    app._is_processing = processing
    app.messages = []
    app.start_llm_processing = MagicMock()
    return app


def test_nudges_once_when_idle_with_unread():
    run = AgentRun(1, 1, "a", 0.0, status="done", result="R")
    app = _app(FakeReg([run]))
    app._maybe_nudge()
    assert app.start_llm_processing.call_count == 1
    assert "unread" in app.messages[0]["content"]
    app._maybe_nudge()                          # already nudged -> no second wake (no loop)
    assert app.start_llm_processing.call_count == 1


def test_no_nudge_while_processing():
    run = AgentRun(1, 1, "a", 0.0, status="done", result="R")
    app = _app(FakeReg([run]), processing=True)
    app._maybe_nudge()
    app.start_llm_processing.assert_not_called()


def test_no_nudge_without_pending():
    app = _app(FakeReg([AgentRun(1, 1, "a", 0.0, status="working")]))
    app._maybe_nudge()
    app.start_llm_processing.assert_not_called()
