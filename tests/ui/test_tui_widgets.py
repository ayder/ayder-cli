"""Tests for TUI widget slash-command completion behavior."""

from ayder_cli.tui.widgets import _SubmitTextArea


def test_slash_completion_cycles_across_multiple_matches():
    input_widget = _SubmitTextArea(commands=["/load-memory", "/logging", "/plan"])

    assert input_widget._next_tab_completion("/lo") == "/load-memory"
    assert input_widget._next_tab_completion("/load-memory") == "/logging"
    assert input_widget._next_tab_completion("/logging") == "/load-memory"


def test_slash_completion_single_match_stays_on_same_command():
    input_widget = _SubmitTextArea(commands=["/load-memory", "/logging", "/plan"])

    assert input_widget._next_tab_completion("/log") == "/logging"
    assert input_widget._next_tab_completion("/logging") == "/logging"


def test_slash_completion_resets_when_prefix_changes():
    input_widget = _SubmitTextArea(commands=["/load-memory", "/logging", "/plan"])

    assert input_widget._next_tab_completion("/lo") == "/load-memory"
    assert input_widget._next_tab_completion("/load-memory") == "/logging"
    assert input_widget._next_tab_completion("/p") == "/plan"
    assert input_widget._next_tab_completion("hello") is None
    assert input_widget._next_tab_completion("/lo") == "/load-memory"
