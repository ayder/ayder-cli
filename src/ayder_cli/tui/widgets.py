"""TUI widget classes: ChatView, ToolPanel, ActivityBar, AutoCompleteInput, CLIInputBar, StatusBar, AgentPanel."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll, Container
from textual.message import Message
from textual.reactive import reactive
from textual.suggester import SuggestFromList
from textual.widgets import Static, Input, Label, TextArea
from rich.text import Text
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.style import Style

from ayder_cli.parser import content_processor
from ayder_cli.tui.rendering import markup_or_plain
from ayder_cli.tui.types import MessageType


def _sanitize_for_assistant_render(content: str) -> str:
    """Strip tool-call XML markup from assistant content before it is rendered
    as Markdown in the TUI.

    Defense-in-depth: per-family Ollama chat drivers should strip or parse
    tool-call markup before display, but future model variants can still leak
    XML tags in msg.content. When a provider leaks such tags, this helper
    removes them from the rendered view so the chat display stays clean.
    Stored message history is never mutated — only the rendered form.
    """
    if not content:
        return content
    return content_processor.strip_for_display(content)


class ChatView(VerticalScroll):
    """
    CLI-style chat display.
    Simple text output with prefixes instead of panels.
    """

    messages: reactive[list] = reactive(list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._message_widgets: list[Static] = []
        self._thinking_visible: bool = False
        self._follow_mode: bool = True

    def disable_follow_mode(self) -> None:
        """Disable auto-scroll on new messages (user is reading history)."""
        self._follow_mode = False

    def enable_follow_mode(self) -> None:
        """Re-enable auto-scroll on new messages."""
        self._follow_mode = True

    def _create_text(
        self, content: str, msg_type: MessageType, metadata: dict | None = None
    ) -> Text | None:
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
            # Tail the last N lines so streaming tokens stay pinned at the bottom.
            lines = content.strip().splitlines()
            if len(lines) > 4:
                preview = f"    ({len(lines) - 4} more lines)\n" + "\n".join(lines[-4:])
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

    def set_thinking_visible(self, visible: bool) -> None:
        """Toggle visibility of all thinking message widgets."""
        self._thinking_visible = visible
        for msg, widget in zip(self.messages, self._message_widgets):
            if msg["type"] == MessageType.THINKING:
                widget.display = visible

    def add_message(
        self, content: str, msg_type: MessageType, metadata: dict | None = None
    ) -> None:
        """Add a message to the chat view."""
        # Merge consecutive streaming messages
        if msg_type in (MessageType.ASSISTANT, MessageType.THINKING):
            if self.messages and self.messages[-1]["type"] == msg_type:
                self.messages[-1]["content"] += content
                full_content = self.messages[-1]["content"]
                last_widget = self._message_widgets[-1]

                if msg_type == MessageType.ASSISTANT:
                    last_widget.update(
                        Markdown(_sanitize_for_assistant_render(full_content).strip())
                    )
                else:
                    text = self._create_text(full_content, msg_type, metadata)
                    if text:
                        last_widget.update(text)
                if self._follow_mode:
                    self.scroll_end(animate=False)
                return

        self.messages.append(
            {"content": content, "type": msg_type, "metadata": metadata}
        )

        if msg_type == MessageType.ASSISTANT:
            content = _sanitize_for_assistant_render(content).strip()

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
                # Hide thinking blocks by default
                if msg_type == MessageType.THINKING and not self._thinking_visible:
                    msg_widget.display = False

        if self._follow_mode:
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
        """Add a new running tool to the panel or update an existing one."""
        args_str = self._format_preview(str(arguments), max_len=80)

        tool_text = Text()
        tool_text.append(f"{tool_name}", style="yellow")
        tool_text.append(f" {args_str}", style="dim")

        if tool_call_id in self._tools:
            widget, spinner, _, _, completed = self._tools[tool_call_id]
            if not completed:
                # Update the existing widget in place. Remounting (remove + mount)
                # re-runs layout and causes a visible flash under load; a fresh
                # Spinner pushed via Static.update() refreshes the row without
                # reflowing the panel.
                spinner = Spinner("aesthetic", text=tool_text, style="bold yellow")
                widget.update(spinner)
                self._tools[tool_call_id] = (widget, spinner, tool_name, args_str, False)
            return

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
        for tool_id, (
            widget,
            spinner,
            tool_name,
            args_str,
            is_done,
        ) in self._tools.items():
            if not is_done and spinner is not None:
                widget.update(spinner)

    def _format_preview(self, text: str, max_len: int = 80) -> str:
        """Format text to be a short preview."""
        preview = text.replace("\n", " ").replace("  ", " ").strip()
        if len(preview) > max_len:
            preview = preview[: max_len - 3] + "..."
        return preview

    def clear_completed(self) -> None:
        """Remove all completed tools (does not change visibility)."""
        to_remove = [
            tid for tid, (_, _, _, _, is_done) in self._tools.items() if is_done
        ]
        for tool_id in to_remove:
            widget, _, _, _, _ = self._tools[tool_id]
            widget.remove()
            del self._tools[tool_id]


class ThinkingPanel(Container):
    """
    A dedicated panel for the model's reasoning / thinking stream.

    Toggled with Ctrl+T, mirroring ToolPanel (Ctrl+O) and AgentPanel (Ctrl+G):
    reasoning is streamed in silently while the ActivityBar spinner shows the
    ambient "Thinking..." status, and the user opens the panel to read the full
    chain. It is taller than the other panels because reasoning is long-form,
    and shows the complete accumulated text (scrollable) rather than a tail.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._user_visible: bool = False
        self._buffer: str = ""
        self._widget: Static | None = None
        self._needs_separator: bool = False

    def compose(self) -> ComposeResult:
        """Compose starts empty; the content widget is mounted on first stream."""
        return
        yield

    def on_mount(self) -> None:
        """Start hidden - user toggles with Ctrl+T."""
        self.display = False

    def toggle(self) -> bool:
        """Toggle panel visibility. Returns new visibility state."""
        self._user_visible = not self._user_visible
        self.display = self._user_visible
        return self._user_visible

    def start_phase(self) -> None:
        """Mark the start of a new reasoning phase within the same turn.

        A blank line is inserted before the next streamed delta so successive
        phases (think -> tool -> think) stay visually separated.
        """
        if self._buffer:
            self._needs_separator = True

    def add_thinking(self, text: str) -> None:
        """Append a streamed reasoning delta and re-render. Never auto-shows."""
        if not text:
            return
        if self._needs_separator:
            self._buffer += "\n\n"
            self._needs_separator = False
        self._buffer += text

        content = self._buffer.strip()
        renderable = markup_or_plain(content)
        if self._widget is None:
            self._widget = Static(renderable, classes="thinking-content")
            self.mount(self._widget)
        else:
            self._widget.update(renderable)
        self.scroll_end(animate=False)

    def clear(self) -> None:
        """Reset the panel for a new turn (does not change visibility)."""
        self._buffer = ""
        self._needs_separator = False
        if self._widget is not None:
            self._widget.remove()
            self._widget = None


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
        self._generating = False
        self._tools_working = False
        self._agents_running = 0
        self._thinking_spinner = Spinner("dots2", style="bold yellow")
        self._generating_spinner = Spinner("dots2", style="bold green")
        self._tools_spinner = Spinner("aesthetic", style="bold yellow")
        self._widget: Static | None = None

    def compose(self) -> ComposeResult:
        self._widget = Static("", id="activity-text")
        yield self._widget

    def set_thinking(self, active: bool) -> None:
        """Show or hide the Thinking indicator."""
        self._thinking = active
        if active:
            self._generating = False
        self._refresh_display()

    def set_generating(self, active: bool) -> None:
        """Show or hide the Generating indicator (content streaming)."""
        self._generating = active
        self._refresh_display()

    def set_tools_working(self, active: bool) -> None:
        """Show or hide the Tools Working indicator."""
        self._tools_working = active
        self._refresh_display()

    def set_agents_running(self, count: int) -> None:
        """Show or hide the agents running indicator."""
        self._agents_running = count
        self._refresh_display()

    def update_spinners(self) -> None:
        """Re-render spinners (call on a timer)."""
        if (not self._thinking and not self._generating
                and not self._tools_working and self._agents_running == 0):
            return
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Update the displayed text based on current state."""
        if not self._widget:
            return

        # Determine the LLM activity label and spinner
        label: Text | None = None
        spinner: Spinner | None = None

        if self._thinking and self._tools_working:
            label = Text.assemble(
                ("Thinking... ", "bold yellow"), ("| ", "dim"), ("Tools Working...", "bold yellow"),
            )
            spinner = self._thinking_spinner
        elif self._thinking:
            label = Text("Thinking...")
            spinner = self._thinking_spinner
        elif self._generating and self._tools_working:
            label = Text.assemble(
                ("Generating... ", "bold green"), ("| ", "dim"), ("Tools Working...", "bold yellow"),
            )
            spinner = self._tools_spinner
        elif self._generating:
            label = Text("Generating...")
            spinner = self._generating_spinner
        elif self._tools_working:
            label = Text("Tools Working...")
            spinner = self._tools_spinner

        # Build agent prefix
        agent_prefix = (
            Text(f"Agents running ({self._agents_running}) ", style="bold cyan")
            if self._agents_running > 0 else None
        )

        if label and agent_prefix and spinner:
            # Both agent and LLM activity
            spinner.text = Text.assemble(agent_prefix, ("| ", "dim"), label)
            self._widget.update(spinner)
        elif label and spinner:
            # LLM activity only
            spinner.text = label
            self._widget.update(spinner)
        elif agent_prefix:
            # Agents only, no LLM — show with spinner
            self._thinking_spinner.text = agent_prefix
            self._widget.update(self._thinking_spinner)
        else:
            self._widget.update("")

    def clear(self) -> None:
        """Reset LLM activity state. Agent indicator preserved via _refresh_display."""
        self._thinking = False
        self._generating = False
        self._tools_working = False
        self._refresh_display()


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
        if event.key == "tab" and self.value.startswith("/"):  # type: ignore[has-type]
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

    PLACEHOLDER = "Type your message or @path/to/file"

    class Submitted(Message):
        """Posted when the user presses Enter to submit."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    _PASTE_THRESHOLD = 3
    _FILE_PICKER_LIMIT = 8
    _FILE_REFERENCE_STYLE = Style(color="cyan", bold=True, underline=True)

    def __init__(self, commands: list[str] | None = None, **kwargs):
        super().__init__(soft_wrap=True, show_line_numbers=False, **kwargs)
        self._commands = commands or []
        self._tab_cycle_matches: list[str] = []
        self._tab_cycle_index = -1
        self._placeholder_widget: Static | None = None
        self._file_picker_widget: Static | None = None
        self._file_picker_suggestions: list[str] = []
        self._file_picker_index = 0
        self._file_picker_token: tuple[int, int, str] | None = None
        self._file_picker_root = Path.cwd().resolve()
        # Ordered (marker, content) pairs for collapsed pastes. Markers are
        # shown inline in the textarea; on submit they are expanded back to
        # their full content in place, preserving any surrounding typed text.
        self._pastes: list[tuple[str, str]] = []

    def on_mount(self) -> None:
        self._placeholder_widget = Static(
            self.PLACEHOLDER, id="input-placeholder"
        )
        self.mount(self._placeholder_widget)
        self._file_picker_widget = Static("", id="file-picker")
        self._file_picker_widget.display = False
        self.mount(self._file_picker_widget)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._placeholder_widget:
            self._placeholder_widget.display = not bool(self.text)
        self._refresh_file_picker()

    def _should_collapse_paste(self, text: str) -> bool:
        """Return True if pasted text should be collapsed."""
        if not text:
            return False
        return text.count("\n") >= self._PASTE_THRESHOLD

    def _collapse_display_text(self, text: str) -> str:
        """Return the collapsed display string for pasted text."""
        line_count = text.count("\n") + (1 if not text.endswith("\n") else 0)
        return f"[pasted: {line_count} lines]"

    def _store_paste(self, marker: str, content: str) -> None:
        """Record a collapsed paste so its marker can be expanded on submit."""
        self._pastes.append((marker, content))

    def _clear_paste(self) -> None:
        """Clear all stored paste state."""
        self._pastes = []

    def _remove_paste(self, marker: str) -> None:
        """Drop the first stored paste whose marker matches."""
        for i, (stored_marker, _content) in enumerate(self._pastes):
            if stored_marker == marker:
                del self._pastes[i]
                return

    def _expand_pastes(self, text: str) -> str:
        """Expand each stored marker in ``text`` back to its full content.

        Markers are replaced one occurrence at a time, in insertion order, so
        text typed around (and between) pastes is preserved verbatim.
        """
        result = text
        for marker, content in self._pastes:
            idx = result.find(marker)
            if idx == -1:
                continue
            result = result[:idx] + content + result[idx + len(marker) :]
        return result

    def _marker_at_cursor_end(self, text_before_cursor: str) -> str | None:
        """Return a stored marker that ``text_before_cursor`` ends with, if any."""
        for marker, _content in self._pastes:
            if text_before_cursor.endswith(marker):
                return marker
        return None

    def _reset_tab_cycle(self) -> None:
        """Reset slash-command tab cycle state."""
        self._tab_cycle_matches = []
        self._tab_cycle_index = -1

    def _offset_from_location(self, location: tuple[int, int]) -> int:
        """Return the character offset for a TextArea row/column location."""
        row, col = location
        lines = self.text.split("\n")
        offset = 0
        for line in lines[:row]:
            offset += len(line) + 1
        if 0 <= row < len(lines):
            offset += min(col, len(lines[row]))
        return offset

    def _location_from_offset(self, offset: int) -> tuple[int, int]:
        """Return a TextArea row/column location for a character offset."""
        remaining = max(0, offset)
        lines = self.text.split("\n")
        for row, line in enumerate(lines):
            if remaining <= len(line):
                return row, remaining
            remaining -= len(line) + 1
        return len(lines) - 1, len(lines[-1]) if lines else 0

    @staticmethod
    def _is_file_token_boundary(char: str) -> bool:
        """Return True when ``char`` can delimit an @file token."""
        return char.isspace()

    def _file_token_at_cursor(self) -> tuple[int, int, str] | None:
        """Return (start, end, token_without_at) for an active @ token."""
        cursor = self._offset_from_location(self.cursor_location)
        before = self.text[:cursor]
        at_index = before.rfind("@")
        if at_index == -1:
            return None
        if at_index > 0 and not self._is_file_token_boundary(before[at_index - 1]):
            return None
        token = before[at_index + 1 :]
        if any(ch.isspace() for ch in token):
            return None
        return at_index, cursor, token

    def _file_reference_path(self, token: str) -> Path | None:
        """Return an existing project path for a complete @ token."""
        normalized = token.replace("\\", "/")
        if not normalized or normalized.startswith("/"):
            return None
        if ".." in Path(normalized).parts:
            return None

        path = self._file_picker_root / normalized
        if not self._path_within_picker_root(path) or not path.exists():
            return None
        return path

    def _file_reference_spans(self, line: str) -> list[tuple[int, int]]:
        """Return @path spans that resolve to existing project entries."""
        spans: list[tuple[int, int]] = []
        index = 0
        while True:
            at_index = line.find("@", index)
            if at_index == -1:
                return spans
            if at_index > 0 and not self._is_file_token_boundary(line[at_index - 1]):
                index = at_index + 1
                continue

            end = at_index + 1
            while end < len(line) and not line[end].isspace():
                end += 1

            token = line[at_index + 1 : end]
            if self._file_reference_path(token) is not None:
                spans.append((at_index, end))
            index = end

    def get_line(self, line_index: int) -> Text:
        """Retrieve a line and highlight complete @file references."""
        line = super().get_line(line_index)
        for start, end in self._file_reference_spans(line.plain):
            line.stylize(self._FILE_REFERENCE_STYLE, start, end)
        return line

    def _path_within_picker_root(self, path: Path) -> bool:
        """Return True when ``path`` resolves under the project root."""
        try:
            path.resolve().relative_to(self._file_picker_root)
            return True
        except ValueError:
            return False

    def _file_picker_entries(self, token: str) -> list[str]:
        """Return directory-first relative suggestions for an @ token."""
        normalized = token.replace("\\", "/")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            return []

        parent_text, _, filter_text = normalized.rpartition("/")
        if normalized.endswith("/"):
            parent_text = normalized.rstrip("/")
            filter_text = ""

        parent = self._file_picker_root / parent_text if parent_text else self._file_picker_root
        if not self._path_within_picker_root(parent) or not parent.is_dir():
            return []

        include_hidden = filter_text.startswith(".")
        entries: list[tuple[bool, str]] = []
        try:
            children = list(parent.iterdir())
        except OSError:
            return []

        for child in children:
            name = child.name
            if name.startswith(".") and not include_hidden:
                continue
            if filter_text and not name.startswith(filter_text):
                continue
            if not self._path_within_picker_root(child):
                continue
            rel = child.relative_to(self._file_picker_root).as_posix()
            is_dir = child.is_dir()
            entries.append((is_dir, f"{rel}/" if is_dir else rel))

        entries.sort(key=lambda item: (not item[0], item[1].casefold()))
        return [entry for _is_dir, entry in entries[: self._FILE_PICKER_LIMIT]]

    def _render_file_picker(self) -> None:
        """Render the current picker suggestions."""
        if self._file_picker_widget is None:
            return
        if not self._file_picker_suggestions:
            self._file_picker_widget.display = False
            self._file_picker_widget.update(markup_or_plain(""))
            return

        lines = []
        for idx, suggestion in enumerate(self._file_picker_suggestions):
            marker = ">" if idx == self._file_picker_index else " "
            lines.append(f"{marker} @{suggestion}")
        self._file_picker_widget.update(markup_or_plain("\n".join(lines)))
        self._file_picker_widget.display = True

    def _close_file_picker(self) -> None:
        """Close and reset the @ file picker."""
        self._file_picker_suggestions = []
        self._file_picker_index = 0
        self._file_picker_token = None
        self._render_file_picker()

    def _refresh_file_picker(self) -> None:
        """Refresh @ file suggestions based on the current cursor token."""
        token = self._file_token_at_cursor()
        if token is None:
            self._close_file_picker()
            return
        suggestions = self._file_picker_entries(token[2])
        if not suggestions:
            self._close_file_picker()
            return
        self._file_picker_token = token
        self._file_picker_suggestions = suggestions
        self._file_picker_index = min(self._file_picker_index, len(suggestions) - 1)
        self._render_file_picker()

    def _file_picker_active(self) -> bool:
        """Return True when @ suggestions are visible."""
        return bool(self._file_picker_suggestions and self._file_picker_token)

    def _move_file_picker_selection(self, direction: int) -> None:
        """Move the selected @ suggestion."""
        if not self._file_picker_suggestions:
            return
        self._file_picker_index = (
            self._file_picker_index + direction
        ) % len(self._file_picker_suggestions)
        self._render_file_picker()

    def _accept_file_picker_selection(self) -> None:
        """Insert the selected @ path; directories keep the picker open."""
        if not self._file_picker_active():
            return
        selected = self._file_picker_suggestions[self._file_picker_index]
        token = self._file_picker_token
        if token is None:
            return
        start, end, _token_text = token
        self.delete(self._location_from_offset(start), self._location_from_offset(end))
        self.insert(f"@{selected}")
        if selected.endswith("/"):
            self._refresh_file_picker()
        else:
            self._close_file_picker()

    def _next_tab_completion(self, current: str) -> str | None:
        """Return the next slash-command completion for current input."""
        if not current.startswith("/"):
            self._reset_tab_cycle()
            return None

        if self._tab_cycle_matches and current in self._tab_cycle_matches:
            matches = self._tab_cycle_matches
        else:
            matches = [c for c in self._commands if c.startswith(current)]
            if not matches:
                self._reset_tab_cycle()
                return None
            self._tab_cycle_matches = matches
            self._tab_cycle_index = -1

        self._tab_cycle_index = (self._tab_cycle_index + 1) % len(matches)
        return matches[self._tab_cycle_index]

    def _on_key(self, event) -> None:  # type: ignore[override]
        if self._file_picker_active():
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._close_file_picker()
                return
            if event.key == "up":
                event.prevent_default()
                event.stop()
                self._move_file_picker_selection(-1)
                return
            if event.key == "down":
                event.prevent_default()
                event.stop()
                self._move_file_picker_selection(1)
                return
            if event.key in ("enter", "tab"):
                event.prevent_default()
                event.stop()
                self._accept_file_picker_selection()
                return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            value = self._expand_pastes(self.text).strip()
            if value:
                self.post_message(self.Submitted(value))
                self._clear_paste()
                self.clear()
            return

        # Newline insertion. Shift+Enter works in terminals that speak the Kitty
        # keyboard protocol (e.g. Ghostty); Ctrl+J sends a literal "\n" and is a
        # universal fallback for terminals that can't distinguish Shift+Enter
        # from Enter. Both insert a line break without submitting.
        if event.key in ("shift+enter", "ctrl+j"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return

        if event.key == "escape" and self._pastes:
            event.prevent_default()
            event.stop()
            self._clear_paste()
            self.clear()
            return

        if event.key == "backspace" and self._pastes:
            row, col = self.cursor_location
            before_cursor = self.text.split("\n")[row][:col]
            marker = self._marker_at_cursor_end(before_cursor)
            if marker is not None:
                event.prevent_default()
                event.stop()
                self.delete((row, col - len(marker)), (row, col))
                self._remove_paste(marker)
                return

        if event.key == "tab" and self.text.startswith("/"):
            event.prevent_default()
            event.stop()
            current = self.text.strip()
            completion = self._next_tab_completion(current)
            if completion:
                self.clear()
                self.insert(completion)
            return

        if event.key == "pageup":
            event.prevent_default()
            event.stop()
            if self._scroll_agent_panel("page_up"):
                return
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.disable_follow_mode()
            chat_view.scroll_page_up(animate=False)
            return

        if event.key == "pagedown":
            event.prevent_default()
            event.stop()
            if self._scroll_agent_panel("page_down"):
                return
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.scroll_page_down(animate=False)
            if chat_view.scroll_offset.y >= chat_view.max_scroll_y:
                chat_view.enable_follow_mode()
            return

        if event.key == "ctrl+pageup":
            event.prevent_default()
            event.stop()
            if self._scroll_agent_panel("up"):
                return
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.disable_follow_mode()
            chat_view.scroll_up(animate=False)
            return

        if event.key == "ctrl+pagedown":
            event.prevent_default()
            event.stop()
            if self._scroll_agent_panel("down"):
                return
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.scroll_down(animate=False)
            if chat_view.scroll_offset.y >= chat_view.max_scroll_y:
                chat_view.enable_follow_mode()
            return

        if event.key == "home":
            event.prevent_default()
            event.stop()
            if self._scroll_agent_panel("home"):
                return
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.disable_follow_mode()
            chat_view.scroll_home(animate=False)
            return

        if event.key == "end":
            event.prevent_default()
            event.stop()
            if self._scroll_agent_panel("end"):
                return
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.enable_follow_mode()
            chat_view.scroll_end(animate=False)
            return

        self._reset_tab_cycle()

    def _scroll_agent_panel(self, motion: str) -> bool:
        """Route a scroll motion to the agents panel when it is open (Ctrl+G).

        ``motion`` is a Widget.scroll_* suffix: 'page_up', 'page_down', 'up',
        'down', 'home', 'end'. Returns True when the panel is visible and
        handled the scroll, so the caller leaves the chat view alone.
        """
        try:
            panel = self.app.query_one("#agent-panel", AgentPanel)
        except Exception:
            return False
        if not panel.display:
            return False
        getattr(panel, f"scroll_{motion}")(animate=False)
        return True

    async def _on_paste(self, event) -> None:
        """Handle bracketed paste — collapse multi-line pastes.

        The collapsed marker is inserted at the cursor (replacing any
        selection) so existing typed text is preserved; the full content is
        expanded back in place on submit.
        """
        text = event.text
        if self._should_collapse_paste(text):
            event.prevent_default()
            event.stop()
            marker = self._collapse_display_text(text)
            self._store_paste(marker, text)
            self.insert(marker)


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
        yield Static("❯", classes="prompt")
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
        """Handle history navigation with wrap-aware multiline cursor support.

        Up/Down navigate command history only when the input is empty or the
        cursor sits at the true visual edge — the first character for Up, the
        last for Down. We detect the edge with the TextArea's own
        ``get_cursor_up_location``/``get_cursor_down_location``: when the cursor
        cannot move further (the would-be location equals the current one), we
        are at the edge. This respects *soft-wrapped* lines, where a long single
        paragraph spans several visual rows but is still document row 0 — so the
        cursor walks up/down each visual row before history kicks in.
        """
        inp = self._input
        if event.key == "up":
            if not inp or not inp.text or inp.get_cursor_up_location() == inp.cursor_location:
                event.prevent_default()
                event.stop()
                self._history_navigate(-1)
        elif event.key == "down":
            if not inp or not inp.text or inp.get_cursor_down_location() == inp.cursor_location:
                event.prevent_default()
                event.stop()
                self._history_navigate(1)

    def focus_input(self) -> None:
        """Focus the input field."""
        if self._input:
            self._input.focus()

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

    def __init__(self, model: str = "default", permissions: set | None = None, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.token_count = 0
        self.active_files: list[str] = []
        self._permissions = permissions or {"r"}

    def compose(self) -> ComposeResult:
        mode_str = "".join(sorted(self._permissions))
        yield Label(markup_or_plain(f"model: {self.model}"), id="model-label")
        yield Label(markup_or_plain(f" | mode: {mode_str}"), id="mode-label")
        yield Label(" | ctx: —", id="token-label")
        yield Label(" | files: 0", id="files-label")
        yield Label("", id="skill-label")
        yield Label("", id="plugin-badges")
        yield Static(classes="spacer")
        yield Label("Ctrl+H Help", classes="key-hint")

    def on_mount(self) -> None:
        # Plugins (e.g. mcp-tool) register their status badge at import time,
        # before the TUI mounts, so a single refresh here picks it up.
        self.refresh_plugin_badges()

    def set_model(self, model: str) -> None:
        """Update the displayed model."""
        self.model = model
        label = self.query_one("#model-label", Label)
        label.update(markup_or_plain(f"model: {model}"))

    def update_context_usage(self, used: int, total: int) -> None:
        """Update the live context-window usage: current tokens / window size.

        Shows how full the MAIN LLM's context is right now (drives compaction),
        not a cumulative session counter.
        """
        self.token_count = used
        pct = (used / total * 100.0) if total > 0 else 0.0
        label = self.query_one("#token-label", Label)
        label.update(
            f" | ctx: {self._fmt_tokens(used)}/{self._fmt_tokens(total)} ({pct:.0f}%)"
        )

    @staticmethod
    def _fmt_tokens(n: int) -> str:
        """Compact token count for the bar: 1234 -> '1K', 131072 -> '131K'."""
        return f"{n / 1000:.0f}K" if n >= 1000 else str(n)

    def update_permissions(self, permissions: set) -> None:
        """Update permission mode display."""
        self._permissions = permissions
        mode_str = "".join(sorted(permissions))
        label = self.query_one("#mode-label", Label)
        label.update(markup_or_plain(f" | mode: {mode_str}"))

    def set_skill(self, skill_name: str | None) -> None:
        """Update the active skill label."""
        label = self.query_one("#skill-label", Label)
        label.update(markup_or_plain(f" | skill: {skill_name}" if skill_name else ""))

    @staticmethod
    def _render_badges(
        statuses: dict[str, tuple[str, str]],
        enabled_tags: "frozenset | set | None" = None,
    ) -> Text:
        """Build the status-bar text for plugin badges.

        ``statuses`` maps plugin name -> (label, color); each badge renders as
        `` | <label>`` with the label in its colour (e.g. green when an MCP
        server is connected, red when configured servers are unreachable).

        When ``enabled_tags`` is given, a badge whose name is NOT enabled is shown
        greyed out — the plugin is installed/connected but turned off via /plugin.
        ``None`` means no tag filter is active (everything enabled), so the
        registered colours are kept.
        """
        text = Text()
        for name, (label, color) in sorted(statuses.items()):
            display_color = color
            if enabled_tags is not None and name not in enabled_tags:
                display_color = "grey50"  # disabled via /plugin
            text.append(" | ", style="dim")
            text.append(label, style=display_color)
        return text

    def _enabled_tags(self) -> "frozenset | None":
        """Enabled tool tags from the running app (None = no filter / all on)."""
        try:
            chat_loop = getattr(self.app, "chat_loop", None)
            if chat_loop is None:
                return None
            return chat_loop.config.tool_tags
        except Exception:
            return None

    def refresh_plugin_badges(self) -> None:
        """Re-render plugin status badges, greying out any disabled via /plugin."""
        from ayder_cli.tools import plugin_status

        try:
            label = self.query_one("#plugin-badges", Label)
        except Exception:
            return  # not mounted yet
        label.update(self._render_badges(plugin_status.get_all(), self._enabled_tags()))


@dataclass
class _AgentEntry:
    """Internal data for one agent run in the panel.

    No Container wrapper — status and detail are mounted as siblings
    in the panel for simplicity (per user request).
    """
    status_widget: Static   # Status line (updated in real-time)
    detail_widget: Static | None  # Full output (added on completion)
    name: str
    completed: bool = False
    assignment: str | None = None  # short '<prompt> · <task_id>' label for this run


class AgentPanel(Container):
    """Scrollable panel for agent runs. Toggled with Ctrl+G.

    Never auto-shows. Content updates silently regardless of visibility.
    The ActivityBar spinner provides ambient status.
    """

    MAX_ENTRIES = 50

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._user_visible: bool = False
        self._entries: dict[int, _AgentEntry] = {}

    def compose(self) -> ComposeResult:
        # Empty generator — widgets mounted dynamically
        return
        yield

    def on_mount(self) -> None:
        self.display = False

    def toggle(self) -> bool:
        """Toggle panel visibility. Returns new visibility state."""
        self._user_visible = not self._user_visible
        self.display = self._user_visible
        return self._user_visible

    def add_agent(self, name: str, run_id: int, assignment: str | None = None) -> None:
        """Add a new agent run entry. Never auto-shows the panel.

        `assignment` is a short '<prompt> · <task_id>' label for the dispatched
        task; when present it is shown between the agent name and its status.
        """
        self._prune_if_needed()

        text = Text()
        text.append("  ▶ ", style="bold yellow")
        text.append(f"{name}", style="bold magenta")
        if assignment:
            text.append(f" — {assignment}", style="cyan")
        text.append(" running...", style="dim")

        status_widget = Static(text, classes="agent-status running")
        entry = _AgentEntry(
            status_widget=status_widget,
            detail_widget=None,
            name=name,
            assignment=assignment,
        )
        self._entries[run_id] = entry
        self.mount(status_widget)

    def complete_agent(self, run_id: int, summary: str, status: str = "completed") -> None:
        """Mark agent as completed with full summary. Lookup by run_id."""
        if run_id not in self._entries:
            return
        entry = self._entries[run_id]
        if entry.completed:
            return
        entry.completed = True

        # Update status line. A successful run reports status "done" (the pull
        # delivery vocabulary); treat that — and the legacy "completed" — as
        # success so it gets the green check, not the red ✗.
        text = Text()
        if status in ("done", "completed"):
            text.append("  ✓ ", style="bold green")
        elif status == "timeout":
            text.append("  ⏱ ", style="bold yellow")
        else:
            text.append("  ✗ ", style="bold red")
        text.append(f"{entry.name}", style="bold")
        preview = summary[:80] + "..." if len(summary) > 80 else summary
        text.append(f" — {preview}", style="dim")
        entry.status_widget.update(text)
        entry.status_widget.remove_class("running")
        status_class = "completed" if status in ("done", "completed") else status
        entry.status_widget.add_class(status_class)

        # Add detail block with full summary
        detail = Static(
            Text(f"    {summary}", style="dim"),
            classes="agent-detail",
        )
        entry.detail_widget = detail
        self.mount(detail, after=entry.status_widget)
        self.scroll_end(animate=False)

    def update_agent(self, run_id: int, name: str, event: str, data: Any = None,
                     assignment: str | None = None) -> None:
        """Handle an agent progress event. Lookup by run_id."""
        if run_id not in self._entries:
            self.add_agent(name, run_id, assignment)

        entry = self._entries.get(run_id)
        if entry is None or entry.completed:
            return
        if assignment and not entry.assignment:
            entry.assignment = assignment  # first event that carried it wins

        if event == "tool_start" and isinstance(data, dict):
            tool_name = data.get("name", "?")
            self._update_status(entry, f"Running tool: {tool_name}")
        elif event == "thinking_start":
            self._update_status(entry, "Thinking...")
        elif event == "tools_cleanup":
            self._update_status(entry, "Processing...")

    def _update_status(self, entry: _AgentEntry, status_text: str) -> None:
        """Update the status line text for a running agent."""
        text = Text()
        text.append("  ▶ ", style="bold yellow")
        text.append(f"{entry.name}", style="bold magenta")
        if entry.assignment:
            text.append(f" — {entry.assignment}", style="cyan")
        text.append(f" — {status_text}", style="dim")
        entry.status_widget.update(text)

    def _prune_if_needed(self) -> None:
        """Remove oldest completed entry if at capacity."""
        if len(self._entries) < self.MAX_ENTRIES:
            return
        to_prune = None
        for run_id, entry in self._entries.items():
            if entry.completed:
                to_prune = run_id
                break
        if to_prune is not None:
            entry = self._entries[to_prune]
            entry.status_widget.remove()
            if entry.detail_widget:
                entry.detail_widget.remove()
            del self._entries[to_prune]
