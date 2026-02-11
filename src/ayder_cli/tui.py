"""
CLI-style TUI (Terminal User Interface) for ayder-cli.

Provides a clean, terminal-like interface:
- Simple text output with prefixes (> for user, < for assistant)
- Minimal borders and chrome
- Slash command auto-completion
- Status bar with context info
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll, Vertical
from textual.widgets import Static, Input, Button, Label
from textual.reactive import reactive
from textual.message import Message
from textual.worker import Worker, get_current_worker
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.timer import Timer
from textual import on
from rich.text import Text
from rich.markdown import Markdown
from rich.spinner import Spinner
from enum import Enum
from pathlib import Path
import asyncio
import json

from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.core.context import ProjectContext
from ayder_cli.client import call_llm_async
from ayder_cli.core.config import load_config
from ayder_cli.services.llm import OpenAIProvider
from ayder_cli.commands.registry import get_registry
from ayder_cli.banner import create_tui_banner
from ayder_cli.tui_theme_manager import get_theme_css


class MessageType(Enum):
    """Types of chat messages."""
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"



class CLIConfirmScreen(ModalScreen[bool]):
    """
    CLI-style confirmation screen.
    Appears as an overlay at the bottom, not a centered popup.
    """

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

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Vertical():
            yield Label(f"? {self.title_text}", classes="prompt")
            yield Label(self.description)

            if self.diff_content:
                diff_text = self._render_diff()
                yield Static(diff_text, classes="diff-container")

            with Horizontal(classes="buttons"):
                yield Button("[Y]es", variant="success", id="confirm-btn")
                yield Button("[N]o", variant="error", id="cancel-btn")

    def _render_diff(self) -> Text:
        """Render diff content with syntax highlighting."""
        lines = self.diff_content.split('\n')
        result = Text()

        for line in lines:
            if line.startswith('@@'):
                result.append(line + "\n", style="cyan")
            elif line.startswith('-') and not line.startswith('---'):
                result.append(line + "\n", style="red")
            elif line.startswith('+') and not line.startswith('+++'):
                result.append(line + "\n", style="green")
            else:
                result.append(line + "\n", style="dim")

        return result

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        key = event.key.lower()
        if key in ("escape", "n", "q"):
            self.dismiss(False)
        elif key in ("enter", "y"):
            self.dismiss(True)


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


class ChatView(VerticalScroll):
    """
    CLI-style chat display.
    Simple text output with prefixes instead of panels.
    """

    messages: reactive[list] = reactive(list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._message_widgets: list[Static] = []
        self._thinking_widget: Static | None = None
        self._thinking_spinner: Spinner | None = None

    def _create_text(self, content: str, msg_type: MessageType, metadata: dict = None) -> Text:
        """Create styled text for a message."""
        if msg_type == MessageType.USER:
            text = Text()
            text.append("> ", style="bold cyan")
            text.append(content, style="cyan")
            return text

        elif msg_type == MessageType.ASSISTANT:
            return None

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

            prefix = Text()
            prefix.append("< ", style="bold green")
            msg_widget = Static(prefix, classes=f"message {msg_type.value}")
            self._message_widgets.append(msg_widget)
            self.mount(msg_widget)

            content_widget = Static(
                Markdown(content), classes=f"message {msg_type.value}-content"
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

    def add_tool_call(self, tool_name: str, arguments: str) -> None:
        """Add a tool call message."""
        self.add_message(arguments, MessageType.TOOL_CALL, {"tool_name": tool_name})

    def add_tool_result(self, result: str) -> None:
        """Add a tool result message."""
        self.add_message(result, MessageType.TOOL_RESULT)

    def add_system_message(self, content: str) -> None:
        """Add a system message."""
        self.add_message(content, MessageType.SYSTEM)

    def show_thinking(self) -> None:
        """Show a thinking/loading indicator with a Rich spinner."""
        if self._thinking_widget is None:
            self._thinking_spinner = Spinner(
                "dots2", text="Thinking...", style="bold yellow"
            )
            self._thinking_widget = Static(
                self._thinking_spinner, classes="thinking-message"
            )
            self._message_widgets.append(self._thinking_widget)
            self.mount(self._thinking_widget)
            self.scroll_end(animate=False)

    def _update_thinking(self) -> None:
        """Re-render the spinner (it auto-advances based on time)."""
        if self._thinking_widget is not None and self._thinking_spinner is not None:
            self._thinking_widget.update(self._thinking_spinner)

    def hide_thinking(self) -> None:
        """Hide the thinking/loading indicator."""
        if self._thinking_widget is not None:
            self._thinking_widget.remove()
            if self._thinking_widget in self._message_widgets:
                self._message_widgets.remove(self._thinking_widget)
            self._thinking_widget = None
            self._thinking_spinner = None

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        for widget in self._message_widgets:
            widget.remove()
        self._message_widgets.clear()
        self._thinking_widget = None
        self.messages.clear()


class ToolPanel(Container):
    """
    A dedicated panel for displaying running/completed tools.
    Shows at the bottom of the chat when tools are active.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # tool_call_id -> (widget, spinner, tool_name, args_str, is_done)
        self._tools: dict[str, tuple[Static, Spinner | None, str, str, bool]] = {}

    def compose(self) -> ComposeResult:
        """Compose starts empty."""
        return
        yield

    def on_mount(self) -> None:
        """Start hidden - only show when tools are active."""
        self.display = False

    def add_tool(self, tool_call_id: str, tool_name: str, arguments: dict) -> None:
        """Add a new running tool to the panel."""
        self.display = True
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
        """Remove all completed tools."""
        to_remove = [tid for tid, (_, _, _, _, is_done) in self._tools.items() if is_done]
        for tool_id in to_remove:
            widget, _, _, _, _ = self._tools[tool_id]
            widget.remove()
            del self._tools[tool_id]
        if not self._tools:
            self.display = False

    def clear_all(self) -> None:
        """Clear all tools from panel."""
        for widget, _, _, _, _ in self._tools.values():
            widget.remove()
        self._tools.clear()
        self.display = False


class AutoCompleteInput(Input):
    """
    Input widget with slash command auto-completion.
    Shows suggestions when user types '/'.
    """

    def __init__(self, commands: list[str], **kwargs):
        self._commands = commands
        suggester = SuggestFromList(commands, case_sensitive=False)
        super().__init__(suggester=suggester, **kwargs)

    def _show_suggestions(self) -> None:
        """Override to only show suggestions for commands (starting with /)."""
        if self.value.startswith("/"):
            super()._show_suggestions()
        else:
            popup = getattr(self, "_suggestion_popup", None)
            if popup is not None:
                popup.display = False

    def on_key(self, event) -> None:
        """Handle key events for completion."""
        if event.key == "tab" and self.value.startswith("/"):
            event.prevent_default()
            event.stop()
            self._accept_suggestion()
        elif event.key == "enter":
            popup = getattr(self, "_suggestion_popup", None)
            if popup is not None:
                popup.display = False

    def _accept_suggestion(self) -> None:
        """Accept the current suggestion if available."""
        if not self.value.startswith("/"):
            return

        suggestion = getattr(self, "_suggestion", None)
        if suggestion:
            self.value = suggestion
            popup = getattr(self, "_suggestion_popup", None)
            if popup is not None:
                popup.display = False
            self.cursor_position = len(self.value)
        else:
            self._show_suggestions()
            suggestion = getattr(self, "_suggestion", None)
            if suggestion:
                self.value = suggestion
                popup = getattr(self, "_suggestion_popup", None)
                if popup is not None:
                    popup.display = False
                self.cursor_position = len(self.value)


class CLIInputBar(Horizontal):
    """
    CLI-style input bar with prompt prefix and auto-completion.
    """

    class Submitted(Message):
        """Message sent when input is submitted."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, commands: list[str], **kwargs):
        super().__init__(**kwargs)
        self.commands = commands
        self._input = None
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
        self._input = AutoCompleteInput(
            self.commands,
            placeholder="Type your message or /command...",
            id="chat-input"
        )
        yield self._input

    def on_mount(self) -> None:
        """Focus input on mount."""
        self._input = self.query_one("#chat-input", AutoCompleteInput)
        self._input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self._submit()

    def _submit(self) -> None:
        """Submit the current input value."""
        if self._input:
            value = self._input.value.strip()
            if value:
                if not self._history or self._history[-1] != value:
                    self._history.append(value)
                    self._save_to_history(value)
                self._history_index = len(self._history)
                self._current_input = ""
                popup = getattr(self._input, "_suggestion_popup", None)
                if popup is not None:
                    popup.display = False
                self.app.post_message(self.Submitted(value))
                self._input.value = ""

    def focus_input(self) -> None:
        """Focus the input field."""
        if self._input:
            self._input.focus()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable input."""
        if self._input:
            self._input.disabled = not enabled

    def on_key(self, event) -> None:
        """Handle key events for history navigation and tab completion."""
        if event.key == "up":
            event.prevent_default()
            event.stop()
            self._history_navigate(-1)
        elif event.key == "down":
            event.prevent_default()
            event.stop()
            self._history_navigate(1)
        elif event.key == "tab":
            if self._input and self._input.value.startswith("/"):
                event.prevent_default()
                event.stop()
                self._input._accept_suggestion()
            else:
                event.prevent_default()
                event.stop()

    def _history_navigate(self, direction: int) -> None:
        """Navigate through command history.

        Args:
            direction: -1 for up (older), 1 for down (newer)
        """
        if not self._history:
            return

        if self._history_index == len(self._history):
            self._current_input = self._input.value

        new_index = self._history_index + direction

        if new_index < 0:
            new_index = 0
        if new_index > len(self._history):
            new_index = len(self._history)

        self._history_index = new_index

        if self._history_index == len(self._history):
            self._input.value = self._current_input
        else:
            self._input.value = self._history[self._history_index]

        self._input.cursor_position = len(self._input.value)


class StatusBar(Horizontal):
    """
    CLI-style status bar showing context info.
    """

    def __init__(self, model: str = "default", **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.token_count = 0
        self.active_files: list[str] = []

    def compose(self) -> ComposeResult:
        yield Label(f"model: {self.model}", id="model-label")
        yield Label(f" | tokens: 0", id="token-label")
        yield Label(f" | files: 0", id="files-label")
        yield Static(classes="spacer")
        yield Label("^C:copy ^X:cancel ^L:clear ^Q:quit", classes="key-hint")

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

    def update_files(self, files: list[str]) -> None:
        """Update active files count."""
        self.active_files = files
        label = self.query_one("#files-label", Label)
        label.update(f" | files: {len(files)}")


class AyderApp(App):
    """
    Main CLI-style application for ayder-cli.

    Layout:
    - Banner at top (compact, not full screen)
    - Main area: Chat view
    - Input bar: CLI prompt style at bottom
    - Status bar: Context info at very bottom
    """

    CSS = get_theme_css()

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+x", "cancel", "Cancel"),
        ("ctrl+c", "copy_selection", "Copy"),
        ("ctrl+l", "clear", "Clear Chat"),
        ("ctrl+d", "exit_prompt", "Exit"),
    ]

    def __init__(self, model: str = "default", safe_mode: bool = False, **kwargs):
        """
        Initialize the TUI app.

        Args:
            model: The LLM model name to use
            safe_mode: Whether to enable safe mode
        """
        super().__init__(**kwargs)
        self.model = model
        self.safe_mode = safe_mode

        self._ctrl_d_pressed = False
        self._ctrl_d_timer = None

        self._pending_messages: list[str] = []
        self._is_processing = False

        self.config = load_config()

        if isinstance(self.config, dict):
            base_url = self.config.get("base_url", "http://localhost:11434/v1")
            api_key = self.config.get("api_key", "ollama")
            actual_model = self.config.get("model", model)
        else:
            base_url = self.config.base_url
            api_key = self.config.api_key
            actual_model = self.config.model

        self.model = actual_model if actual_model != "default" else model
        self.llm = OpenAIProvider(base_url=base_url, api_key=api_key)

        self.messages: list[dict] = []

        registry = get_registry()
        self.commands = registry.get_command_names()

        self.registry = create_default_registry(ProjectContext("."))
        self._setup_registry_callbacks()
        self._setup_registry_middleware()

        self._thinking_timer: Timer | None = None
        self._tools_timer: Timer | None = None
        self._total_tokens: int = 0

    def _animate_running_tools(self) -> None:
        """Animate spinner for running tools."""
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        tool_panel.update_spinners()

    def _setup_registry_callbacks(self) -> None:
        """Setup callbacks for tool registry."""
        def on_tool_start(tool_name: str, arguments: dict):
            chat_view = self.query_one("#chat-view", ChatView)
            chat_view.add_tool_call(tool_name, str(arguments))

        def on_tool_complete(result):
            chat_view = self.query_one("#chat-view", ChatView)
            if result.result:
                chat_view.add_tool_result(result.result)

        self.registry.add_pre_execute_callback(on_tool_start)
        self.registry.add_post_execute_callback(on_tool_complete)

    def _setup_registry_middleware(self) -> None:
        """Setup middleware for safe mode."""
        def safe_mode_check(tool_name: str, arguments: dict):
            if self._is_tool_blocked_in_safe_mode(tool_name):
                raise PermissionError(f"Tool '{tool_name}' blocked in safe mode")

        if self.safe_mode:
            self.registry.add_middleware(safe_mode_check)

    def _is_tool_blocked_in_safe_mode(self, tool_name: str) -> bool:
        """Check if a tool should be blocked in safe mode."""
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

        tool_def = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
        return tool_def.safe_mode_blocked if tool_def else False

    def compose(self) -> ComposeResult:
        """Compose the UI layout - terminal style with scrolling content."""
        yield ChatView(id="chat-view")
        yield ToolPanel(id="tool-panel")
        yield CLIInputBar(commands=self.commands, id="input-bar")
        yield StatusBar(model=self.model, id="status-bar")

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = f"ayder - {self.model}"

        # Show the banner as scrollable content in the chat view
        chat_view = self.query_one("#chat-view", ChatView)
        banner = create_tui_banner(self.model)
        chat_view.mount(Static(banner, classes="banner-content"))

    @on(CLIInputBar.Submitted)
    def handle_input_submitted(self, event: CLIInputBar.Submitted) -> None:
        """Handle user input submission."""
        user_input = event.value

        if user_input.startswith("/"):
            self._handle_command(user_input)
            return

        self._pending_messages.append(user_input)

        if not self._is_processing:
            self._process_next_message()

    def _process_next_message(self) -> None:
        """Process the next pending message."""
        if not self._pending_messages:
            self._is_processing = False
            return

        self._is_processing = True
        user_input = self._pending_messages.pop(0)

        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_user_message(user_input)

        self.messages.append({"role": "user", "content": user_input})

        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)

        self.run_worker(self._process_llm_response(), exclusive=True)

    def _animate_thinking(self) -> None:
        """Animate the thinking indicator."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view._update_thinking()

    def _handle_command(self, cmd: str) -> None:
        """Handle slash commands - display output in TUI."""
        from ayder_cli.core.context import SessionContext

        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_user_message(cmd)

        parts = cmd.split(None, 1)
        cmd_name = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""

        try:
            if cmd_name == "/help":
                self._show_help(chat_view)
            elif cmd_name == "/model":
                self._handle_model_command(cmd_args, chat_view)
            elif cmd_name == "/tasks":
                self._handle_tasks_command(chat_view)
            elif cmd_name == "/tools":
                self._handle_tools_command(chat_view)
            elif cmd_name == "/verbose":
                self._handle_verbose_command(chat_view)
            elif cmd_name == "/compact":
                self._handle_compact_command(chat_view)
            elif cmd_name == "/plan":
                self._handle_plan_command(cmd_args, chat_view)
            elif cmd_name == "/ask":
                self._handle_ask_command(cmd_args, chat_view)
            elif cmd_name == "/implement":
                self._handle_implement_command(cmd_args, chat_view)
            elif cmd_name == "/implement-all":
                self._handle_implement_all_command(chat_view)
            elif cmd_name == "/task-edit":
                self._handle_task_edit_command(cmd_args, chat_view)
            elif cmd_name == "/archive-completed-tasks":
                self._handle_archive_command(chat_view)
            else:
                chat_view.add_system_message(f"Unknown command: {cmd_name}. Type /help for available commands.")
        except Exception as e:
            chat_view.add_system_message(f"Command error: {type(e).__name__}: {e}")

    def _show_help(self, chat_view: ChatView) -> None:
        """Show help message in TUI."""
        registry = get_registry()
        commands = registry.list_commands()
        commands.sort(key=lambda c: c.name)

        help_text = "[bold]Available Commands:[/bold]\n"
        for cmd in commands:
            help_text += f"  [cyan]{cmd.name:<20}[/cyan] {cmd.description}\n"

        chat_view.add_assistant_message(help_text)

    def _do_clear(self, chat_view: ChatView) -> None:
        """Clear conversation history."""
        if self.messages:
            if self.messages[0].get("role") == "system":
                system_msg = self.messages[0]
                self.messages.clear()
                self.messages.append(system_msg)
            else:
                self.messages.clear()

        chat_view.clear_messages()
        chat_view.add_system_message("Conversation history cleared.")

    def _handle_model_command(self, args: str, chat_view: ChatView) -> None:
        """Handle /model command."""
        if not args.strip():
            try:
                models = self.llm.list_models()
                if not models:
                    chat_view.add_system_message(f"Current model: {self.model}")
                    return

                # Show interactive select screen
                items = [(m, m) for m in sorted(models)]

                def on_model_selected(selected: str | None) -> None:
                    if selected:
                        self.model = selected
                        status_bar = self.query_one("#status-bar", StatusBar)
                        status_bar.set_model(selected)
                        chat_view.add_system_message(f"Switched to model: {selected}")

                self.push_screen(
                    CLISelectScreen(
                        title="Select model",
                        items=items,
                        current=self.model,
                        description=f"Currently using: {self.model}"
                    ),
                    on_model_selected
                )
            except Exception as e:
                chat_view.add_system_message(f"Error listing models: {e}")
        else:
            new_model = args.strip()
            self.model = new_model
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.set_model(new_model)
            chat_view.add_system_message(f"Switched to model: {new_model}")

    def _handle_tasks_command(self, chat_view: ChatView) -> None:
        """Handle /tasks command."""
        from ayder_cli.tasks import _get_tasks_dir, _get_task_path_by_id, _parse_title, _extract_id

        try:
            project_ctx = ProjectContext(".")
            tasks_dir = _get_tasks_dir(project_ctx)

            if not tasks_dir.exists():
                chat_view.add_system_message("No tasks directory found. Create tasks first with /plan.")
                return

            # Build list of tasks
            items = []
            task_paths = {}  # Map display text to task path

            for task_file in sorted(tasks_dir.glob("*.md")):
                task_id = _extract_id(task_file.name)
                if task_id is None:
                    continue

                title = _parse_title(task_file)
                content = task_file.read_text(encoding="utf-8")

                # Determine status
                status = "pending"
                if "- **status:** done" in content.lower():
                    status = "done"
                elif "- **status:** in_progress" in content.lower():
                    status = "in_progress"

                # Format display with status indicator
                status_icon = "✓" if status == "done" else "○" if status == "pending" else "◐"
                display = f"TASK-{task_id:03d}: {title} [{status_icon}]"

                items.append((str(task_id), display))
                task_paths[str(task_id)] = task_file

            if not items:
                chat_view.add_system_message("No tasks found. Create tasks first with /plan.")
                return

            def on_task_selected(selected: str | None) -> None:
                if selected:
                    task_id = int(selected)
                    task_path = task_paths.get(selected)
                    if task_path:
                        title = _parse_title(task_path)
                        self._run_implement_task(task_id, title, chat_view)

            self.push_screen(
                CLISelectScreen(
                    title="Select task to implement",
                    items=items,
                    description=f"{len(items)} task(s) found • Enter to implement • Esc to cancel"
                ),
                on_task_selected
            )

        except Exception as e:
            chat_view.add_system_message(f"Error listing tasks: {e}")

    def _handle_tools_command(self, chat_view: ChatView) -> None:
        """Handle /tools command - list all available tools."""
        from ayder_cli.tools.schemas import tools_schema

        try:
            if not tools_schema:
                chat_view.add_system_message("No tools available.")
                return

            tools_text = "[bold]Available Tools:[/bold]\n\n"
            for tool in tools_schema:
                func = tool.get('function', {})
                name = func.get('name', 'Unknown')
                desc = func.get('description', 'No description provided.')
                # Truncate long descriptions
                if len(desc) > 100:
                    desc = desc[:100] + "..."
                tools_text += f"  [cyan]{name}[/cyan]: {desc}\n"

            chat_view.add_assistant_message(tools_text)
        except Exception as e:
            chat_view.add_system_message(f"Error listing tools: {e}")

    def _run_implement_task(self, task_id: int, title: str, chat_view) -> None:
        """Run a single task implementation."""
        from ayder_cli.tasks import _get_task_path_by_id
        from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE

        project_ctx = ProjectContext(".")
        task_path = _get_task_path_by_id(project_ctx, task_id)

        if task_path is None:
            chat_view.add_system_message(f"Task TASK-{task_id:03d} not found.")
            return

        rel_path = project_ctx.to_relative(task_path)
        command = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
        self.messages.append({"role": "user", "content": command})
        chat_view.add_system_message(f"Running TASK-{task_id:03d}: {title}")

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(False)
        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
        self.run_worker(self._process_llm_response(), exclusive=True)

    def _handle_verbose_command(self, chat_view: ChatView) -> None:
        """Handle /verbose command."""
        current = getattr(self, '_verbose_mode', False)
        self._verbose_mode = not current
        status = "ON" if self._verbose_mode else "OFF"
        chat_view.add_system_message(f"Verbose mode: {status}")

    def _handle_compact_command(self, chat_view: ChatView) -> None:
        """Handle /compact command."""
        from ayder_cli.prompts import COMPACT_PROMPT_TEMPLATE

        if len(self.messages) <= 1:
            chat_view.add_system_message("No conversation to compact.")
            return

        conversation_text = ""
        for msg in self.messages:
            if msg.get("role") in ("user", "assistant"):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                conversation_text += f"[{role}] {content}\n\n"

        system_msg = None
        if self.messages and self.messages[0].get("role") == "system":
            system_msg = self.messages[0]
        self.messages.clear()
        if system_msg:
            self.messages.append(system_msg)

        compact_prompt = COMPACT_PROMPT_TEMPLATE.format(conversation_text=conversation_text)
        self.messages.append({"role": "user", "content": compact_prompt})
        chat_view.add_system_message("Compacting: summarize → save → clear → load")

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(False)
        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
        self.run_worker(self._process_llm_response(), exclusive=True)

    def _handle_plan_command(self, args: str, chat_view: ChatView) -> None:
        """Handle /plan command."""
        from ayder_cli.prompts import PLANNING_PROMPT_TEMPLATE

        if not args.strip():
            chat_view.add_system_message("Usage: /plan <task description>\nExample: /plan Implement user authentication")
            return

        planning_prompt = PLANNING_PROMPT_TEMPLATE.format(task_description=args.strip())
        self.messages.append({"role": "user", "content": planning_prompt})
        chat_view.add_system_message(f"Planning: {args.strip()[:50]}...")

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(False)
        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
        self.run_worker(self._process_llm_response(), exclusive=True)

    def _handle_ask_command(self, args: str, chat_view: ChatView) -> None:
        """Handle /ask command."""
        if not args.strip():
            chat_view.add_system_message("Usage: /ask <question>\nExample: /ask What is Python?")
            return

        self._no_tools_for_next = True
        self.messages.append({"role": "user", "content": args.strip()})
        chat_view.add_user_message(args.strip())

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(False)
        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
        self.run_worker(self._process_llm_response(no_tools=True), exclusive=True)

    def _handle_implement_command(self, args: str, chat_view: ChatView) -> None:
        """Handle /implement command."""
        from ayder_cli.tasks import _get_tasks_dir, _get_task_path_by_id, _parse_title, _extract_id
        from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE

        if not args.strip():
            chat_view.add_system_message("Usage: /implement <task_id|name|pattern>\nExample: /implement 001")
            return

        project_ctx = ProjectContext(".")
        tasks_dir = _get_tasks_dir(project_ctx)
        query = args.strip()

        try:
            task_id = int(query)
            task_path = _get_task_path_by_id(project_ctx, task_id)
            if task_path:
                title = _parse_title(task_path)
                rel_path = project_ctx.to_relative(task_path)
                command = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
                self.messages.append({"role": "user", "content": command})
                chat_view.add_system_message(f"Running TASK-{task_id:03d}: {title}")

                chat_view.show_thinking()
                self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
                self.run_worker(self._process_llm_response(), exclusive=True)
                return
        except ValueError:
            pass

        matching = []
        query_lower = query.lower()
        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue
            title = _parse_title(task_file)
            if query_lower in title.lower():
                matching.append((task_id, task_file, title))

        if not matching:
            chat_view.add_system_message(f"No tasks found matching: {query}")
            return

        for task_id, task_path, title in matching:
            rel_path = project_ctx.to_relative(task_path)
            command = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
            self.messages.append({"role": "user", "content": command})

        chat_view.add_system_message(f"Running {len(matching)} matching task(s)...")

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(False)
        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
        self.run_worker(self._process_llm_response(), exclusive=True)

    def _handle_implement_all_command(self, chat_view: ChatView) -> None:
        """Handle /implement-all command."""
        from ayder_cli.tasks import _get_tasks_dir, _extract_id, _parse_title
        from ayder_cli.prompts import TASK_EXECUTION_ALL_PROMPT_TEMPLATE

        project_ctx = ProjectContext(".")
        tasks_dir = _get_tasks_dir(project_ctx)

        if not tasks_dir.exists():
            chat_view.add_system_message("No tasks directory found. Create tasks first with /plan.")
            return

        pending = []
        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue
            content = task_file.read_text(encoding="utf-8")
            if "- **status:** pending" in content.lower() or "- **status:** todo" in content.lower():
                title = _parse_title(task_file)
                pending.append((task_id, title))

        if not pending:
            chat_view.add_system_message("No pending tasks found. All tasks are complete!")
            return

        task_list = "\n".join([f"  - TASK-{tid:03d}: {title}" for tid, title in pending])
        chat_view.add_system_message(f"Implementing {len(pending)} pending tasks:\n{task_list}")

        self.messages.append({"role": "user", "content": TASK_EXECUTION_ALL_PROMPT_TEMPLATE})

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(False)
        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
        self.run_worker(self._process_llm_response(), exclusive=True)

    def _handle_task_edit_command(self, args: str, chat_view: ChatView) -> None:
        """Handle /task-edit command."""
        import subprocess
        from ayder_cli.tasks import _get_task_path_by_id

        if not args.strip():
            chat_view.add_system_message("Usage: /task-edit <task_id>\nExample: /task-edit 1")
            return

        try:
            task_id = int(args.strip())
        except ValueError:
            chat_view.add_system_message(f"Invalid task ID: {args.strip()}")
            return

        project_ctx = ProjectContext(".")
        task_path = _get_task_path_by_id(project_ctx, task_id)

        if task_path is None:
            chat_view.add_system_message(f"Task TASK-{task_id:03d} not found.")
            return

        if isinstance(self.config, dict):
            editor = self.config.get("editor", "vim")
        else:
            editor = self.config.editor

        try:
            subprocess.run([editor, str(task_path)], check=True)
            chat_view.add_system_message(f"Task TASK-{task_id:03d} edited successfully.")
        except Exception as e:
            chat_view.add_system_message(f"Error opening editor: {e}")

    def _handle_archive_command(self, chat_view: ChatView) -> None:
        """Handle /archive-completed-tasks command."""
        import shutil
        from ayder_cli.tasks import _get_tasks_dir, _extract_id, _parse_title

        project_ctx = ProjectContext(".")
        tasks_dir = _get_tasks_dir(project_ctx)

        if not tasks_dir.exists():
            chat_view.add_system_message("No tasks directory found.")
            return

        archive_dir = tasks_dir.parent / "task_archive"
        archived = []

        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue
            content = task_file.read_text(encoding="utf-8")
            if "- **status:** done" in content.lower():
                title = _parse_title(task_file)
                archive_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(task_file), str(archive_dir / task_file.name))
                archived.append((task_id, title))

        if not archived:
            chat_view.add_system_message("No completed tasks to archive.")
        else:
            lines = "\n".join(f"  TASK-{tid:03d}: {title}" for tid, title in archived)
            chat_view.add_system_message(f"Archived {len(archived)} completed task(s):\n{lines}")

    async def _process_llm_response(self, no_tools: bool = False) -> None:
        """Process LLM response (runs in worker thread)."""
        worker = get_current_worker()

        try:
            tool_schemas = [] if no_tools else self.registry.get_schemas()

            if isinstance(self.config, dict):
                model = self.config.get("model", "qwen3-coder:latest")
                num_ctx = self.config.get("num_ctx", 65536)
            else:
                model = self.config.model
                num_ctx = self.config.num_ctx

            response = await call_llm_async(
                self.llm,
                self.messages,
                model,
                tools=tool_schemas,
                num_ctx=num_ctx
            )

            if worker.is_cancelled:
                return

            await self._handle_llm_response(response)

        except Exception as e:
            if not worker.is_cancelled:
                chat_view = self.query_one("#chat-view", ChatView)
                chat_view.add_system_message(f"Error: {str(e)}")
        finally:
            if not worker.is_cancelled:
                self.call_later(self._finish_processing)

    async def _handle_llm_response(self, response) -> None:
        """Handle the LLM response, including tool calls."""
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = message.tool_calls

        # Update token counter from usage stats
        usage = getattr(response, "usage", None)
        if usage:
            tokens = getattr(usage, "total_tokens", 0) or 0
            self._total_tokens += tokens
            self.call_later(
                lambda t=self._total_tokens: self.query_one(
                    "#status-bar", StatusBar
                ).update_token_usage(t)
            )

        msg_dict = {
            "role": "assistant",
            "content": content
        }

        if tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in tool_calls
            ]

        self.messages.append(msg_dict)

        if content.strip():
            chat_view = self.query_one("#chat-view", ChatView)
            chat_view.add_assistant_message(content)

        if tool_calls:
            tool_panel = self.query_one("#tool-panel", ToolPanel)

            # Show all tools as running first
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                arguments = tool_call.function.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                tool_panel.add_tool(tool_call.id, tool_name, arguments)

            # Start spinner animation for running tools
            self._tools_timer = self.set_interval(0.1, self._animate_running_tools)

            # Execute tool calls in parallel using asyncio.gather
            async def execute_tool_async(tool_call):
                """Execute a single tool call asynchronously."""
                tool_name = tool_call.function.name
                arguments = tool_call.function.arguments

                if isinstance(arguments, str):
                    arguments = json.loads(arguments)

                # Run the synchronous tool in a thread pool
                result = await asyncio.to_thread(
                    self.registry.execute,
                    tool_name,
                    arguments
                )

                return {
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "result": result
                }

            # Execute all tools concurrently
            tool_tasks = [execute_tool_async(tc) for tc in tool_calls]
            tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)

            # Stop the spinner timer
            if self._tools_timer:
                self._tools_timer.stop()
                self._tools_timer = None

            # Process results and mark tools as complete
            for result_data in tool_results:
                if isinstance(result_data, Exception):
                    # Handle exceptions from tool execution
                    error_msg = f"Error: {str(result_data)}"
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": "error",
                        "name": "unknown",
                        "content": error_msg
                    })
                else:
                    tool_call_id = result_data["tool_call_id"]
                    result = result_data["result"]

                    # Mark tool as complete in panel
                    self.call_later(
                        lambda tid=tool_call_id, res=result: tool_panel.complete_tool(tid, str(res))
                    )

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": result_data["name"],
                        "content": str(result)
                    })

            # Schedule panel cleanup after a short delay
            self.set_timer(2.0, lambda: tool_panel.clear_completed())

            worker = get_current_worker()
            if not worker.is_cancelled:
                await self._process_llm_response()

    def _finish_processing(self) -> None:
        """Finish processing - hide thinking indicator and process next message."""
        if self._thinking_timer:
            self._thinking_timer.stop()
            self._thinking_timer = None

        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.hide_thinking()

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(True)
        input_bar.focus_input()

        if self._pending_messages:
            self._process_next_message()
        else:
            self._is_processing = False

    def _enable_input(self) -> None:
        """Ensure input is enabled (called from worker thread)."""
        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(True)
        input_bar.focus_input()

    def action_cancel(self) -> None:
        """Cancel current operation."""
        if self._thinking_timer:
            self._thinking_timer.stop()
            self._thinking_timer = None

        if self._tools_timer:
            self._tools_timer.stop()
            self._tools_timer = None

        for worker in self.workers:
            worker.cancel()

        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.hide_thinking()

        pending_count = len(self._pending_messages)
        self._pending_messages.clear()
        self._is_processing = False

        self._enable_input()
        if pending_count > 0:
            chat_view.add_system_message(f"Operation cancelled ({pending_count} pending messages cleared).")
        else:
            chat_view.add_system_message("Operation cancelled.")

    def action_exit_prompt(self) -> None:
        """Handle Ctrl+D - press twice to exit."""
        chat_view = self.query_one("#chat-view", ChatView)

        if self._ctrl_d_pressed:
            chat_view.add_system_message("Goodbye!")
            self.exit()
        else:
            self._ctrl_d_pressed = True
            chat_view.add_system_message("Press Ctrl+D again to exit")
            self._ctrl_d_timer = self.set_timer(3.0, self._reset_ctrl_d)

    def _reset_ctrl_d(self) -> None:
        """Reset the Ctrl+D press state."""
        self._ctrl_d_pressed = False
        self._ctrl_d_timer = None

    def action_copy_selection(self) -> None:
        """Copy selected text to clipboard, or cancel if nothing selected."""
        text = self.screen.get_selected_text()
        if text:
            self.copy_to_clipboard(text)
            self.screen.clear_selection()
        else:
            # No selection — fall back to cancel so Ctrl+C
            # still interrupts when nothing is selected
            self.action_cancel()

    def action_clear(self) -> None:
        """Clear chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        self._do_clear(chat_view)


def run_tui(model: str = "default", safe_mode: bool = False) -> None:
    """
    Run the CLI-style TUI application.

    Args:
        model: The LLM model name to use
        safe_mode: Whether to enable safe mode
    """
    app = AyderApp(model=model, safe_mode=safe_mode)
    app.run()


if __name__ == "__main__":
    run_tui()
