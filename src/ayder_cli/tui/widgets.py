"""TUI widget classes: ChatView (with its thinking, tool and agent items), ActivityBar, AutoCompleteInput, CLIInputBar, StatusBar."""

import json
import time
from pathlib import Path
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.content import Content
from textual.css.query import NoMatches
from textual.geometry import Size
from textual.highlight import (
    ANSIDarkHighlightTheme,
    ANSILightHighlightTheme,
    HighlightTheme,
    highlight,
)
from textual.message import Message
from textual.reactive import reactive
from textual.suggester import SuggestFromList
from textual.widgets import Static, Input, Label, TextArea
from textual.widgets.markdown import Markdown, MarkdownFence
from rich.cells import cell_len
from rich.text import Text
from rich.spinner import Spinner
from rich.style import Style

from ayder_cli.parser import content_processor
from ayder_cli.tui.rendering import markup_or_plain
from ayder_cli.tui.types import MessageType
from ayder_cli.log import get_logger

logger = get_logger("ui")


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


# textual 8.2.7's ANSI code themes misspell four colour names, and a colour it
# cannot parse is dropped: under the ayder palettes, single-quoted strings,
# magic methods, attributes and (light) errors rendered uncoloured.
_ANSI_COLOUR_TYPOS = {
    "ans_red": "ansi_red",
    "ansi_blow": "ansi_blue",
    "ansi_greenb": "ansi_green",
    "ansi_yelllow": "ansi_yellow",
}


def _fix_colour_names(styles: dict[tuple[str, ...], str]) -> dict[tuple[str, ...], str]:
    """Return a code theme's styles with the misspelt ANSI colour names corrected."""
    return {
        token: " ".join(_ANSI_COLOUR_TYPOS.get(word, word) for word in style.split())
        for token, style in styles.items()
    }


class _AnsiDarkCodeTheme(ANSIDarkHighlightTheme):
    """Code colours under an ANSI palette on a dark terminal."""

    STYLES = _fix_colour_names(ANSIDarkHighlightTheme.STYLES)


class _AnsiLightCodeTheme(ANSILightHighlightTheme):
    """Code colours under an ANSI palette on a light terminal."""

    STYLES = _fix_colour_names(ANSILightHighlightTheme.STYLES)


class AssistantFence(MarkdownFence):
    """A fenced code block in an assistant reply, highlighted as rich.markdown did.

    The language is the first word of the info string (```python title="x.py"
    is Python). No info string means plain text: Textual would guess, and
    Pygments guesses short snippets badly (a Python def comes out as
    "teratermmacro"). ANSI palettes use the corrected code themes above.
    """

    @classmethod
    def highlight(
        cls, code: str, language: str, ansi: bool = False, dark: bool = False
    ) -> Content:
        words = (language or "").split()
        theme: type[HighlightTheme] = HighlightTheme
        if ansi:
            theme = _AnsiDarkCodeTheme if dark else _AnsiLightCodeTheme
        return highlight(code, language=words[0] if words else "text", theme=theme)


class AssistantReply(Markdown):
    """An assistant reply, drawn with Textual's Markdown widget so the mouse can
    select its text: Textual extracts a selection only from Text/Content
    visuals, and a rich.markdown renderable gave none.

    ``set_text`` takes the whole reply so far. One worker brings the widget up
    to date, and only through ``append``, because in textual 8.2.7:
    * ``append`` reads the source when it is called, so two appends that are
      not awaited one after the other duplicate blocks;
    * ``update(text)`` leaves the next ``append`` parsing from the last line
      rather than the last block, which breaks an open code fence.
    When the text no longer extends what is shown (the sanitizer removed
    tool-call markup that had streamed in), the document is cleared and
    rebuilt. Links do not open on click.

    The first block carries the ``-first-block`` class, which the themes use
    to drop its top margin. A ``:first-child`` rule would do the same, but
    Textual restyles every block with an order-dependent rule on each mount,
    which made a long reply stream slower than rich.markdown did.
    """

    BLOCKS = {**Markdown.BLOCKS, "fence": AssistantFence, "code_block": AssistantFence}

    def __init__(self, text: str = "", **kwargs: Any) -> None:
        super().__init__(None, open_links=False, **kwargs)
        self._target = text
        self._draining = False

    def on_mount(self) -> None:
        self._drain_soon()

    def set_text(self, text: str) -> None:
        """Show ``text``, the whole reply so far; the widget catches up in the background."""
        self._target = text
        if self.is_mounted:
            self._drain_soon()

    def _drain_soon(self) -> None:
        if not self._draining and self._target != self.source:
            self._draining = True
            self.run_worker(self._drain(), group="assistant-reply")

    async def _drain(self) -> None:
        try:
            while self._target != self.source:
                target, shown = self._target, self.source
                # One batch: no frame shows a cleared document, or a new first
                # block before it is marked.
                with self.app.batch_update():
                    if not target.startswith(shown):
                        await self.update("")
                        shown = ""
                    await self.append(target[len(shown):])
                    if self.children:
                        self.children[0].add_class("-first-block")
        finally:
            self._draining = False


_THINK_ROWS = 8  # most tail rows a thinking box shows (plus its header line)


def _fmt_secs(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def _full_lines(result: str) -> list[Content]:
    return [Content(line.expandtabs(4)) for line in result.splitlines()]


def _tail_rows(text: str, width: int, rows: int) -> list[Content]:
    """The last ``rows`` wrapped lines of ``text``. Only a suffix is wrapped, so
    the cost does not grow with the length of the reasoning."""
    text = text.strip("\n")
    window = text[-width * rows * 3 :]
    return Content(window).wrap(width, overflow="fold")[-rows:]


class _InChatItem(Static):
    """An item in the chat: a Static whose Content is rebuilt from its state.

    Content, not a Rich renderable, so the mouse can select its text. Live items
    (a running thinking phase or agent) are refreshed by ChatView.tick_live_items,
    which the app's shared activity timer calls.
    """

    live = False

    def __init__(self, classes: str) -> None:
        super().__init__("", classes=classes)
        self._last_width = 0
        self._shown_secs = -1

    def _build(self, width: int) -> Content:
        raise NotImplementedError

    def _elapsed(self) -> float:
        return 0.0

    def refresh_item(self) -> None:
        self._last_width = max(10, self.content_size.width or 80)
        self._shown_secs = int(self._elapsed())
        self.update(self._build(self._last_width))

    def tick(self) -> None:
        if int(self._elapsed()) != self._shown_secs:
            self.refresh_item()

    def on_mount(self) -> None:
        self.refresh_item()

    def on_resize(self, event: events.Resize) -> None:
        if max(10, self.content_size.width) != self._last_width:
            self.refresh_item()


class _Expandable(_InChatItem):
    """A tool or agent item: one line collapsed, a bordered box with the full
    output expanded (the ``-expanded`` class carries the border)."""

    def __init__(self, classes: str, expanded: bool) -> None:
        super().__init__(f"{classes} -expanded" if expanded else classes)
        self.expanded = expanded

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        self.set_class(expanded, "-expanded")
        self.refresh_item()


class ThinkingItem(_InChatItem):
    """One reasoning phase, a bordered box in the chat. It grows with the text up
    to ``_THINK_ROWS`` tail rows, then stays that tall and shows the tail. When
    thinking ends the box stays as it is and only its header changes. Ctrl+T
    swaps the tail for the full reasoning text."""

    def __init__(self, expanded: bool, started: float, text: str) -> None:
        super().__init__("thinking-item")
        self.text = text
        self.expanded = expanded
        self.started = started
        self.finished: float | None = None
        self.live = True
        self._dirty = True

    def _elapsed(self) -> float:
        return (self.finished or time.monotonic()) - self.started

    def add_text(self, delta: str) -> None:
        self.text += delta
        self._dirty = True  # rendered by tick(), not per delta

    def tick(self) -> None:
        if self._dirty:
            self._dirty = False
            self.refresh_item()
        else:
            super().tick()

    def finish(self) -> None:
        self.finished = time.monotonic()
        self.live = False
        self.refresh_item()

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        self.refresh_item()

    def _build(self, width: int) -> Content:
        secs = _fmt_secs(self._elapsed())
        if self.finished is None:
            title = f"∴ thinking… {secs}"
        else:
            verb = "collapse" if self.expanded else "expand"
            title = f"∴ thought for {secs} · Ctrl+T to {verb}"
        head = Content.styled(title, "dim")
        if self.expanded:
            return Content("\n").join([head, Content(self.text.strip())])
        return Content("\n").join([head, *_tail_rows(self.text, width, _THINK_ROWS)])


def _one_line(
    name: str, state: tuple[str, str], args: str, suffix: str, width: int
) -> Content:
    """``● name ✓ ok {args} · 168 lines``; the args give way to fit the width."""
    head = Content.assemble(("● ", state[1]), (name, "bold $accent"), " ", state)
    tail = Content.styled(suffix, "dim")
    budget = width - head.cell_length - tail.cell_length - 1
    if args and budget >= 4:
        return Content.assemble(
            head, " ", Content.styled(args, "dim").truncate(budget, ellipsis=True), tail
        )
    return Content.assemble(head, tail)


class ToolBox(_Expandable):
    """One tool call, mounted when the call starts and updated in place."""

    def __init__(self, name: str, arguments: dict, expanded: bool) -> None:
        super().__init__("toolbox running", expanded)
        self.tool_name = name
        self.arguments = arguments
        self.result: str | None = None

    def update_call(self, name: str, arguments: dict) -> None:
        # The loop announces a call by name first and again once the arguments are in.
        self.tool_name = name or self.tool_name
        self.arguments = arguments or self.arguments
        self.refresh_item()

    def finish(self, result: str) -> None:
        self.result = result
        self.remove_class("running")
        if result.lstrip().startswith("Error"):
            self.add_class("-error")
        self.refresh_item()

    def _build(self, width: int) -> Content:
        if self.result is None:
            state = ("… running", "$warning")
        elif self.has_class("-error"):
            state = ("✗ error", "$error")
        else:
            state = ("✓ ok", "$success")
        args = (
            json.dumps(self.arguments, separators=(",", ":"), ensure_ascii=False, default=str)
            if self.arguments
            else ""
        )
        lines = (self.result or "").splitlines()
        if not self.expanded:
            n = len(lines)
            suffix = f" · {n} line{'s' if n != 1 else ''}" if n else ""
            return _one_line(self.tool_name, state, args, suffix, width)
        header = Content.assemble(
            (self.tool_name, "bold $accent"), " ", state, (f" {args}", "dim") if args else ""
        ).truncate(width, ellipsis=True)
        return Content("\n").join([header, *_full_lines(self.result or "")])


class AgentBox(_Expandable):
    """One agent run with a ticking status line, then its result."""

    def __init__(self, name: str, expanded: bool) -> None:
        super().__init__("agentbox running", expanded)
        self.agent_name = name
        self.started = time.monotonic()
        self.finished: float | None = None
        self.status = "running"
        self.result = ""
        self.tool_ids: set[str] = set()
        self.assignment: str | None = None  # AgentRegistry.run_label, set by the first event
        self.live = True

    def _elapsed(self) -> float:
        return (self.finished or time.monotonic()) - self.started

    def set_assignment(self, label: str | None) -> None:
        if label and not self.assignment:
            self.assignment = label
            self.refresh_item()

    def note_tool(self, call_id: str) -> None:
        if call_id not in self.tool_ids:
            self.tool_ids.add(call_id)
            self.refresh_item()

    def finish(self, result: str, status: str) -> None:
        self.finished = time.monotonic()
        self.live = False
        self.status = status
        self.result = result or ""
        self.remove_class("running")
        if status not in ("done", "completed"):
            self.add_class("-error")
        self.refresh_item()

    def _build(self, width: int) -> Content:
        secs = _fmt_secs(self._elapsed())
        n = len(self.tool_ids)
        tools = f" · {n} tool{'s' if n != 1 else ''}"
        if self.finished is None:
            state = (f"running {secs}", "$warning")
        elif self.status in ("done", "completed"):
            state = (f"✓ done {secs}", "$success")
        else:
            state = (f"✗ failed {secs}", "$error")
        label = f"— {self.assignment}" if self.assignment else ""
        if not self.expanded:
            return _one_line(self.agent_name, state, label, tools, width)
        head = Content.assemble(
            (self.agent_name, "bold $accent"), " ", state,
            (f" {label}", "dim") if label else "", (tools, "dim"),
        ).truncate(width, ellipsis=True)
        return Content("\n").join([head, *_full_lines(self.result)])


class ChatView(VerticalScroll):
    """
    CLI-style chat display.
    Simple text output with prefixes instead of panels.
    """

    messages: reactive[list] = reactive(list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._message_widgets: list[Static | AssistantReply] = []
        self._thinking_visible: bool = False
        # In-chat items (see the methods below the message ones).
        self._thinking_item: ThinkingItem | None = None
        self._thinking_started = 0.0
        self._thinking_pending = ""
        self._tool_boxes: dict[str, ToolBox] = {}
        self._agent_boxes: dict[int, AgentBox] = {}
        self._thinking_expanded = False
        self._tools_expanded = False
        self._agents_expanded = False

    def on_mount(self) -> None:
        """Anchor to the bottom: follow the end of the chat.

        Textual's public ``Widget.anchor()`` keeps an anchored widget pinned to
        its end as content arrives or the size changes. Scrolling up releases
        the anchor; scrolling back to the end re-arms it.
        """
        self.anchor()

    def page_down(self) -> None:
        """Scroll one page down; at the end, do nothing.

        Textual releases the anchor on any scroll and re-arms it only when the
        scroll position changes, so a scroll that lands where it already is (down
        at the end) would leave the chat un-anchored and the next content would
        not be followed.
        """
        if not self.is_vertical_scroll_end:
            self.scroll_page_down(animate=False)

    def line_down(self) -> None:
        """Scroll one line down; at the end, do nothing (see ``page_down``)."""
        if not self.is_vertical_scroll_end:
            self.scroll_down(animate=False)

    def action_page_down(self) -> None:
        self.page_down()

    def action_scroll_down(self) -> None:
        self.line_down()

    def disable_follow_mode(self) -> None:
        """Stop following the end (user is reading history)."""
        self.release_anchor()

    def enable_follow_mode(self) -> None:
        """Follow the end again and jump to it."""
        self.anchor()

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

                if isinstance(last_widget, AssistantReply):
                    last_widget.set_text(
                        _sanitize_for_assistant_render(full_content).strip()
                    )
                else:
                    text = self._create_text(full_content, msg_type, metadata)
                    if text:
                        last_widget.update(text)
                return

        self.messages.append(
            {"content": content, "type": msg_type, "metadata": metadata}
        )

        if msg_type == MessageType.ASSISTANT:
            reply = AssistantReply(
                _sanitize_for_assistant_render(content).strip(),
                classes=f"message {msg_type.value}",
            )
            self._message_widgets.append(reply)
            self.mount(reply)
        else:
            text = self._create_text(content, msg_type, metadata)
            if text:
                msg_widget = Static(text, classes=f"message {msg_type.value}")
                self._message_widgets.append(msg_widget)
                self.mount(msg_widget)
                # Hide thinking blocks by default
                if msg_type == MessageType.THINKING and not self._thinking_visible:
                    msg_widget.display = False

    # ── Thinking, tool calls and agent runs, drawn in the chat in order ──

    def _add_item(self, item: Static, msg_type: MessageType) -> None:
        """Mount an in-chat item in order. Registering it in ``messages`` also
        stops the next assistant chunk from merging into a reply above it."""
        self.messages.append({"content": "", "type": msg_type, "metadata": {"inchat": True}})
        self._message_widgets.append(item)
        self.mount(item)

    def start_thinking(self) -> None:
        """A reasoning phase begins. The item is mounted with the first reasoning
        text, so a phase with none leaves no trace."""
        self._thinking_started = time.monotonic()
        self._thinking_pending = ""

    def add_thinking_text(self, text: str) -> None:
        if self._thinking_item is None:
            self._thinking_pending += text
            if not self._thinking_pending.strip():
                return
            item = ThinkingItem(
                self._thinking_expanded, self._thinking_started, self._thinking_pending
            )
            self._thinking_item = item
            self._add_item(item, MessageType.THINKING)
            return
        self._thinking_item.add_text(text)

    def stop_thinking(self) -> None:
        if self._thinking_item is not None:
            self._thinking_item.finish()
            self._thinking_item = None
        self._thinking_pending = ""

    def tool_started(self, call_id: str, name: str, arguments: dict) -> None:
        box = self._tool_boxes.get(call_id)
        if box is not None:
            box.update_call(name, arguments)
            return
        box = ToolBox(name, arguments, self._tools_expanded)
        self._tool_boxes[call_id] = box
        self._add_item(box, MessageType.TOOL_CALL)

    def tool_completed(self, call_id: str, result: str) -> None:
        box = self._tool_boxes.get(call_id)
        if box is not None:
            box.finish(str(result))

    def _agent_box(self, run_id: int, name: str) -> AgentBox:
        box = self._agent_boxes.get(run_id)
        if box is None:
            box = AgentBox(name, self._agents_expanded)
            self._agent_boxes[run_id] = box
            self._add_item(box, MessageType.TOOL_CALL)
        return box

    def agent_event(
        self, run_id: int, name: str, event: str, data: Any = None,
        assignment: str | None = None,
    ) -> None:
        """An agent progress event; the first one for a run mounts its box.
        ``assignment`` is the run's label; the first one given is kept."""
        box = self._agent_box(run_id, name)
        box.set_assignment(assignment)
        if event == "tool_start" and isinstance(data, dict):
            box.note_tool(str(data.get("call_id") or data.get("name") or ""))

    def agent_completed(self, run_id: int, name: str, result: str, status: str) -> None:
        self._agent_box(run_id, name).finish(result, status)

    def tick_live_items(self) -> None:
        """Refresh running items (elapsed seconds); called by the activity timer."""
        for item in self._message_widgets:
            if isinstance(item, _InChatItem) and item.live:
                item.tick()

    def toggle_thinking_expanded(self) -> bool:
        self._thinking_expanded = not self._thinking_expanded
        for item in self._message_widgets:
            if isinstance(item, ThinkingItem):
                item.set_expanded(self._thinking_expanded)
        return self._thinking_expanded

    def toggle_tools_expanded(self, agents: bool = True) -> bool:
        """Ctrl+O: every tool box (and, with ``agents``, every agent box)."""
        self._tools_expanded = not self._tools_expanded
        if agents:
            self._agents_expanded = self._tools_expanded
        for item in self._message_widgets:
            if isinstance(item, ToolBox):
                item.set_expanded(self._tools_expanded)
            elif agents and isinstance(item, AgentBox):
                item.set_expanded(self._agents_expanded)
        return self._tools_expanded

    def toggle_agents_expanded(self) -> bool:
        self._agents_expanded = not self._agents_expanded
        for item in self._message_widgets:
            if isinstance(item, AgentBox):
                item.set_expanded(self._agents_expanded)
        return self._agents_expanded

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
        self._thinking_item = None
        self._thinking_pending = ""
        self._tool_boxes.clear()
        self._agent_boxes.clear()


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
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.disable_follow_mode()
            chat_view.scroll_page_up(animate=False)
            return

        if event.key == "pagedown":
            event.prevent_default()
            event.stop()
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.page_down()
            return

        if event.key == "ctrl+pageup":
            event.prevent_default()
            event.stop()
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.disable_follow_mode()
            chat_view.scroll_up(animate=False)
            return

        if event.key == "ctrl+pagedown":
            event.prevent_default()
            event.stop()
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.line_down()
            return

        if event.key == "home":
            event.prevent_default()
            event.stop()
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.disable_follow_mode()
            chat_view.scroll_home(animate=False)
            return

        if event.key == "end":
            event.prevent_default()
            event.stop()
            chat_view = self.app.query_one("#chat-view", ChatView)
            chat_view.enable_follow_mode()
            return

        self._reset_tab_cycle()

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
            except Exception:  # noqa: BLE001 - history file boundary: an unreadable history file starts an empty history
                logger.opt(exception=True).debug(
                    "Failed to load chat history file; starting with empty history"
                )
        return []

    def _save_to_history(self, command: str) -> None:
        """Append command to history file."""
        try:
            with open(self._history_file, "a", encoding="utf-8") as f:
                f.write(command + "\n")
        except Exception:  # noqa: BLE001 - history file boundary: a failed append must never block submitting the command
            logger.opt(exception=True).debug(
                "Failed to append to the chat history file"
            )

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


_STATUS_SEP = " | "


def _abbreviate_home(path: Path | str) -> str:
    """Show a path with the home directory as ``~`` (``~`` itself for home)."""
    path = Path(path)
    try:
        relative = path.relative_to(Path.home())
    except (ValueError, RuntimeError):  # not under home, or no home to compare to
        return str(path)
    return "~" if not relative.parts else f"~/{relative.as_posix()}"


def _shorten_left(text: str, width: int) -> str:
    """Fit a path into ``width`` cells, dropping leading components for ``…``.

    ``~/Vscode/ayder-cli/src`` in 15 cells becomes ``…/ayder-cli/src``. When even
    the last component is too wide, its tail is kept: ``…ongname``.
    """
    if width <= 0:
        return ""
    if cell_len(text) <= width:
        return text
    parts = [part for part in text.split("/") if part]
    if width == 1 or not parts:
        return "…"
    kept: list[str] = []
    for part in reversed(parts):
        if cell_len("…/" + "/".join([part, *kept])) > width:
            break
        kept.insert(0, part)
    if kept:
        return "…/" + "/".join(kept)
    return "…" + parts[-1][-(width - 1):]


class _CwdLabel(Label):
    """The working directory, shortened from the left to the width it is given."""

    def __init__(self, display: str, **kwargs):
        super().__init__("", **kwargs)
        self.display_text = display

    def get_content_width(self, container: Size, viewport: Size) -> int:
        """Width from the path and the bar alone, never from the other items.

        The path is shortened from the left to at most a third of the bar, but
        never below ``…/<last component>`` (or the whole path, if shorter). The
        items on its right may overflow the bar; the cwd stays visible.
        """
        sep = cell_len(_STATUS_SEP)
        last = self.display_text.rsplit("/", 1)[-1]
        budget = max(container.width // 3, cell_len(f"…/{last}"))
        shown = _shorten_left(self.display_text, min(budget, container.width - sep))
        return cell_len(shown) + sep

    def render(self) -> Text:
        room = self.size.width - cell_len(_STATUS_SEP)
        if room < 1:
            return Text("")
        return Text(_shorten_left(self.display_text, room) + _STATUS_SEP)


class StatusBar(Horizontal):
    """
    CLI-style status bar showing context info.
    """

    def __init__(
        self,
        model: str = "default",
        permissions: set | None = None,
        effort: str = "default",
        cwd: Path | str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._cwd_display = _abbreviate_home(cwd if cwd is not None else Path.cwd())
        self.model = model
        self.effort = effort
        self.token_count = 0
        self.active_files: list[str] = []
        self._permissions = permissions or {"r"}

    def compose(self) -> ComposeResult:
        mode_str = "".join(sorted(self._permissions))
        yield _CwdLabel(self._cwd_display, id="cwd-label")
        yield Label(markup_or_plain(f"model: {self.model}"), id="model-label")
        yield Label(f" | effort: {self.effort}", id="effort-label")
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

    def set_effort(self, effort: str) -> None:
        """Update the effort displayed immediately after the model."""
        self.effort = effort
        self.query_one("#effort-label", Label).update(f" | effort: {effort}")

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
        except Exception:  # noqa: BLE001 - badge filter guard: unreadable tool tags render badges unfiltered rather than killing the app
            logger.opt(exception=True).debug(
                "Could not read enabled tool tags; badges rendered unfiltered"
            )
            return None

    def refresh_plugin_badges(self) -> None:
        """Re-render plugin status badges, greying out any disabled via /plugin."""
        from ayder_cli.tools import plugin_status

        try:
            label = self.query_one("#plugin-badges", Label)
        except NoMatches:
            return  # not mounted yet
        except Exception:  # noqa: BLE001 - badge lookup guard: residual after NoMatches; badge rendering is cosmetic
            logger.opt(exception=True).debug("Plugin badge label lookup failed")
            return
        label.update(self._render_badges(plugin_status.get_all(), self._enabled_tags()))
