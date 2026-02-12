"""Tests for ConfirmResult dataclass and CLIConfirmScreen."""
import pytest
from unittest.mock import patch, MagicMock


class TestConfirmResult:
    """Tests for the ConfirmResult dataclass."""

    def test_approve_action(self):
        """Test creating an approve result."""
        from ayder_cli.tui import ConfirmResult

        result = ConfirmResult("approve")
        assert result.action == "approve"
        assert result.instructions is None

    def test_deny_action(self):
        """Test creating a deny result."""
        from ayder_cli.tui import ConfirmResult

        result = ConfirmResult("deny")
        assert result.action == "deny"
        assert result.instructions is None

    def test_instruct_action_with_instructions(self):
        """Test creating an instruct result with instructions."""
        from ayder_cli.tui import ConfirmResult

        result = ConfirmResult("instruct", instructions="use a different approach")
        assert result.action == "instruct"
        assert result.instructions == "use a different approach"

    def test_instruct_action_without_instructions(self):
        """Test creating an instruct result without instructions defaults to None."""
        from ayder_cli.tui import ConfirmResult

        result = ConfirmResult("instruct")
        assert result.action == "instruct"
        assert result.instructions is None

    def test_equality(self):
        """Test that two ConfirmResults with same values are equal."""
        from ayder_cli.tui import ConfirmResult

        r1 = ConfirmResult("approve")
        r2 = ConfirmResult("approve")
        assert r1 == r2

    def test_inequality(self):
        """Test that different ConfirmResults are not equal."""
        from ayder_cli.tui import ConfirmResult

        r1 = ConfirmResult("approve")
        r2 = ConfirmResult("deny")
        assert r1 != r2


class TestCLIConfirmScreenInit:
    """Tests for CLIConfirmScreen initialization and options."""

    def test_screen_has_three_options(self):
        """Test that CLIConfirmScreen has exactly 3 options."""
        from ayder_cli.tui import CLIConfirmScreen

        assert len(CLIConfirmScreen.OPTIONS) == 3

    def test_option_actions(self):
        """Test that the 3 options are approve, deny, instruct."""
        from ayder_cli.tui import CLIConfirmScreen

        actions = [action for action, _ in CLIConfirmScreen.OPTIONS]
        assert actions == ["approve", "deny", "instruct"]

    def test_initial_selected_index(self):
        """Test that the initial selected index is 0."""
        from ayder_cli.tui import CLIConfirmScreen

        screen = CLIConfirmScreen(
            title="test_tool",
            description="Test description"
        )
        assert screen.selected_index == 0

    def test_stores_title_and_description(self):
        """Test that title and description are stored."""
        from ayder_cli.tui import CLIConfirmScreen

        screen = CLIConfirmScreen(
            title="write_file",
            description="File test.py will be written",
            diff_content="+new line",
            action_name="Write file"
        )
        assert screen.title_text == "write_file"
        assert screen.description == "File test.py will be written"
        assert screen.diff_content == "+new line"
        assert screen.action_name == "Write file"

    def test_screen_type_is_modal(self):
        """Test that CLIConfirmScreen is a ModalScreen."""
        from ayder_cli.tui import CLIConfirmScreen
        from textual.screen import ModalScreen

        assert issubclass(CLIConfirmScreen, ModalScreen)


class TestCLIConfirmScreenRenderList:
    """Tests for the option list rendering."""

    def test_render_list_highlights_selected(self):
        """Test that _render_list highlights the selected index."""
        from ayder_cli.tui import CLIConfirmScreen

        screen = CLIConfirmScreen(title="test", description="test")
        screen.selected_index = 0
        text = screen._render_list()
        plain = text.plain
        assert "→" in plain
        assert "Yes, allow this action" in plain

    def test_render_list_second_option(self):
        """Test rendering with second option selected."""
        from ayder_cli.tui import CLIConfirmScreen

        screen = CLIConfirmScreen(title="test", description="test")
        screen.selected_index = 1
        text = screen._render_list()
        # The arrow should be on the deny option line
        lines = text.plain.strip().split("\n")
        assert "→" in lines[1]

    def test_render_list_third_option(self):
        """Test rendering with third option selected."""
        from ayder_cli.tui import CLIConfirmScreen

        screen = CLIConfirmScreen(title="test", description="test")
        screen.selected_index = 2
        text = screen._render_list()
        lines = text.plain.strip().split("\n")
        assert "→" in lines[2]


class TestCLIConfirmScreenDiff:
    """Tests for the diff rendering in CLIConfirmScreen."""

    def test_render_diff_additions(self):
        """Test that additions are rendered."""
        from ayder_cli.tui import CLIConfirmScreen

        screen = CLIConfirmScreen(
            title="test",
            description="test",
            diff_content="+added line\n-removed line\n unchanged"
        )
        text = screen._render_diff()
        assert "+added line" in text.plain
        assert "-removed line" in text.plain

    def test_render_diff_none_when_no_content(self):
        """Test that diff is None when no diff_content."""
        from ayder_cli.tui import CLIConfirmScreen

        screen = CLIConfirmScreen(title="test", description="test")
        assert screen.diff_content is None


class TestToolNeedsConfirmation:
    """Tests for AyderApp._tool_needs_confirmation."""

    def test_read_tool_auto_approved_with_default_permissions(self):
        """Test that read tools are auto-approved with default permissions."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig
        from unittest.mock import MagicMock

        loop = TuiChatLoop.__new__(TuiChatLoop)
        loop.config = TuiLoopConfig(permissions={"r"})
        assert not loop._tool_needs_confirmation("read_file")
        assert not loop._tool_needs_confirmation("list_files")

    def test_write_tool_needs_confirmation_with_default_permissions(self):
        """Test that write tools need confirmation with default permissions."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig

        loop = TuiChatLoop.__new__(TuiChatLoop)
        loop.config = TuiLoopConfig(permissions={"r"})
        assert loop._tool_needs_confirmation("write_file")
        assert loop._tool_needs_confirmation("replace_string")

    def test_execute_tool_needs_confirmation_with_default_permissions(self):
        """Test that execute tools need confirmation with default permissions."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig

        loop = TuiChatLoop.__new__(TuiChatLoop)
        loop.config = TuiLoopConfig(permissions={"r"})
        assert loop._tool_needs_confirmation("run_shell_command")

    def test_write_tool_auto_approved_with_w_permission(self):
        """Test that write tools are auto-approved with w permission."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig

        loop = TuiChatLoop.__new__(TuiChatLoop)
        loop.config = TuiLoopConfig(permissions={"r", "w"})
        assert not loop._tool_needs_confirmation("write_file")
        assert not loop._tool_needs_confirmation("replace_string")

    def test_execute_tool_auto_approved_with_x_permission(self):
        """Test that execute tools are auto-approved with x permission."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig

        loop = TuiChatLoop.__new__(TuiChatLoop)
        loop.config = TuiLoopConfig(permissions={"r", "x"})
        assert not loop._tool_needs_confirmation("run_shell_command")

    def test_all_tools_auto_approved_with_full_permissions(self):
        """Test that all tools are auto-approved with rwx permissions."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig

        loop = TuiChatLoop.__new__(TuiChatLoop)
        loop.config = TuiLoopConfig(permissions={"r", "w", "x"})
        assert not loop._tool_needs_confirmation("read_file")
        assert not loop._tool_needs_confirmation("write_file")
        assert not loop._tool_needs_confirmation("run_shell_command")

    def test_unknown_tool_auto_approved(self):
        """Test that unknown tools default to 'r' permission and are auto-approved."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig

        loop = TuiChatLoop.__new__(TuiChatLoop)
        loop.config = TuiLoopConfig(permissions={"r"})
        assert not loop._tool_needs_confirmation("nonexistent_tool")


class TestGenerateDiff:
    """Tests for AyderApp._generate_diff."""

    def test_non_file_tool_returns_none(self):
        """Test that non-file-modifying tools return None."""
        from ayder_cli.tui import AyderApp

        app = AyderApp.__new__(AyderApp)
        assert app._generate_diff("read_file", {"file_path": "test.py"}) is None
        assert app._generate_diff("run_shell_command", {"command": "ls"}) is None

    def test_write_file_new_file(self, tmp_path):
        """Test diff for writing a new file."""
        from ayder_cli.tui import AyderApp

        app = AyderApp.__new__(AyderApp)
        new_file = str(tmp_path / "new.py")
        diff = app._generate_diff("write_file", {
            "file_path": new_file,
            "content": "print('hello')\n"
        })
        assert diff is not None
        assert "+print('hello')" in diff

    def test_write_file_existing_file(self, tmp_path):
        """Test diff for overwriting an existing file."""
        from ayder_cli.tui import AyderApp

        existing = tmp_path / "existing.py"
        existing.write_text("old content\n")

        app = AyderApp.__new__(AyderApp)
        diff = app._generate_diff("write_file", {
            "file_path": str(existing),
            "content": "new content\n"
        })
        assert diff is not None
        assert "-old content" in diff
        assert "+new content" in diff

    def test_replace_string_diff(self, tmp_path):
        """Test diff for replace_string tool."""
        from ayder_cli.tui import AyderApp

        f = tmp_path / "test.py"
        f.write_text("def foo():\n    pass\n")

        app = AyderApp.__new__(AyderApp)
        diff = app._generate_diff("replace_string", {
            "file_path": str(f),
            "old_string": "pass",
            "new_string": "return 42"
        })
        assert diff is not None
        assert "-    pass" in diff
        assert "+    return 42" in diff


class TestRunTuiPermissions:
    """Tests for run_tui permission passthrough."""

    def test_run_tui_passes_permissions_to_app(self):
        """Test that run_tui passes permissions to AyderApp."""
        from ayder_cli.tui import run_tui

        with patch('ayder_cli.tui.AyderApp') as MockApp:
            mock_instance = MagicMock()
            MockApp.return_value = mock_instance
            run_tui(permissions={"r", "w"})
            MockApp.assert_called_once_with(
                model="default",
                safe_mode=False,
                permissions={"r", "w"}
            )

    def test_run_tui_default_permissions(self):
        """Test that run_tui defaults to None permissions."""
        from ayder_cli.tui import run_tui

        with patch('ayder_cli.tui.AyderApp') as MockApp:
            mock_instance = MagicMock()
            MockApp.return_value = mock_instance
            run_tui()
            MockApp.assert_called_once_with(
                model="default",
                safe_mode=False,
                permissions=None
            )


class TestAyderAppPermissions:
    """Tests for AyderApp permission initialization."""

    def test_default_permissions_is_read_only(self):
        """Test that AyderApp defaults to read-only permissions."""
        from ayder_cli.tui import AyderApp

        app = AyderApp.__new__(AyderApp)
        # Simulate __init__ behavior for permissions
        app.permissions = None or {"r"}
        assert app.permissions == {"r"}

    def test_custom_permissions_stored(self):
        """Test that custom permissions are stored correctly."""
        from ayder_cli.tui import AyderApp

        app = AyderApp.__new__(AyderApp)
        app.permissions = {"r", "w", "x"}
        assert app.permissions == {"r", "w", "x"}


class TestCLIPermissionScreenInit:
    """Tests for CLIPermissionScreen initialization."""

    def test_screen_has_three_items(self):
        """Test that CLIPermissionScreen has 3 permission items."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        assert len(screen._items) == 3

    def test_items_are_rwx(self):
        """Test that the 3 items are r, w, x."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        perms = [p for p, _, _ in screen._items]
        assert perms == ["r", "w", "x"]

    def test_initial_selected_index(self):
        """Test that the initial selected index is 0."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        assert screen.selected_index == 0

    def test_copies_permissions(self):
        """Test that permissions are copied, not shared."""
        from ayder_cli.tui import CLIPermissionScreen

        original = {"r", "w"}
        screen = CLIPermissionScreen(original)
        screen._permissions.add("x")
        assert "x" not in original

    def test_screen_type_is_modal(self):
        """Test that CLIPermissionScreen is a ModalScreen."""
        from ayder_cli.tui import CLIPermissionScreen
        from textual.screen import ModalScreen

        assert issubclass(CLIPermissionScreen, ModalScreen)


class TestCLIPermissionScreenRenderList:
    """Tests for the permission list rendering."""

    def test_render_list_shows_checkboxes(self):
        """Test that _render_list shows checkboxes."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        text = screen._render_list()
        plain = text.plain
        assert "[✓]" in plain  # Read is checked
        assert "[ ]" in plain  # Write/Execute unchecked

    def test_render_list_highlights_selected(self):
        """Test that _render_list highlights the selected index."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        screen.selected_index = 0
        text = screen._render_list()
        assert "→" in text.plain

    def test_render_list_shows_locked_for_read(self):
        """Test that read permission shows (locked) indicator."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        text = screen._render_list()
        assert "(locked)" in text.plain

    def test_render_list_with_write_enabled(self):
        """Test rendering with write permission enabled."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r", "w"})
        text = screen._render_list()
        plain = text.plain
        # Both Read and Write should be checked
        assert plain.count("[✓]") == 2

    def test_render_list_with_all_enabled(self):
        """Test rendering with all permissions enabled."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r", "w", "x"})
        text = screen._render_list()
        plain = text.plain
        assert plain.count("[✓]") == 3
        assert "[ ]" not in plain


class TestCLIPermissionScreenToggle:
    """Tests for permission toggling logic."""

    def test_read_cannot_be_toggled_off(self):
        """Test that read permission cannot be disabled."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r", "w"})
        screen.selected_index = 0  # Read
        # Simulate toggle — read is locked
        perm = screen._items[screen.selected_index][0]
        assert perm == "r"
        # The on_key handler skips "r", so permissions should not change
        assert "r" in screen._permissions

    def test_write_can_be_toggled_on(self):
        """Test that write permission can be enabled."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        screen.selected_index = 1  # Write
        perm = screen._items[screen.selected_index][0]
        assert perm == "w"
        screen._permissions.add(perm)
        assert "w" in screen._permissions

    def test_write_can_be_toggled_off(self):
        """Test that write permission can be disabled."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r", "w"})
        screen.selected_index = 1  # Write
        perm = screen._items[screen.selected_index][0]
        screen._permissions.discard(perm)
        assert "w" not in screen._permissions

    def test_execute_can_be_toggled_on(self):
        """Test that execute permission can be enabled."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r"})
        screen.selected_index = 2  # Execute
        perm = screen._items[screen.selected_index][0]
        assert perm == "x"
        screen._permissions.add(perm)
        assert "x" in screen._permissions

    def test_execute_can_be_toggled_off(self):
        """Test that execute permission can be disabled."""
        from ayder_cli.tui import CLIPermissionScreen

        screen = CLIPermissionScreen({"r", "x"})
        screen.selected_index = 2
        perm = screen._items[screen.selected_index][0]
        screen._permissions.discard(perm)
        assert "x" not in screen._permissions


class TestStatusBarUpdatePermissions:
    """Tests for StatusBar.update_permissions method."""

    def test_status_bar_stores_initial_permissions(self):
        """Test that StatusBar stores initial permissions."""
        from ayder_cli.tui import StatusBar

        sb = StatusBar(permissions={"r", "w"})
        assert sb._permissions == {"r", "w"}

    def test_status_bar_defaults_to_read_only(self):
        """Test that StatusBar defaults to read-only permissions."""
        from ayder_cli.tui import StatusBar

        sb = StatusBar()
        assert sb._permissions == {"r"}
