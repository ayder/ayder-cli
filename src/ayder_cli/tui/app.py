"""
AyderApp — main Textual application for ayder-cli TUI.

Contains init, compose, AppCallbacks, and UI actions.
LLM pipeline and tool execution are delegated to ChatLoop.
Command handlers are in tui.commands.
"""

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.timer import Timer
from textual import on
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import asyncio
import difflib
import logging

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
from ayder_cli.tui.screens import CLIConfirmScreen, CLIHelpScreen
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.tool import (
    AGENT_TOOL_DEFINITION,
    create_agent_handler,
)
from ayder_cli.tui.widgets import (
    AgentPanel,
    ChatView,
    ThinkingPanel,
    ToolPanel,
    ActivityBar,
    CLIInputBar,
    StatusBar,
)
from ayder_cli.tui.commands import COMMAND_MAP, do_clear
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

logger = logging.getLogger(__name__)


@dataclass
class TurnRequest:
    """A single queued unit of work for the serial turn consumer.

    ``prepare`` runs while no turn is active (quiescent); if ``run_loop`` is
    True the consumer then starts one ``ChatLoop.run()`` and awaits its full
    teardown before pulling the next request.
    """

    prepare: Callable[[], None] | None = None
    run_loop: bool = True
    no_tools: bool = False


class AppCallbacks:
    """Implements TuiCallbacks by dispatching to Textual widgets."""

    def __init__(self, app: "AyderApp") -> None:
        self._app = app
        self._cancel_event: asyncio.Event | None = None

    def on_thinking_start(self) -> None:
        activity = self._app.query_one("#activity-bar", ActivityBar)
        activity.set_thinking(True)
        # Separate this reasoning phase from any earlier one in the same turn.
        self._app.query_one("#thinking-panel", ThinkingPanel).start_phase()
        self._app._start_activity_timer()

    def on_thinking_stop(self) -> None:
        activity = self._app.query_one("#activity-bar", ActivityBar)
        activity.set_thinking(False)
        # Transition to "Generating" so the user sees activity while content streams
        activity.set_generating(True)

    def on_assistant_content(self, text: str) -> None:
        chat_view = self._app.query_one("#chat-view", ChatView)
        chat_view.add_assistant_message(text)

    def on_thinking_content(self, text: str) -> None:
        # Reasoning streams silently into the dedicated panel (Ctrl+T to view),
        # the same way tools stream into the tool panel. The ActivityBar spinner
        # provides ambient "Thinking..." status in the meantime.
        self._app.query_one("#thinking-panel", ThinkingPanel).add_thinking(text)

    def on_token_usage(self, total_tokens: int) -> None:
        # Show LIVE context-window fill (current / window size), not the
        # cumulative session counter. The context manager's stats were just
        # refreshed via update_from_response before this callback fired.
        cm = getattr(self._app, "context_manager", None)
        if cm is None or not hasattr(cm, "get_stats"):
            return
        try:
            stats = cm.get_stats()
            used = int(stats.total_tokens)
            total = int(stats.total_tokens + stats.available_tokens)
        except Exception:
            return
        self._app.call_later(
            lambda u=used, t=total: self._app.query_one(
                "#status-bar", StatusBar
            ).update_context_usage(u, t)
        )

    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None:
        tool_panel = self._app.query_one("#tool-panel", ToolPanel)
        tool_panel.add_tool(call_id, name, arguments)
        activity = self._app.query_one("#activity-bar", ActivityBar)
        activity.set_generating(False)
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
        activity.set_generating(False)
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
        ev = self._cancel_event
        return ev is not None and ev.is_set()


def _enable_installed_plugin_tags(tool_tags, plugin_defs, status_names) -> frozenset | None:
    """Auto-enable installed plugins' capability tags at startup.

    A plugin the user deliberately installed (e.g. mcp-tool) should work without a
    manual /plugin toggle, so its capability tags are merged into the effective
    ``tool_tags``. Tags come from loaded plugin tool definitions and from any
    status badge a plugin published (so an installed-but-disconnected plugin like
    mcp-tool is still enabled). Builtin/optional tags stay governed by config.

    ``tool_tags`` of ``None`` means "no filter / everything enabled" — left as-is.
    """
    if tool_tags is None:
        return None
    extra = {
        tag
        for td in plugin_defs
        for tag in td.tags
        if tag not in ("core", "metadata")
    }
    extra.update(name for name in status_names if name not in ("core", "metadata"))
    return frozenset(tool_tags | extra) if extra else tool_tags


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
    ENABLE_MOUSE_SUPPORT = False

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+x", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
        ("ctrl+l", "clear", "Clear Chat"),
        ("ctrl+o", "toggle_tools", "Toggle Tools"),
        ("ctrl+t", "toggle_thinking", "Toggle Thinking"),
        ("ctrl+g", "toggle_agents", "Toggle Agents"),
        ("ctrl+h", "show_help", "Help"),
        ("pageup", "scroll_chat_up", "Scroll Up"),
        ("pagedown", "scroll_chat_down", "Scroll Down"),
    ]

    def __init__(
        self,
        model: str = "default",
        safe_mode: bool = False,
        permissions: set | None = None,
        agent_mode: bool = False,
        system_prompt_override: str | None = None,
        **kwargs,
    ):
        """
        Initialize the TUI app.

        Args:
            model: The LLM model name to use
            safe_mode: Whether to enable safe mode
            permissions: Set of granted permission levels ("r", "w", "x")
            agent_mode: When True, drive the multi-agent harness — inject the
                AGENTIC orchestrator system prompt (ayder-cli --agent).
            system_prompt_override: When set, use this text as the system-prompt base
                instead of the built-in prompts.py prompt (ayder --system-prompt FILE).
        """
        super().__init__(**kwargs)
        self.safe_mode = safe_mode
        self.permissions = permissions or {"r"}
        self._system_prompt_override = system_prompt_override

        self._requests: asyncio.Queue[TurnRequest] = asyncio.Queue()
        self._run_task: asyncio.Task | None = None
        self._cancel_event: asyncio.Event | None = None
        self._verbose_mode: bool = False
        self._show_thinking: bool = False
        self._active_skill: str | None = None

        # Build all shared runtime components via the factory
        rt = create_runtime(prompt_tier="AGENTIC" if agent_mode else None)
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
        self.registry.app = self
        self.context_manager = rt.context_manager
        self._pending_compact: dict | None = None

        # Wire up debug logging for verbose mode
        from ayder_cli.tui.adapter import TUIInteractionSink
        
        def on_llm_debug(messages, model, tools, options):
            num_msg = len(messages) if messages else 0
            num_tools = len(tools) if tools else 0
            chat_view = self.query_one("#chat-view", ChatView)
            chat_view.add_system_message(
                f"[DEBUG] LLM Request: {model} | {num_msg} messages | {num_tools} tools"
            )

        if hasattr(self.llm, "interaction_sink"):
            self.llm.interaction_sink = TUIInteractionSink(
                on_llm_request_debug_cb=on_llm_debug
            )

        self._setup_registry_callbacks()
        self._setup_registry_middleware()

        self.messages: list[dict] = []
        self._init_system_prompt()

        # Initialize agent registry if agents are configured (Part 1)
        self._agent_registry: AgentRegistry | None = None
        if hasattr(self.config, 'agents') and isinstance(self.config.agents, dict) and self.config.agents:
            def _agent_progress(run_id, name, event, data):
                """Forward agent events to AgentPanel and sync activity bar."""
                try:
                    panel = self.query_one("#agent-panel", AgentPanel)
                    label = self._agent_registry.run_label(run_id) if self._agent_registry else None
                    self.call_later(lambda: panel.update_agent(run_id, name, event, data, label))
                except Exception:
                    pass
                # Keep activity bar agent count in sync and ensure spinner animates
                try:
                    activity = self.query_one("#activity-bar", ActivityBar)
                    count = self._agent_registry.active_count if self._agent_registry else 0
                    self.call_later(lambda: activity.set_agents_running(count))
                    self.call_later(self._start_activity_timer)
                except Exception:
                    pass

            def _agent_complete(run_id, run):
                """Handle agent completion: update UI and nudge the idle LLM."""
                try:
                    panel = self.query_one("#agent-panel", AgentPanel)
                    self.call_later(lambda: panel.complete_agent(run_id, run.result, run.status))
                except Exception:
                    pass
                try:
                    activity = self.query_one("#activity-bar", ActivityBar)
                    count = self._agent_registry.active_count if self._agent_registry else 0
                    self.call_later(lambda: activity.set_agents_running(count))
                except Exception:
                    pass
                self._maybe_nudge()                 # event-driven nudge (spec §7)

            self._agent_registry = AgentRegistry(
                agents=self.config.agents,
                parent_config=self.config,
                project_ctx=rt.project_ctx,
                process_manager=self._process_manager,
                permissions=self.permissions,
                agent_timeout=getattr(self.config, 'agent_timeout', 600),
                max_concurrent_agents=getattr(self.config, 'max_concurrent_agents', 5),
                on_progress=_agent_progress,
                on_complete=_agent_complete,
            )

            # Register agent tool
            self.registry.register_dynamic_tool(
                AGENT_TOOL_DEFINITION, create_agent_handler(self._agent_registry)
            )

            # Append capability prompts to system prompt
            cap_prompts = self._agent_registry.get_capability_prompts()
            if cap_prompts and self.messages and self.messages[0].get("role") == "system":
                self.messages[0]["content"] += cap_prompts

        # Initialize command list from tui.commands
        self.commands = sorted(COMMAND_MAP.keys())
        # Add TUI-only commands to autocomplete
        if "/permission" not in self.commands:
            self.commands.append("/permission")
        # Add /skill <name> completions from .ayder/skills/
        _skills_dir = Path(".").resolve() / ".ayder" / "skills"
        if _skills_dir.is_dir():
            for _skill_dir in sorted(_skills_dir.iterdir()):
                if _skill_dir.is_dir() and (_skill_dir / "SKILL.md").exists():
                    self.commands.append(f"/skill {_skill_dir.name}")

        self._activity_timer: Timer | None = None

        # Create chat loop
        num_ctx = (
            self.config.num_ctx
            if not isinstance(self.config, dict)
            else self.config.get("num_ctx", 65536)
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
        # Auto-enable installed plugins so they work without a manual /plugin toggle.
        from ayder_cli.tools import plugin_status
        from ayder_cli.tools.definition import _GLOBAL_PLUGIN_DEFS

        tool_tags = _enable_installed_plugin_tags(
            tool_tags, _GLOBAL_PLUGIN_DEFS, plugin_status.get_all().keys()
        )
        self.chat_loop = ChatLoop(
            llm=self.llm,
            registry=self.registry,
            messages=self.messages,
            config=ChatLoopConfig(
                model=self.model,
                provider=self.config.provider,
                num_ctx=num_ctx,
                max_output_tokens=max_output_tokens,
                stop_sequences=stop_sequences,
                permissions=self.permissions,
                tool_tags=tool_tags,
                max_history=getattr(self.config, 'max_history_messages', 0),
            ),
            callbacks=self._callbacks,
            context_manager=self.context_manager,
        )

        existing_hook = self.chat_loop.config.pre_iteration_hook

        async def _composed_pre_iteration(messages):
            await apply_pending_compact(self, messages)

            if existing_hook is not None:
                result = existing_hook(messages)
                if hasattr(result, "__await__"):
                    await result

        self.chat_loop.config.pre_iteration_hook = _composed_pre_iteration

    def _init_system_prompt(self) -> None:
        """Build and set the system prompt with project structure."""
        from ayder_cli.prompts import (
            get_system_prompt,
            PROJECT_STRUCTURE_MACRO_TEMPLATE,
        )

        try:
            structure = self.registry.execute("get_project_structure", {"max_depth": 3})
            macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
        except Exception:
            macro = ""

        if self._system_prompt_override is not None:
            base_prompt = self._system_prompt_override
        else:
            base_prompt = get_system_prompt(self.config.prompt)
        raw_tags = getattr(self.config, "tool_tags", None) if not isinstance(self.config, dict) else self.config.get("tool_tags")
        tags = frozenset(raw_tags) if raw_tags else None
        tool_prompts = self.registry.get_system_prompts(tags=tags)
        system_prompt = base_prompt + tool_prompts + macro
        self.messages.append({"role": "system", "content": system_prompt})

    def update_system_prompt_model(self) -> None:
        """Update the model name in the system prompt after /model switch."""
        from ayder_cli.prompts import (
            get_system_prompt,
            PROJECT_STRUCTURE_MACRO_TEMPLATE,
        )

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
            tags = self.chat_loop.config.tool_tags
            tool_prompts = self.registry.get_system_prompts(tags=tags)
            if self._system_prompt_override is not None:
                base_prompt = self._system_prompt_override
            else:
                base_prompt = get_system_prompt(self.config.prompt)
            self.messages[0]["content"] = base_prompt + tool_prompts + macro

    def inject_skill(self, skill_name: str, skill_content: str) -> None:
        """Inject or replace the active skill system message."""
        from ayder_cli.prompts import SKILL_INJECTION_TEMPLATE

        # Remove previous skill message if any (in place so chat_loop.messages
        # keeps referencing the same list object)
        self.messages[:] = [
            m for m in self.messages
            if not (
                m.get("role") == "system"
                and m.get("content", "").startswith("### ACTIVE SKILL:")
            )
        ]
        block = SKILL_INJECTION_TEMPLATE.format(
            skill_name=skill_name, skill_content=skill_content
        )
        self.messages.append({"role": "system", "content": block})
        self._active_skill = skill_name

    def _animate_activity(self) -> None:
        """Animate spinners in the activity bar and tool panel.

        Both updates are wrapped in a single ``batch_update`` so the 10fps tick
        produces one repaint instead of two, and the tool panel is skipped when
        it is empty — under load (streaming + tools + agents) this keeps the
        per-tick redraw cost (and the flicker that comes with it) down.
        """
        activity = self.query_one("#activity-bar", ActivityBar)
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        with self.batch_update():
            activity.update_spinners()
            if tool_panel._tools:
                tool_panel.update_spinners()

    def _start_activity_timer(self) -> None:
        """Start the shared activity animation timer if not running."""
        if not self._activity_timer:
            self._activity_timer = self.set_interval(0.1, self._animate_activity)

    def _maybe_stop_activity_timer(self) -> None:
        """Stop the activity timer if nothing is active."""
        activity = self.query_one("#activity-bar", ActivityBar)
        if (not activity._thinking and not activity._generating
                and not activity._tools_working and activity._agents_running == 0):
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
        from ayder_cli.tui.helpers import is_tool_blocked_in_safe_mode
        return is_tool_blocked_in_safe_mode(tool_name, self.safe_mode)

    def _generate_diff(self, tool_name: str, arguments: dict) -> str | None:
        """Generate a diff preview for file-modifying tools."""
        if tool_name != "file_editor":
            return None

        file_path = arguments.get("file_path", "")
        operation = arguments.get("operation", "")
        
        try:
            path = Path(file_path)
            if not path.exists():
                if operation == "write":
                    new_content = arguments.get("content", "")
                    return "\n".join(f"+{line}" for line in new_content.split("\n"))
                return None

            original = path.read_text(encoding="utf-8")
            original_lines = original.splitlines(keepends=True)

            if operation == "write":
                new_content = arguments.get("content", "")
                new_lines = new_content.splitlines(keepends=True)
            elif operation == "replace":
                old_string = arguments.get("old_string", "")
                new_string = arguments.get("new_string", "")
                new_content = original.replace(old_string, new_string, 1)
                new_lines = new_content.splitlines(keepends=True)
            elif operation == "insert":
                line_num = arguments.get("line_number", 1)
                content = arguments.get("content", "")
                lines = list(original_lines)
                idx = max(0, min(line_num - 1, len(lines)))
                lines.insert(idx, content + "\n")
                new_lines = lines
            elif operation == "delete":
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
        yield ThinkingPanel(id="thinking-panel")
        yield AgentPanel(id="agent-panel")
        yield ActivityBar(id="activity-bar")
        yield CLIInputBar(commands=self.commands, id="input-bar")
        yield StatusBar(model=self.model, permissions=self.permissions, id="status-bar")

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = f"ayder - {self.model}"

        # Start the single serial turn consumer (owns the turn lifecycle)
        self._engine_task = asyncio.create_task(self._turn_consumer())

        # Set the event loop on the agent registry now that it's running (Part 3)
        if self._agent_registry:
            self._agent_registry.set_loop(asyncio.get_running_loop())
            self.set_interval(1.0, self._maybe_nudge)   # recovery fallback (spec §7)

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
        content_h = sum(
            child.size.height
            for child in chat_view.children
            if child.id != "banner-spacer"
        )
        spacer_h = max(0, viewport_h - content_h)
        self._banner_spacer.styles.height = spacer_h
        chat_view.scroll_end(animate=False)

    @property
    def _is_processing(self) -> bool:
        """Back-compat read of "a turn is running" (was an eager flag)."""
        return self._run_task is not None

    @property
    def is_turn_running(self) -> bool:
        """True while the active turn's ChatLoop.run() coroutine is in flight."""
        return self._run_task is not None

    async def _turn_consumer(self) -> None:
        """Serial owner of the turn lifecycle.

        Pulls one TurnRequest at a time. Runs ``prepare`` while quiescent (no
        turn active), then optionally starts a single ``ChatLoop.run()`` and
        awaits its full teardown (including cancellation) before pulling the
        next request. This is the single point of serialization that replaces
        Textual's non-awaiting ``exclusive=True`` worker.
        """
        while True:
            req = await self._requests.get()
            try:
                if req.prepare is not None:
                    req.prepare()                      # quiescent: no turn running here
            except Exception as e:
                self._report_turn_error(e)
                continue
            if not req.run_loop:
                continue
            self._cancel_event = asyncio.Event()
            callbacks = getattr(self, "_callbacks", None)
            if callbacks is not None:
                callbacks._cancel_event = self._cancel_event
            self._run_task = asyncio.create_task(self.chat_loop.run(no_tools=req.no_tools))
            try:
                await self._run_task
            except asyncio.CancelledError:
                # A cancel targeting the consumer itself (e.g. app shutdown) must
                # terminate the loop; a cancel that only targeted the active turn
                # (Ctrl+C / interrupt) is swallowed so queued requests still run.
                consumer_task = asyncio.current_task()
                if consumer_task is not None and consumer_task.cancelling():
                    raise
            except Exception as e:
                self._report_turn_error(e)
            finally:
                self._run_task = None
                self._after_turn_finished()

    def request_turn(self, prepare: Callable[[], None] | None = None, *,
                     run_loop: bool = True, no_tools: bool = False,
                     interrupt: bool = False) -> None:
        """Enqueue a unit of work for the serial turn consumer.

        ``prepare`` runs when quiescent (no turn active). With ``interrupt`` the
        active turn is cancelled so this request runs sooner; queued requests
        are never discarded.
        """
        self._requests.put_nowait(TurnRequest(prepare, run_loop, no_tools))
        if interrupt and self._run_task is not None:
            cancel_event = getattr(self, "_cancel_event", None)
            if cancel_event is not None:
                cancel_event.set()
            self._run_task.cancel()

    def _report_turn_error(self, exc: Exception) -> None:
        """Surface a turn/prepare error in the chat view (best effort)."""
        try:
            self.query_one("#chat-view", ChatView).add_system_message(f"Error: {exc}")
        except Exception:
            pass

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

    @on(CLIInputBar.Submitted)
    def handle_input_submitted(self, event: CLIInputBar.Submitted) -> None:
        """Handle user input submission.

        Plain messages are echoed immediately but only appended to
        ``self.messages`` inside ``prepare`` (when the consumer is quiescent),
        so message order across messages and commands is unambiguous.
        """
        user_input = event.value
        if user_input.startswith("/"):
            self._handle_command(user_input)
            return
        try:
            self.query_one("#chat-view", ChatView).add_user_message(user_input)  # echo now
            # Start each turn's reasoning fresh in the thinking panel.
            self.query_one("#thinking-panel", ThinkingPanel).clear()
        except Exception:
            pass

        def _prepare(text=user_input):
            if self._agent_registry:
                self._agent_registry.reset_settled()   # finding 5: at turn-prep, not submit
            self.messages.append({"role": "user", "content": text})

        self.request_turn(prepare=_prepare)

    def _after_turn_finished(self) -> None:
        """UI teardown after a turn fully exits; the consumer pulls the next one."""
        self._maybe_stop_activity_timer()
        try:
            self.query_one("#activity-bar", ActivityBar).clear()
            self.query_one("#input-bar", CLIInputBar).focus_input()
        except Exception:
            pass
        if self._agent_registry:
            self._maybe_nudge()

    def _maybe_nudge(self) -> None:
        """Wake the LLM once when it left a finished agent result unread while idle."""
        if self._is_processing or not self._agent_registry:
            return
        pending = self._agent_registry.pending_nudge()
        if not pending:
            return
        n = len(pending)
        text = (
            f"[system] {n} agent result(s) are ready and unread. "
            'Call agent(action="status") then agent(action="read_result", run_id=...) to collect.'
        )

        # Defer the append into the request's prepare so ALL self.messages writes
        # are uniformly deferred — a user message submitted just before this nudge
        # (whose append is also deferred) keeps its submission order.
        def _prepare(msg=text):
            self.messages.append({"role": "user", "content": msg})

        logger.debug("agent nudge: %d unread result(s) -> waking LLM", n)
        self.request_turn(prepare=_prepare)         # serial consumer enqueues the nudge turn
        self._agent_registry.mark_nudged(pending)   # finding A: AFTER enqueue

    def action_cancel(self) -> None:
        """Cancel the active turn only; queued requests survive and proceed."""
        if self._activity_timer:
            self._activity_timer.stop()
            self._activity_timer = None

        cancel_event = getattr(self, "_cancel_event", None)
        if cancel_event is not None:
            cancel_event.set()
        if self._run_task is not None:
            self._run_task.cancel()          # active turn only — do NOT drain self._requests

        activity = self.query_one("#activity-bar", ActivityBar)
        activity.clear()

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.focus_input()
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_system_message("Turn cancelled.")

    def action_toggle_tools(self) -> None:
        """Toggle the tool context panel."""
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        visible = tool_panel.toggle()
        chat_view = self.query_one("#chat-view", ChatView)
        state = "visible" if visible else "hidden"
        chat_view.add_system_message(f"Tool panel {state} (Ctrl+O to toggle)")

    def action_toggle_thinking(self) -> None:
        """Toggle the thinking/reasoning panel (mirrors Ctrl+O / Ctrl+G)."""
        thinking_panel = self.query_one("#thinking-panel", ThinkingPanel)
        visible = thinking_panel.toggle()
        self._show_thinking = visible
        chat_view = self.query_one("#chat-view", ChatView)
        state = "visible" if visible else "hidden"
        chat_view.add_system_message(f"Thinking panel {state} (Ctrl+T to toggle)")

    def action_toggle_agents(self) -> None:
        """Toggle the agent panel."""
        agent_panel = self.query_one("#agent-panel", AgentPanel)
        visible = agent_panel.toggle()
        chat_view = self.query_one("#chat-view", ChatView)
        state = "visible" if visible else "hidden"
        chat_view.add_system_message(f"Agent panel {state} (Ctrl+G to toggle)")

    def action_show_help(self) -> None:
        """Show help modal with keybindings."""
        self.push_screen(CLIHelpScreen())

    def action_scroll_chat_up(self) -> None:
        """PageUp: scroll an open panel (agents/thinking) if any, else the chat view."""
        if self._scroll_open_panel("page_up"):
            return
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.disable_follow_mode()
        chat_view.scroll_page_up(animate=False)

    def action_scroll_chat_down(self) -> None:
        """PageDown: scroll an open panel (agents/thinking) if any, else the chat view."""
        if self._scroll_open_panel("page_down"):
            return
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.scroll_page_down(animate=False)
        if chat_view.scroll_offset.y >= chat_view.max_scroll_y:
            chat_view.enable_follow_mode()

    def _scroll_open_panel(self, motion: str) -> bool:
        """Scroll a visible scrollable panel — the agents (Ctrl+G) or thinking
        (Ctrl+T) panel — instead of the chat view.

        ``motion`` is a Widget.scroll_* suffix ('page_up', 'page_down', 'up',
        'down', 'home', 'end'). Returns True when a panel handled the scroll so
        the caller leaves the chat view alone; False otherwise (none open).
        """
        for panel_id, panel_cls in (
            ("#agent-panel", AgentPanel),
            ("#thinking-panel", ThinkingPanel),
        ):
            try:
                panel = self.query_one(panel_id, panel_cls)
            except Exception:
                continue
            if not panel.display:
                continue
            getattr(panel, f"scroll_{motion}")(animate=False)
            return True
        return False

    def action_clear(self) -> None:
        """Clear chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        self.query_one("#thinking-panel", ThinkingPanel).clear()
        do_clear(self, chat_view)

    def on_app_focus(self) -> None:
        """Restore input focus when terminal window regains focus."""
        try:
            input_bar = self.query_one("#input-bar", CLIInputBar)
            input_bar.focus_input()
        except Exception:
            pass


def _split_into_exchanges(messages: list[dict]) -> list[list[dict]]:
    """Group messages into user-led exchanges."""
    exchanges: list[list[dict]] = []
    current: list[dict] = []
    for message in messages:
        role = message.get("role")
        if role == "user":
            if current:
                exchanges.append(current)
            current = [message]
        elif current:
            current.append(message)
    if current:
        exchanges.append(current)
    return exchanges


async def apply_pending_compact(app, messages: list[dict]) -> None:
    """Consume pending context compaction at the chat-loop boundary."""
    pending = getattr(app, "_pending_compact", None)
    if not pending:
        return

    summary_content = pending.get("summary_content", "")
    keep_last_n = max(0, int(pending.get("keep_last_n", 0)))

    system_msg = None
    if messages and messages[0].get("role") == "system":
        system_msg = messages[0]

    tail_messages: list[dict] = []
    if keep_last_n > 0:
        exchanges = _split_into_exchanges(messages)
        for exchange in exchanges[-keep_last_n:]:
            tail_messages.extend(exchange)

    messages.clear()
    if system_msg is not None:
        messages.append(system_msg)
    messages.append(
        {
            "role": "user",
            "content": f"[Previous session summary]\n\n{summary_content}",
        }
    )
    messages.extend(tail_messages)

    context_manager = getattr(app, "context_manager", None)
    if context_manager is not None and hasattr(context_manager, "clear"):
        context_manager.clear()

    _agent_reg = getattr(app, "_agent_registry", None)
    if _agent_reg is not None:
        _agent_reg.new_generation()

    app._pending_compact = None
