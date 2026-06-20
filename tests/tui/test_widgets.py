"""Tests for ActivityBar agent indicator."""

from unittest.mock import patch, MagicMock

from ayder_cli.tui.widgets import ActivityBar, AgentPanel


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


class TestAgentPanelToggle:
    def test_starts_not_visible(self):
        panel = AgentPanel()
        assert panel._user_visible is False

    def test_toggle_returns_new_state(self):
        panel = AgentPanel()
        assert panel.toggle() is True
        assert panel._user_visible is True

    def test_toggle_twice_returns_false(self):
        panel = AgentPanel()
        panel.toggle()
        assert panel.toggle() is False
        assert panel._user_visible is False


class TestAgentPanelDataModel:
    @patch.object(AgentPanel, "mount")
    def test_add_agent_creates_entry(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("code_reviewer", run_id=1)
        assert 1 in panel._entries
        assert panel._entries[1].name == "code_reviewer"
        assert panel._entries[1].completed is False
        mock_mount.assert_called_once()

    @patch.object(AgentPanel, "mount")
    def test_add_agent_multiple_entries(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("agent_a", run_id=1)
        panel.add_agent("agent_b", run_id=2)
        assert len(panel._entries) == 2

    @patch.object(AgentPanel, "mount")
    def test_add_agent_stores_assignment_label(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("senior_coder", run_id=1, assignment="refactor auth · TASK-003")
        assert panel._entries[1].assignment == "refactor auth · TASK-003"

    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "mount")
    def test_update_agent_first_event_sets_assignment(self, mock_mount, mock_update):
        # Entry born from a progress event that carries the label (no prior add_agent).
        panel = AgentPanel()
        panel.update_agent(2, "senior_coder", "thinking_start", assignment="TASK-009")
        assert panel._entries[2].assignment == "TASK-009"

    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "mount")
    def test_running_status_line_includes_assignment(self, mock_mount, mock_update):
        # The "▶ name — <prompt> · <task_id> — Thinking..." line the user asked for.
        panel = AgentPanel()
        panel.add_agent("senior_coder", run_id=1, assignment="refactor auth · TASK-003")
        panel.update_agent(1, "senior_coder", "thinking_start")
        rendered = mock_update.call_args[0][0].plain
        assert "senior_coder" in rendered
        assert "refactor auth · TASK-003" in rendered
        assert "Thinking..." in rendered

    @patch.object(AgentPanel, "mount")
    def test_redispatch_creates_second_entry(self, mock_mount):
        panel = AgentPanel()
        panel.add_agent("code_reviewer", run_id=1)
        panel.add_agent("code_reviewer", run_id=2)
        assert 1 in panel._entries
        assert 2 in panel._entries
        assert len(panel._entries) == 2

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_marks_completed(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        panel = AgentPanel()
        panel.add_agent("web_parser", run_id=5)
        panel.complete_agent(5, "Found 3 results", "completed")
        assert panel._entries[5].completed is True

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_done_shows_green_check(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        # A successful run reports status "done" (pull-delivery vocabulary): it
        # must render the green check + "completed" CSS class, never the red ✗.
        panel = AgentPanel()
        panel.add_agent("web_parser", run_id=5)
        panel.complete_agent(5, "Found 3 results", "done")
        rendered = mock_update.call_args[0][0].plain
        assert "✓" in rendered
        assert "✗" not in rendered
        mock_add_class.assert_any_call("completed")

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_error_shows_red_x(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        panel = AgentPanel()
        panel.add_agent("web_parser", run_id=5)
        panel.complete_agent(5, "boom", "error")
        rendered = mock_update.call_args[0][0].plain
        assert "✗" in rendered
        assert "✓" not in rendered
        mock_add_class.assert_any_call("error")

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_complete_agent_stores_detail(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        panel = AgentPanel()
        panel.add_agent("web_parser", run_id=5)
        panel.complete_agent(5, "Full summary text here", "completed")
        assert panel._entries[5].detail_widget is not None

    def test_complete_unknown_run_id_is_noop(self):
        panel = AgentPanel()
        panel.complete_agent(999, "summary", "completed")

    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "mount")
    def test_update_agent_unknown_creates_entry(self, mock_mount, mock_update):
        panel = AgentPanel()
        panel.update_agent(42, "auto_created", "thinking_start")
        assert 42 in panel._entries

    @patch("ayder_cli.tui.widgets.Static.add_class")
    @patch("ayder_cli.tui.widgets.Static.remove_class")
    @patch("ayder_cli.tui.widgets.Static.update")
    @patch.object(AgentPanel, "scroll_end")
    @patch.object(AgentPanel, "mount")
    def test_prune_at_50_entries(self, mock_mount, mock_scroll, mock_update, mock_remove_class, mock_add_class):
        panel = AgentPanel()
        for i in range(50):
            panel.add_agent(f"agent_{i}", run_id=i + 1)
            panel.complete_agent(i + 1, f"summary {i}", "completed")
        assert len(panel._entries) == 50
        # 51st should prune oldest completed
        oldest_run_id = next(iter(panel._entries))
        panel._entries[oldest_run_id].status_widget.remove = MagicMock()
        if panel._entries[oldest_run_id].detail_widget:
            panel._entries[oldest_run_id].detail_widget.remove = MagicMock()
        panel.add_agent("agent_50", run_id=51)
        assert len(panel._entries) == 50
        assert oldest_run_id not in panel._entries
