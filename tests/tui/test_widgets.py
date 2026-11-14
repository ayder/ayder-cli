"""Tests for ActivityBar agent indicator."""


from textual.widgets import Static

from ayder_cli.tui.widgets import ActivityBar, _SubmitTextArea


class TestActivityBarAgents:
    def test_set_agents_running_stores_count(self):
        bar = ActivityBar()
        bar.set_agents_running(3)
        assert bar._agents_running == 3

    def test_set_agents_running_zero(self):
        bar = ActivityBar()
        bar.set_agents_running(3)
        bar.set_agents_running(0)
        assert bar._agents_running == 0


class TestFilePickerRendering:
    def test_malformed_markup_path_falls_back_to_plain_text(self):
        input_widget = _SubmitTextArea()
        input_widget._file_picker_widget = Static("", id="file-picker")
        malformed = '[agent-result name="reviewer" run="3" status="completed"]'
        input_widget._file_picker_suggestions = [malformed]

        input_widget._render_file_picker()

        assert input_widget._file_picker_widget.render().plain == f"> @{malformed}"


