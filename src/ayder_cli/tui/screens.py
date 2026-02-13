"""Modal screens for the TUI: confirm, permission, safe mode, select, task edit."""

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, Input, Label, TextArea
from textual.screen import ModalScreen
from rich.text import Text

from ayder_cli.tui.types import ConfirmResult


class CLIConfirmScreen(ModalScreen[ConfirmResult | None]):
    """
    CLI-style 3-option confirmation screen.
    Options: approve, deny, or provide custom instructions.
    """

    OPTIONS = [
        ("approve", "Yes, allow this action"),
        ("deny", "No, deny this action"),
        ("instruct", "Provide custom instructions"),
    ]

    def __init__(
        self,
        title: str,
        description: str,
        diff_content: str = None,
        action_name: str = "Confirm"
    ):
        super().__init__()
        self.title_text = title
        self.description = description
        self.diff_content = diff_content
        self.action_name = action_name
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Vertical():
            yield Label(f"? Tool: {self.title_text}", classes="prompt")
            yield Label(self.description, classes="description")

            if self.diff_content:
                diff_text = self._render_diff()
                with VerticalScroll(classes="diff-container", id="diff-scroll"):
                    yield Static(diff_text, id="diff-content")

            list_content = self._render_list()
            yield Static(list_content, id="option-list", classes="option-list")

            yield Input(
                placeholder="Type your instructions...",
                id="instruction-input"
            )

            yield Label(
                "↑↓ navigate, PgUp/PgDn scroll diff, Enter select, Y/N shortcut, Esc cancel",
                classes="hint"
            )

    def _render_list(self) -> Text:
        """Render the 3-option list with current highlight."""
        result = Text()
        for i, (_, display) in enumerate(self.OPTIONS):
            if i == self.selected_index:
                result.append(" → ", style="bold cyan")
                result.append(display, style="bold white")
            else:
                result.append("   ", style="dim")
                result.append(display, style="white")
            result.append("\n")
        return result

    def _update_display(self) -> None:
        """Update the list display after navigation."""
        list_widget = self.query_one("#option-list", Static)
        list_widget.update(self._render_list())

    def _render_diff(self) -> Text:
        """Render diff content with syntax highlighting."""
        lines = self.diff_content.split('\n')
        result = Text()

        for line in lines:
            line = line.rstrip('\n')
            if line.startswith('@@'):
                result.append(line + "\n", style="cyan")
            elif line.startswith('-') and not line.startswith('---'):
                result.append(line + "\n", style="red")
            elif line.startswith('+') and not line.startswith('+++'):
                result.append(line + "\n", style="green")
            else:
                result.append(line + "\n", style="dim")

        return result

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle instruction input submission."""
        text = event.value.strip()
        if text:
            self.dismiss(ConfirmResult("instruct", instructions=text))
        else:
            # Empty input, go back to list
            input_widget = self.query_one("#instruction-input", Input)
            input_widget.display = False
            self._update_display()

    def on_key(self, event) -> None:
        """Handle keyboard navigation and shortcuts."""
        # Don't intercept keys when instruction input is focused
        input_widget = self.query_one("#instruction-input", Input)
        if input_widget.display and input_widget.has_focus:
            if event.key.lower() == "escape":
                event.stop()
                input_widget.display = False
                self._update_display()
            return

        key = event.key.lower()

        if key in ("pageup", "pagedown"):
            event.stop()
            try:
                diff_scroll = self.query_one("#diff-scroll", VerticalScroll)
                if key == "pageup":
                    diff_scroll.scroll_page_up(animate=False)
                else:
                    diff_scroll.scroll_page_down(animate=False)
            except Exception:
                pass
            return

        if key in ("up", "k"):
            event.stop()
            self.selected_index = max(0, self.selected_index - 1)
            self._update_display()
        elif key in ("down", "j"):
            event.stop()
            self.selected_index = min(len(self.OPTIONS) - 1, self.selected_index + 1)
            self._update_display()
        elif key in ("enter", "return"):
            event.stop()
            self._select_current()
        elif key == "y":
            event.stop()
            self.dismiss(ConfirmResult("approve"))
        elif key in ("n", "escape", "q"):
            event.stop()
            self.dismiss(None)

    def _select_current(self) -> None:
        """Select the currently highlighted option."""
        action = self.OPTIONS[self.selected_index][0]
        if action == "approve":
            self.dismiss(ConfirmResult("approve"))
        elif action == "deny":
            self.dismiss(ConfirmResult("deny"))
        elif action == "instruct":
            input_widget = self.query_one("#instruction-input", Input)
            input_widget.display = True
            input_widget.focus()


class CLIPermissionScreen(ModalScreen[set | None]):
    """
    CLI-style permission toggle screen.
    Allows enabling/disabling write and execute permissions.
    """

    def __init__(self, current_permissions: set):
        super().__init__()
        self._permissions = set(current_permissions)
        self.selected_index = 0
        self._items = [
            ("r", "Read", "Auto-approve read tools (always enabled)"),
            ("w", "Write", "Auto-approve write tools (write_file, replace_string, ...)"),
            ("x", "Execute", "Auto-approve execute tools (run_shell_command, ...)"),
        ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("? Permissions", classes="prompt")
            yield Label("Toggle which tool categories are auto-approved", classes="description")
            yield Static(self._render_list(), id="perm-list", classes="option-list")
            yield Label(
                "↑↓ navigate, Space/Enter toggle, Esc apply & close",
                classes="hint"
            )

    def _render_list(self) -> Text:
        result = Text()
        for i, (perm, label, desc) in enumerate(self._items):
            is_selected = i == self.selected_index
            is_enabled = perm in self._permissions
            is_locked = perm == "r"

            # Checkbox
            if is_enabled:
                checkbox = "[✓]" if not is_locked else "[✓]"
            else:
                checkbox = "[ ]"

            # Arrow indicator
            if is_selected:
                result.append(" → ", style="bold cyan")
                result.append(f"{checkbox} ", style="bold green" if is_enabled else "bold dim")
                result.append(f"{label}", style="bold white")
                result.append(f"  {desc}", style="dim")
            else:
                result.append("   ", style="dim")
                result.append(f"{checkbox} ", style="green" if is_enabled else "dim")
                result.append(f"{label}", style="white")
                result.append(f"  {desc}", style="dim")

            if is_locked:
                result.append(" (locked)", style="dim italic")

            result.append("\n")
        return result

    def _update_display(self) -> None:
        list_widget = self.query_one("#perm-list", Static)
        list_widget.update(self._render_list())

    def on_key(self, event) -> None:
        key = event.key.lower()

        if key in ("up", "k"):
            event.stop()
            self.selected_index = max(0, self.selected_index - 1)
            self._update_display()
        elif key in ("down", "j"):
            event.stop()
            self.selected_index = min(len(self._items) - 1, self.selected_index + 1)
            self._update_display()
        elif key in ("space", "enter", "return"):
            event.stop()
            perm = self._items[self.selected_index][0]
            if perm != "r":  # Read is always locked on
                if perm in self._permissions:
                    self._permissions.discard(perm)
                else:
                    self._permissions.add(perm)
                self._update_display()
        elif key in ("escape", "q"):
            event.stop()
            self.dismiss(self._permissions)


class CLISafeModeScreen(ModalScreen):
    """
    CLI-style safe mode block screen.
    """

    def __init__(self, tool_name: str):
        super().__init__()
        self.tool_name = tool_name

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"⛔ Safe Mode: '{self.tool_name}' blocked", classes="title")
            yield Label("Restart without --safe to enable this tool.")
            yield Label("Press any key to continue...", classes="dim")

    def on_key(self, event) -> None:
        self.dismiss()


class CLISelectScreen(ModalScreen[str | None]):
    """
    CLI-style selection screen with up/down navigation.
    Appears as an overlay at the bottom with a selectable list.
    Returns the selected value or None if cancelled.
    """

    def __init__(
        self,
        title: str,
        items: list[tuple[str, str]],
        current: str = "",
        description: str = ""
    ):
        """
        Initialize the select screen.

        Args:
            title: The title/prompt to display
            items: List of (value, display_text) tuples
            current: Currently selected value (to highlight)
            description: Optional description text
        """
        super().__init__()
        self.title_text = title
        self.items = items
        self.current_value = current
        self.description = description
        self.selected_index = 0

        # Find current index
        for i, (value, _) in enumerate(items):
            if value == current:
                self.selected_index = i
                break

    def compose(self) -> ComposeResult:
        """Compose the selection modal."""
        with Vertical():
            yield Label(f"? {self.title_text}", classes="prompt")

            if self.description:
                yield Label(self.description, classes="description")

            # Build the list display
            list_content = self._render_list()
            yield Static(list_content, id="select-list", classes="select-list")

            yield Label("↑↓ to navigate, Enter to select, Esc to cancel", classes="hint")

    def _render_list(self) -> Text:
        """Render the selectable list with current highlight."""
        result = Text()

        for i, (value, display) in enumerate(self.items):
            is_selected = i == self.selected_index
            is_current = value == self.current_value

            if is_selected:
                # Highlighted row
                result.append(" → ", style="bold cyan")
                if is_current:
                    result.append(f"{display}", style="bold green")
                    result.append(" (current)", style="dim green")
                else:
                    result.append(f"{display}", style="bold white")
            else:
                # Normal row
                result.append("   ", style="dim")
                if is_current:
                    result.append(f"{display}", style="green")
                    result.append(" (current)", style="dim")
                else:
                    result.append(f"{display}", style="white")

            result.append("\n")

        return result

    def _update_display(self) -> None:
        """Update the list display after navigation."""
        list_widget = self.query_one("#select-list", Static)
        list_widget.update(self._render_list())

    def on_key(self, event) -> None:
        """Handle keyboard navigation."""
        key = event.key.lower()

        if key in ("up", "k"):
            event.stop()
            self.selected_index = max(0, self.selected_index - 1)
            self._update_display()
        elif key in ("down", "j"):
            event.stop()
            self.selected_index = min(len(self.items) - 1, self.selected_index + 1)
            self._update_display()
        elif key in ("enter", "return"):
            event.stop()
            if self.items:
                self.dismiss(self.items[self.selected_index][0])
            else:
                self.dismiss(None)
        elif key in ("escape", "q"):
            event.stop()
            self.dismiss(None)


class TaskEditScreen(ModalScreen[str | None]):
    """
    In-app task editor screen with a TextArea.
    Returns the edited content on save, or None on cancel.
    Styled via theme CSS (same bottom-panel pattern as other modals).
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, content: str):
        super().__init__()
        self.title_text = title
        self.initial_content = content

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Editing: {self.title_text}", classes="prompt")
            yield TextArea(self.initial_content, id="task-editor", language="markdown")
            yield Label("Ctrl+S save • Esc cancel", classes="hint")

    def on_mount(self) -> None:
        editor = self.query_one("#task-editor", TextArea)
        editor.focus()

    def action_save(self) -> None:
        editor = self.query_one("#task-editor", TextArea)
        self.dismiss(editor.text)

    def action_cancel(self) -> None:
        self.dismiss(None)
