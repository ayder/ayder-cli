"""
AyderApp — main Textual application for ayder-cli TUI.

Contains init, compose, AppCallbacks, and UI actions.
LLM pipeline and tool execution are delegated to TuiChatLoop.
Command handlers are in tui.commands.
"""

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.worker import get_current_worker
from textual.timer import Timer
from textual import on
from pathlib import Path
from typing import Any
import asyncio
import difflib

from ayder_cli.application.runtime_factory import create_runtime
from ayder_cli.core.config import Config
from ayder_cli.logging_config import (
    get_effective_log_level,
    is_logging_configured,
    setup_logging,
)
from ayder_cli.tui.helpers import create_tui_banner
from ayder_cli.tui.theme_manager import get_theme_css
from ayder_cli.tui.types import ConfirmResult
from ayder_cli.tui.screens import CLIConfirmScreen
from ayder_cli.tui.widgets import (
    ChatView,
    ToolPanel,
    ActivityBar,
    CLIInputBar,
    StatusBar,
)
from ayder_cli.tui.commands import COMMAND_MAP, do_clear
from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig


class AppCallbacks:
    """Implements TuiCallbacks by dispatching to Textual widgets."""

    def __init__(self, app: "AyderApp") -> None:
        self._app = app
        self._worker: Any | None = None

    def on_thinking_start(self) -> None:
        activity = self._app.query_one("#activity-bar", ActivityBar)
        activity.set_thinking(True)
        self._app._start_activity_timer()

    def on_thinking_stop(self) -> None:
        activity = self._app.query_one("#activity-bar", ActivityBar)
        activity.set_thinking(False)
        self._app._maybe_stop_activity_timer()

    def on_assistant_content(self, text: str) -> None:
        chat_view = self._app.query_one("#chat-view", ChatView)
        chat_view.add_assistant_message(text)

    def on_thinking_content(self, text: str) -> None:
        chat_view = self._app.query_one("#chat-view", ChatView)
        chat_view.add_thinking_message(text)

    def on_token_usage(self, total_tokens: int) -> None:
        self._app.call_later(
            lambda t=total_tokens: self._app.query_one(
                "#status-bar", StatusBar
            ).update_token_usage(t)
        )

    def on_iteration_update(self, current: int, maximum: int) -> None:
        self._app.call_later(
            lambda c=current, m=maximum: self._app.query_one(
                "#status-bar", StatusBar
            ).update_iterations(c, m)
        )

    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None:
        tool_panel = self._app.query_one("#tool-panel", ToolPanel)
        tool_panel.add_tool(call_id, name, arguments)
        activity = self._app.query_one("#activity-bar", ActivityBar)
        activity.set_tools_working(True)
        self._app._start_activity_timer()

    def on_tool_complete(self, call_id: str, result: str) -> None:
        tool_panel = self._app.query_one("#tool-panel", ToolPanel)
        self._app.call_later(
            lambda tid=call_id, res=result: tool_panel.complete_tool(tid, res)
        )

    def on_tools_cleanup(self) -> None:
        activity = self._app.query_one("#activity-bar", ActivityBar)
        activity.set_tools_working(False)
        self._app._maybe_stop_activity_timer()
        # Schedule panel cleanup after a short delay
        tool_panel = self._app.query_one("#tool-panel", ToolPanel)
        self._app.set_timer(2.0, lambda: tool_panel.clear_completed())

    def on_system_message(self, text: str) -> None:
        chat_view = self._app.query_one("#chat-view", ChatView)
        chat_view.add_system_message(text)

    async def request_confirmation(
        self, name: str, arguments: dict
    ) -> ConfirmResult | None:
        return await self._app._request_confirmation(name, arguments)

    def is_cancelled(self) -> bool:
        if self._worker is None:
            return False
        return self._worker.is_cancelled


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
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+x", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
        ("ctrl+l", "clear", "Clear Chat"),
        ("ctrl+o", "toggle_tools", "Toggle Tools"),
    ]

    def __init__(
        self,
        model: str = "default",
        safe_mode: bool = False,
        permissions: set | None = None,
        iterations: int | None = None,
        **kwargs,
    ):
        """
        Initialize the TUI app.

        Args:
            model: The LLM model name to use
            safe_mode: Whether to enable safe mode
            permissions: Set of granted permission levels ("r", "w", "x")
            iterations: Max agentic iterations per message (None = use config default)
        """
        super().__init__(**kwargs)
        self.safe_mode = safe_mode
        self.permissions = permissions or {"r"}
        self._iterations_override = iterations

        self._pending_messages: list[str] = []
        self._is_processing = False
        self._verbose_mode: bool = False

        # Build all shared runtime components via the factory
        rt = create_runtime()
        self.config = rt.config
        if isinstance(self.config, Config) and not is_logging_configured():
            setup_logging(self.config)
        self._logging_level = get_effective_log_level()

        if isinstance(self.config, dict):
            actual_model = self.config.get("model", model)
        else:
            actual_model = self.config.model
        self.model = actual_model if actual_model != "default" else model

        self.llm = rt.llm_provider
        self._process_manager = rt.process_manager
        self.registry = rt.tool_registry
        self._checkpoint_manager = rt.checkpoint_manager
        self._memory_manager = rt.memory_manager

        self._setup_registry_callbacks()
        self._setup_registry_middleware()

        self.messages: list[dict] = []
        self._init_system_prompt()

        # Initialize command list from tui.commands
        self.commands = sorted(COMMAND_MAP.keys())
        # Add TUI-only commands to autocomplete
        if "/permission" not in self.commands:
            self.commands.append("/permission")

        self._activity_timer: Timer | None = None

        # Create chat loop
        num_ctx = (
            self.config.num_ctx
            if not isinstance(self.config, dict)
            else self.config.get("num_ctx", 65536)
        )
        max_iters = self._iterations_override
        if max_iters is None:
            max_iters = (
                self.config.max_iterations
                if not isinstance(self.config, dict)
                else self.config.get("max_iterations", 50)
            )
        self._callbacks = AppCallbacks(self)
        if isinstance(self.config, dict):
            max_output_tokens = self.config.get("max_output_tokens", 4096)
            stop_sequences = self.config.get("stop_sequences", [])
            tool_tags_list = self.config.get("tool_tags", ["core", "metadata"])
        else:
            max_output_tokens = getattr(self.config, "max_output_tokens", 4096)
            raw_stop = getattr(self.config, "stop_sequences", [])
            stop_sequences = list(raw_stop) if raw_stop is not None else []
            raw_tags = getattr(self.config, "tool_tags", ["core", "metadata"])
            tool_tags_list = list(raw_tags) if raw_tags is not None else []
        tool_tags = frozenset(tool_tags_list) if tool_tags_list else None
        self.chat_loop = TuiChatLoop(
            llm=self.llm,
            registry=self.registry,
            messages=self.messages,
            config=TuiLoopConfig(
                model=self.model,
                num_ctx=num_ctx,
                max_output_tokens=max_output_tokens,
                stop_sequences=stop_sequences,
                max_iterations=max_iters,
                permissions=self.permissions,
                tool_tags=tool_tags,
            ),
            callbacks=self._callbacks,
            checkpoint_manager=self._checkpoint_manager,
            memory_manager=self._memory_manager,
        )

    def _init_system_prompt(self) -> None:
        """Build and set the system prompt with project structure."""
        from ayder_cli.prompts import SYSTEM_PROMPT, TOOL_PROTOCOL_BLOCK, PROJECT_STRUCTURE_MACRO_TEMPLATE

        try:
            structure = self.registry.execute("get_project_structure", {"max_depth": 3})
            macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
        except Exception:
            macro = ""

        driver = self.config.driver if not isinstance(self.config, dict) else self.config.get("driver", "openai")
        tool_protocol = TOOL_PROTOCOL_BLOCK if driver in ("openai", "ollama") else ""
        system_prompt = SYSTEM_PROMPT + tool_protocol + macro
        self.messages.append({"role": "system", "content": system_prompt})

    def update_system_prompt_model(self) -> None:
        """Update the model name in the system prompt after /model switch."""
        from ayder_cli.prompts import SYSTEM_PROMPT, TOOL_PROTOCOL_BLOCK, PROJECT_STRUCTURE_MACRO_TEMPLATE

        if self.messages and self.messages[0].get("role") == "system":
            try:
                structure = self.registry.execute(
                    "get_project_structure", {"max_depth": 3}
                )
                macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(
                    project_structure=structure
                )
            except Exception:
                macro = ""
            driver = self.config.driver if not isinstance(self.config, dict) else self.config.get("driver", "openai")
            tool_protocol = TOOL_PROTOCOL_BLOCK if driver in ("openai", "ollama") else ""
            self.messages[0]["content"] = SYSTEM_PROMPT + tool_protocol + macro

    def _animate_activity(self) -> None:
        """Animate spinners in the activity bar and tool panel."""
        activity = self.query_one("#activity-bar", ActivityBar)
        activity.update_spinners()
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        tool_panel.update_spinners()

    def _start_activity_timer(self) -> None:
        """Start the shared activity animation timer if not running."""
        if not self._activity_timer:
            self._activity_timer = self.set_interval(0.1, self._animate_activity)

    def _maybe_stop_activity_timer(self) -> None:
        """Stop the activity timer if nothing is active."""
        activity = self.query_one("#activity-bar", ActivityBar)
        if not activity._thinking and not activity._tools_working:
            if self._activity_timer:
                self._activity_timer.stop()
                self._activity_timer = None

    def _setup_registry_callbacks(self) -> None:
        """Setup callbacks for tool registry.

        Note: Registry callbacks run inside asyncio.to_thread() (background thread),
        so they MUST NOT mount widgets on the ChatView (not thread-safe in Textual).
        Tool call/result display is handled by the ToolPanel and by TuiChatLoop
        which runs on the main event loop.
        """
        pass

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

    def _generate_diff(self, tool_name: str, arguments: dict) -> str | None:
        """Generate a diff preview for file-modifying tools."""
        file_modifying_tools = {
            "write_file",
            "replace_string",
            "insert_line",
            "delete_line",
        }
        if tool_name not in file_modifying_tools:
            return None

        file_path = arguments.get("file_path", "")
        try:
            path = Path(file_path)
            if not path.exists():
                if tool_name == "write_file":
                    new_content = arguments.get("content", "")
                    return "\n".join(f"+{line}" for line in new_content.split("\n"))
                return None

            original = path.read_text(encoding="utf-8")
            original_lines = original.splitlines(keepends=True)

            if tool_name == "write_file":
                new_content = arguments.get("content", "")
                new_lines = new_content.splitlines(keepends=True)
            elif tool_name == "replace_string":
                old_string = arguments.get("old_string", "")
                new_string = arguments.get("new_string", "")
                new_content = original.replace(old_string, new_string, 1)
                new_lines = new_content.splitlines(keepends=True)
            elif tool_name == "insert_line":
                line_num = arguments.get("line_number", 1)
                content = arguments.get("content", "")
                lines = list(original_lines)
                idx = max(0, min(line_num - 1, len(lines)))
                lines.insert(idx, content + "\n")
                new_lines = lines
            elif tool_name == "delete_line":
                line_num = arguments.get("line_number", 1)
                lines = list(original_lines)
                idx = line_num - 1
                if 0 <= idx < len(lines):
                    lines.pop(idx)
                new_lines = lines
            else:
                return None

            diff = difflib.unified_diff(
                original_lines,
                new_lines,
                fromfile=f"a/{path.name}",
                tofile=f"b/{path.name}",
                lineterm="",
            )
            return "\n".join(diff) or None

        except Exception:
            return None

    async def _request_confirmation(
        self, tool_name: str, arguments: dict
    ) -> ConfirmResult | None:
        """Push CLIConfirmScreen and await the user's response.

        Since async workers run in the app's event loop (same thread),
        we use asyncio.Event + push_screen callback instead of call_from_thread.
        """
        from ayder_cli.ui import describe_tool_action

        event = asyncio.Event()
        result_holder: list[ConfirmResult | None] = [None]

        description = describe_tool_action(tool_name, arguments)
        diff_content = self._generate_diff(tool_name, arguments)

        def on_result(result):
            result_holder[0] = result
            event.set()

        self.push_screen(
            CLIConfirmScreen(
                title=tool_name,
                description=description,
                diff_content=diff_content,
                action_name=description,
            ),
            on_result,
        )

        await event.wait()
        return result_holder[0]

    def compose(self) -> ComposeResult:
        """Compose the UI layout - terminal style with scrolling content."""
        yield ChatView(id="chat-view")
        yield ToolPanel(id="tool-panel")
        yield ActivityBar(id="activity-bar")
        yield CLIInputBar(commands=self.commands, id="input-bar")
        yield StatusBar(model=self.model, permissions=self.permissions, id="status-bar")

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = f"ayder - {self.model}"

        # Show the banner as scrollable content in the chat view
        chat_view = self.query_one("#chat-view", ChatView)
        banner = create_tui_banner(self.model)
        self._banner_spacer = Static("", id="banner-spacer")
        chat_view.mount(self._banner_spacer)
        chat_view.mount(Static(banner, classes="banner-content"))

        # After layout is computed, size the spacer to push the banner near the input
        self.call_after_refresh(self._position_banner)

    def _position_banner(self) -> None:
        """Size the top spacer so the banner sits just above the input bar."""
        chat_view = self.query_one("#chat-view", ChatView)
        viewport_h = chat_view.size.height
        # Sum the height of all children except the spacer
        content_h = sum(
            child.size.height
            for child in chat_view.children
            if child.id != "banner-spacer"
        )
        spacer_h = max(0, viewport_h - content_h)
        self._banner_spacer.styles.height = spacer_h
        chat_view.scroll_end(animate=False)

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

        self.start_llm_processing()

    def start_llm_processing(self, *, no_tools: bool = False) -> None:
        """Launch the chat loop worker.

        Called from _process_next_message and from command handlers.
        """
        self.run_worker(self._run_chat_loop(no_tools=no_tools), exclusive=True)

    async def _run_chat_loop(self, *, no_tools: bool = False) -> None:
        """Thin wrapper: sets worker on callbacks, runs loop, finishes."""
        worker = get_current_worker()
        self._callbacks._worker = worker
        try:
            await self.chat_loop.run(no_tools=no_tools)
        except Exception as e:
            if not worker.is_cancelled:
                chat_view = self.query_one("#chat-view", ChatView)
                chat_view.add_system_message(f"Error: {e}")
        finally:
            if not worker.is_cancelled:
                self.call_later(self._finish_processing)

    def _handle_command(self, cmd: str) -> None:
        """Handle slash commands - dispatch to tui.commands handlers."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_user_message(cmd)

        parts = cmd.split(None, 1)
        cmd_name = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""

        try:
            handler = COMMAND_MAP.get(cmd_name)
            if handler:
                handler(self, cmd_args, chat_view)
            else:
                chat_view.add_system_message(
                    f"Unknown command: {cmd_name}. Type /help for available commands."
                )
        except Exception as e:
            chat_view.add_system_message(f"Command error: {type(e).__name__}: {e}")

    def _finish_processing(self) -> None:
        """Finish processing - clear activity bar and process next message."""
        if self._activity_timer:
            self._activity_timer.stop()
            self._activity_timer = None

        activity = self.query_one("#activity-bar", ActivityBar)
        activity.clear()

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.focus_input()

        if self._pending_messages:
            self._process_next_message()
        else:
            self._is_processing = False

    def action_cancel(self) -> None:
        """Cancel current operation."""
        if self._activity_timer:
            self._activity_timer.stop()
            self._activity_timer = None

        for worker in self.workers:
            worker.cancel()

        activity = self.query_one("#activity-bar", ActivityBar)
        activity.clear()

        pending_count = len(self._pending_messages)
        self._pending_messages.clear()
        self._is_processing = False

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.focus_input()
        chat_view = self.query_one("#chat-view", ChatView)
        if pending_count > 0:
            chat_view.add_system_message(
                f"Operation cancelled ({pending_count} pending messages cleared)."
            )
        else:
            chat_view.add_system_message("Operation cancelled.")

    def action_toggle_tools(self) -> None:
        """Toggle the tool context panel."""
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        visible = tool_panel.toggle()
        chat_view = self.query_one("#chat-view", ChatView)
        state = "visible" if visible else "hidden"
        chat_view.add_system_message(f"Tool panel {state} (Ctrl+O to toggle)")

    def action_clear(self) -> None:
        """Clear chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        do_clear(self, chat_view)
