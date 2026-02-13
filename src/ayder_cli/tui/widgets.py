"""TUI widget classes: ChatView, ToolPanel, ActivityBar, AutoCompleteInput, CLIInputBar, StatusBar."""

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll, Container
from textual.widgets import Static, Input, Label, TextArea
from textual.reactive import reactive
from textual.message import Message
from textual.suggester import SuggestFromList
from rich.text import Text
from rich.markdown import Markdown
from rich.spinner import Spinner
from pathlib import Path

from ayder_cli.tui.types import MessageType


class ChatView(VerticalScroll):
    """
    CLI-style chat display.
    Simple text output with prefixes instead of panels.
    """

    messages: reactive[list] = reactive(list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._message_widgets: list[Static] = []

    def _create_text(self, content: str, msg_type: MessageType, metadata: dict = None) -> Text:
        """Create styled text for a message."""
        if msg_type == MessageType.USER:
            text = Text()
            text.append("> ", style="bold cyan")
            text.append(content, style="cyan")
            return text

        elif msg_type == MessageType.ASSISTANT:
            return None

        elif msg_type == MessageType.THINKING:
            text = Text()
            text.append("  ... ", style="dim italic")
            # Truncate long thinking blocks
            lines = content.strip().splitlines()
            if len(lines) > 4:
                preview = "\n".join(lines[:4]) + f"\n    ({len(lines) - 4} more lines)"
            else:
                preview = content.strip()
            text.append(preview, style="dim italic")
            return text

        elif msg_type == MessageType.TOOL_CALL:
            tool_name = metadata.get("tool_name", "unknown") if metadata else "unknown"
            text = Text()
            text.append("  → ", style="dim")
            text.append(f"{tool_name}", style="bold yellow")
            if content:
                text.append(f"({content})", style="yellow")
            return text

        elif msg_type == MessageType.TOOL_RESULT:
            text = Text()
            text.append("  ✓ ", style="bold green")
            result = content
            if len(result) > 200:
                result = result[:200] + "..."
            text.append(result, style="dim")
            return text

        else:
            text = Text()
            text.append("# ", style="dim")
            text.append(content, style="dim italic")
            return text

    def add_message(self, content: str, msg_type: MessageType, metadata: dict = None) -> None:
        """Add a message to the chat view."""
        self.messages.append({"content": content, "type": msg_type, "metadata": metadata})

        if msg_type == MessageType.ASSISTANT:
            content = content.strip()

            content_widget = Static(
                Markdown(content), classes=f"message {msg_type.value}"
            )
            self._message_widgets.append(content_widget)
            self.mount(content_widget)
        else:
            text = self._create_text(content, msg_type, metadata)
            if text:
                msg_widget = Static(text, classes=f"message {msg_type.value}")
                self._message_widgets.append(msg_widget)
                self.mount(msg_widget)

        self.scroll_end(animate=False)

    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self.add_message(content, MessageType.USER)

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message."""
        self.add_message(content, MessageType.ASSISTANT)

    def add_thinking_message(self, content: str) -> None:
        """Add a thinking/reasoning message."""
        self.add_message(content, MessageType.THINKING)

    def add_tool_call(self, tool_name: str, arguments: str) -> None:
        """Add a tool call message."""
        self.add_message(arguments, MessageType.TOOL_CALL, {"tool_name": tool_name})

    def add_tool_result(self, result: str) -> None:
        """Add a tool result message."""
        self.add_message(result, MessageType.TOOL_RESULT)

    def add_system_message(self, content: str) -> None:
        """Add a system message."""
        self.add_message(content, MessageType.SYSTEM)

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        for widget in self._message_widgets:
            widget.remove()
        self._message_widgets.clear()
        self.messages.clear()


class ToolPanel(Container):
    """
    A dedicated panel for displaying running/completed tools.
    Toggled with Ctrl+O. Content is added silently; visibility is user-controlled.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # tool_call_id -> (widget, spinner, tool_name, args_str, is_done)
        self._tools: dict[str, tuple[Static, Spinner | None, str, str, bool]] = {}
        self._user_visible = False

    def compose(self) -> ComposeResult:
        """Compose starts empty."""
        return
        yield

    def on_mount(self) -> None:
        """Start hidden - user toggles with Ctrl+O."""
        self.display = False

    def toggle(self) -> bool:
        """Toggle panel visibility. Returns new visibility state."""
        self._user_visible = not self._user_visible
        self.display = self._user_visible
        return self._user_visible

    def add_tool(self, tool_call_id: str, tool_name: str, arguments: dict) -> None:
        """Add a new running tool to the panel."""
        args_str = self._format_preview(str(arguments), max_len=80)

        tool_text = Text()
        tool_text.append(f"{tool_name}", style="yellow")
        tool_text.append(f" {args_str}", style="dim")

        spinner = Spinner("aesthetic", text=tool_text, style="bold yellow")
        widget = Static(spinner, classes="tool-item running")
        self._tools[tool_call_id] = (widget, spinner, tool_name, args_str, False)
        self.mount(widget)

    def complete_tool(self, tool_call_id: str, result: str = "") -> None:
        """Mark a tool as completed."""
        if tool_call_id not in self._tools:
            return

        widget, _, tool_name, args_str, _ = self._tools[tool_call_id]
        result_preview = self._format_preview(str(result), max_len=80)

        text = Text()
        text.append("✓ ", style="bold green")
        text.append(f"{tool_name}", style="green")
        if result_preview:
            text.append(f" → {result_preview}", style="dim")

        widget.update(text)
        widget.remove_class("running")
        widget.add_class("completed")
        self._tools[tool_call_id] = (widget, None, tool_name, args_str, True)

    def update_spinners(self) -> None:
        """Re-render running tool spinners (they auto-advance based on time)."""
        for tool_id, (widget, spinner, tool_name, args_str, is_done) in self._tools.items():
            if not is_done and spinner is not None:
                widget.update(spinner)

    def _format_preview(self, text: str, max_len: int = 80) -> str:
        """Format text to be a short preview."""
        preview = text.replace("\n", " ").replace("  ", " ").strip()
        if len(preview) > max_len:
            preview = preview[:max_len - 3] + "..."
        return preview

    def clear_completed(self) -> None:
        """Remove all completed tools (does not change visibility)."""
        to_remove = [tid for tid, (_, _, _, _, is_done) in self._tools.items() if is_done]
        for tool_id in to_remove:
            widget, _, _, _, _ = self._tools[tool_id]
            widget.remove()
            del self._tools[tool_id]

    def clear_all(self) -> None:
        """Clear all tools from panel (does not change visibility)."""
        for widget, _, _, _, _ in self._tools.values():
            widget.remove()
        self._tools.clear()


class ActivityBar(Horizontal):
    """
    Static status bar above the input showing activity state.
    Displays a spinner for 'Thinking...' and 'Tools Working...' states.
    """

    can_focus = False
    can_focus_children = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._thinking = False
        self._tools_working = False
        self._thinking_spinner = Spinner("dots2", style="bold yellow")
        self._tools_spinner = Spinner("aesthetic", style="bold yellow")
        self._widget: Static | None = None

    def compose(self) -> ComposeResult:
        self._widget = Static("", id="activity-text")
        yield self._widget

    def set_thinking(self, active: bool) -> None:
        """Show or hide the Thinking indicator."""
        self._thinking = active
        self._refresh_display()

    def set_tools_working(self, active: bool) -> None:
        """Show or hide the Tools Working indicator."""
        self._tools_working = active
        self._refresh_display()

    def update_spinners(self) -> None:
        """Re-render spinners (call on a timer)."""
        if not self._thinking and not self._tools_working:
            return
        # Build a combined renderable
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Update the displayed text based on current state."""
        if not self._widget:
            return

        if self._thinking and self._tools_working:
            self._widget.update(self._thinking_spinner)
            # Show both — use thinking spinner with combined text
            self._thinking_spinner.text = Text.assemble(
                ("Thinking... ", "bold yellow"),
                ("| ", "dim"),
                ("Tools Working...", "bold yellow"),
            )
            self._widget.update(self._thinking_spinner)
        elif self._thinking:
            self._thinking_spinner.text = "Thinking..."
            self._widget.update(self._thinking_spinner)
        elif self._tools_working:
            self._tools_spinner.text = "Tools Working..."
            self._widget.update(self._tools_spinner)
        else:
            self._widget.update("")

    def clear(self) -> None:
        """Reset all activity state."""
        self._thinking = False
        self._tools_working = False
        if self._widget:
            self._widget.update("")


class AutoCompleteInput(Input):
    """
    Input widget with slash command auto-completion.
    Shows inline suggestions when user types '/'.
    Tab accepts the current suggestion.
    """

    def __init__(self, commands: list[str], **kwargs):
        self._commands = commands
        suggester = SuggestFromList(commands, case_sensitive=False)
        super().__init__(suggester=suggester, **kwargs)

    def on_key(self, event) -> None:
        """Handle tab to accept suggestion."""
        if event.key == "tab" and self.value.startswith("/"):
            event.prevent_default()
            event.stop()
            suggestion = self._suggestion
            if suggestion:
                self.value = suggestion
                self.cursor_position = len(self.value)


class _SubmitTextArea(TextArea):
    """TextArea where Enter submits and Shift+Enter inserts a newline.

    Also supports Tab completion for slash commands.
    """

    class Submitted(Message):
        """Posted when the user presses Enter to submit."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, commands: list[str] | None = None, **kwargs):
        super().__init__(soft_wrap=True, show_line_numbers=False, **kwargs)
        self._commands = commands or []

    def _on_key(self, event) -> None:
        if event.key == "enter":
            # Plain Enter → submit (Shift+Enter comes as "shift+enter")
            event.prevent_default()
            event.stop()
            value = self.text.strip()
            if value:
                self.post_message(self.Submitted(value))
                self.clear()
            return

        if event.key == "tab" and self.text.startswith("/"):
            event.prevent_default()
            event.stop()
            current = self.text.strip()
            matches = [c for c in self._commands if c.startswith(current)]
            if len(matches) == 1:
                self.clear()
                self.insert(matches[0])
            return


class CLIInputBar(Horizontal):
    """
    CLI-style input bar with word-wrapping TextArea.
    Enter submits, Shift+Enter inserts a newline.
    """

    class Submitted(Message):
        """Message sent when input is submitted."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, commands: list[str], **kwargs):
        super().__init__(**kwargs)
        self.commands = commands
        self._input: _SubmitTextArea | None = None
        self._history_file = Path.home() / ".ayder_chat_history"
        self._history: list[str] = self._load_history()
        self._history_index: int = len(self._history)
        self._current_input: str = ""

    def _load_history(self) -> list[str]:
        """Load command history from file (same file as CLI)."""
        if self._history_file.exists():
            try:
                content = self._history_file.read_text(encoding="utf-8")
                lines = [line.strip() for line in content.split("\n") if line.strip()]
                return lines[-1000:]
            except Exception:
                pass
        return []

    def _save_to_history(self, command: str) -> None:
        """Append command to history file."""
        try:
            with open(self._history_file, "a", encoding="utf-8") as f:
                f.write(command + "\n")
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        """Compose the input bar."""
        yield Static(">", classes="prompt")
        self._input = _SubmitTextArea(
            commands=self.commands,
            id="chat-input",
        )
        yield self._input

    def on_mount(self) -> None:
        """Focus input on mount."""
        self._input = self.query_one("#chat-input", _SubmitTextArea)
        self._input.focus()

    def on__submit_text_area_submitted(self, event: _SubmitTextArea.Submitted) -> None:
        """Handle Enter (submit) from the TextArea."""
        event.prevent_default()
        event.stop()
        value = event.value
        if value:
            if not self._history or self._history[-1] != value:
                self._history.append(value)
                self._save_to_history(value)
            self._history_index = len(self._history)
            self._current_input = ""
            self.app.post_message(self.Submitted(value))

    def on_key(self, event) -> None:
        """Handle history navigation."""
        if event.key == "up":
            event.prevent_default()
            event.stop()
            self._history_navigate(-1)
        elif event.key == "down":
            event.prevent_default()
            event.stop()
            self._history_navigate(1)

    def focus_input(self) -> None:
        """Focus the input field."""
        if self._input:
            self._input.focus()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable input (no-op, input always stays enabled)."""
        pass

    def _history_navigate(self, direction: int) -> None:
        """Navigate through command history.

        Args:
            direction: -1 for up (older), 1 for down (newer)
        """
        if not self._history or not self._input:
            return

        if self._history_index == len(self._history):
            self._current_input = self._input.text

        new_index = self._history_index + direction

        if new_index < 0:
            new_index = 0
        if new_index > len(self._history):
            new_index = len(self._history)

        self._history_index = new_index

        if self._history_index == len(self._history):
            text = self._current_input
        else:
            text = self._history[self._history_index]

        self._input.clear()
        self._input.insert(text)


class StatusBar(Horizontal):
    """
    CLI-style status bar showing context info.
    """

    def __init__(self, model: str = "default", permissions: set = None, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.token_count = 0
        self.active_files: list[str] = []
        self._permissions = permissions or {"r"}

    def compose(self) -> ComposeResult:
        mode_str = "".join(sorted(self._permissions))
        yield Label(f"model: {self.model}", id="model-label")
        yield Label(f" | mode: {mode_str}", id="mode-label")
        yield Label(f" | tokens: 0", id="token-label")
        yield Label(f" | iter: 0", id="iter-label")
        yield Label(f" | files: 0", id="files-label")
        yield Static(classes="spacer")
        yield Label("^C:cancel ^L:clear ^O:tools ^Q:quit", classes="key-hint")

    def set_model(self, model: str) -> None:
        """Update the displayed model."""
        self.model = model
        label = self.query_one("#model-label", Label)
        label.update(f"model: {model}")

    def update_token_usage(self, count: int) -> None:
        """Update token count display."""
        self.token_count = count
        label = self.query_one("#token-label", Label)
        label.update(f" | tokens: {count:,}")

    def update_iterations(self, current: int, maximum: int) -> None:
        """Update iteration counter display."""
        label = self.query_one("#iter-label", Label)
        label.update(f" | iter: {current}/{maximum}")

    def update_files(self, files: list[str]) -> None:
        """Update active files count."""
        self.active_files = files
        label = self.query_one("#files-label", Label)
        label.update(f" | files: {len(files)}")

    def update_permissions(self, permissions: set) -> None:
        """Update permission mode display."""
        self._permissions = permissions
        mode_str = "".join(sorted(permissions))
        label = self.query_one("#mode-label", Label)
        label.update(f" | mode: {mode_str}")
