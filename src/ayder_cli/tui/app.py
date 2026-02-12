"""
AyderApp — main Textual application for ayder-cli TUI.

Contains init, compose, LLM pipeline, tool confirmation, and UI actions.
Command handlers are in tui.commands.
"""

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.worker import get_current_worker
from textual.timer import Timer
from textual import on
from rich.text import Text
from pathlib import Path
import asyncio
import difflib
import json
import re

from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.core.context import ProjectContext
from ayder_cli.client import call_llm_async
from ayder_cli.core.config import load_config
from ayder_cli.services.llm import OpenAIProvider
from ayder_cli.commands.registry import get_registry
from ayder_cli.banner import create_tui_banner
from ayder_cli.tui.theme_manager import get_theme_css
from ayder_cli.tui.types import ConfirmResult
from ayder_cli.tui.screens import CLIConfirmScreen
from ayder_cli.tui.widgets import ChatView, ToolPanel, CLIInputBar, StatusBar
from ayder_cli.tui.commands import COMMAND_MAP, do_clear


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
        ("ctrl+d", "quit", "Quit"),
        ("ctrl+x", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
        ("ctrl+l", "clear", "Clear Chat"),
    ]

    def __init__(self, model: str = "default", safe_mode: bool = False, permissions: set = None, **kwargs):
        """
        Initialize the TUI app.

        Args:
            model: The LLM model name to use
            safe_mode: Whether to enable safe mode
            permissions: Set of granted permission levels ("r", "w", "x")
        """
        super().__init__(**kwargs)
        self.model = model
        self.safe_mode = safe_mode
        self.permissions = permissions or {"r"}

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

        registry = get_registry()
        self.commands = registry.get_command_names()
        # Add TUI-only commands to autocomplete
        if "/permission" not in self.commands:
            self.commands.append("/permission")

        from ayder_cli.process_manager import ProcessManager

        max_procs = self.config.max_background_processes if not isinstance(self.config, dict) else self.config.get("max_background_processes", 5)
        self._process_manager = ProcessManager(max_processes=max_procs)
        self.registry = create_default_registry(ProjectContext("."), process_manager=self._process_manager)
        self._setup_registry_callbacks()
        self._setup_registry_middleware()

        # Build system prompt (same as CLI runner)
        self.messages: list[dict] = []
        self._init_system_prompt()

        self._thinking_timer: Timer | None = None
        self._tools_timer: Timer | None = None
        self._total_tokens: int = 0

    def _init_system_prompt(self) -> None:
        """Build and set the system prompt with project structure."""
        from ayder_cli.prompts import SYSTEM_PROMPT, PROJECT_STRUCTURE_MACRO_TEMPLATE

        try:
            structure = self.registry.execute("get_project_structure", {"max_depth": 3})
            macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
        except Exception:
            macro = ""

        system_prompt = SYSTEM_PROMPT + macro
        self.messages.append({"role": "system", "content": system_prompt})

    def _animate_running_tools(self) -> None:
        """Animate spinner for running tools."""
        tool_panel = self.query_one("#tool-panel", ToolPanel)
        tool_panel.update_spinners()

    def _setup_registry_callbacks(self) -> None:
        """Setup callbacks for tool registry.

        Note: Registry callbacks run inside asyncio.to_thread() (background thread),
        so they MUST NOT mount widgets on the ChatView (not thread-safe in Textual).
        Tool call/result display is handled by the ToolPanel and by _handle_llm_response
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

    def _tool_needs_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation based on permissions."""
        from ayder_cli.tools.schemas import TOOL_PERMISSIONS

        tool_perm = TOOL_PERMISSIONS.get(tool_name, "r")
        return tool_perm not in self.permissions

    def _generate_diff(self, tool_name: str, arguments: dict) -> str | None:
        """Generate a diff preview for file-modifying tools."""
        file_modifying_tools = {"write_file", "replace_string", "insert_line", "delete_line"}
        if tool_name not in file_modifying_tools:
            return None

        file_path = arguments.get("file_path", "")
        try:
            path = Path(file_path)
            if not path.exists():
                if tool_name == "write_file":
                    new_content = arguments.get("content", "")
                    return "\n".join(
                        f"+{line}" for line in new_content.split("\n")
                    )
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
                original_lines, new_lines,
                fromfile=f"a/{path.name}", tofile=f"b/{path.name}",
                lineterm=""
            )
            return "\n".join(diff) or None

        except Exception:
            return None

    async def _request_confirmation(self, tool_name: str, arguments: dict) -> ConfirmResult | None:
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
                action_name=description
            ),
            on_result
        )

        await event.wait()
        return result_holder[0]

    def compose(self) -> ComposeResult:
        """Compose the UI layout - terminal style with scrolling content."""
        yield ChatView(id="chat-view")
        yield ToolPanel(id="tool-panel")
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
            child.size.height for child in chat_view.children
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

        input_bar = self.query_one("#input-bar", CLIInputBar)
        input_bar.set_enabled(False)
        chat_view.show_thinking()
        self._thinking_timer = self.set_interval(0.1, self._animate_thinking)

        self.run_worker(self._process_llm_response(), exclusive=True)

    def _animate_thinking(self) -> None:
        """Animate the thinking indicator."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view._update_thinking()

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
                chat_view.add_system_message(f"Unknown command: {cmd_name}. Type /help for available commands.")
        except Exception as e:
            chat_view.add_system_message(f"Command error: {type(e).__name__}: {e}")

    async def _process_llm_response(self, no_tools: bool = False, _is_continuation: bool = False) -> None:
        """Process LLM response (runs in worker thread).

        Args:
            no_tools: If True, don't send tool schemas to the LLM.
            _is_continuation: Internal flag -- True for recursive calls after tool execution.
                Prevents duplicate _finish_processing scheduling.
        """
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
            if not worker.is_cancelled and not _is_continuation:
                self.call_later(self._finish_processing)

    async def _handle_llm_response(self, response) -> None:
        """Handle the LLM response, including tool calls."""
        # Hide thinking spinner as soon as LLM responds
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.hide_thinking()
        if self._thinking_timer:
            self._thinking_timer.stop()
            self._thinking_timer = None

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

        # Extract and display <think>...</think> blocks separately

        # Extract <think> blocks -- handle both closed and unclosed tags
        think_blocks = re.findall(r"<think>(.*?)</think>", content, flags=re.DOTALL)
        display_content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

        # Handle unclosed <think> (model didn't emit </think>)
        unclosed = re.findall(r"<think>(.*)", display_content, flags=re.DOTALL)
        if unclosed:
            think_blocks.extend(unclosed)
            display_content = re.sub(r"<think>.*", "", display_content, flags=re.DOTALL)

        for think_text in think_blocks:
            think_text = think_text.strip()
            if think_text:
                chat_view.add_thinking_message(think_text)

        # Collapse excessive blank lines
        display_content = re.sub(r"\n{3,}", "\n\n", display_content).strip()
        if display_content:
            chat_view.add_assistant_message(display_content)

        if tool_calls:
            tool_panel = self.query_one("#tool-panel", ToolPanel)

            # Split tools into auto-approved and needs-confirmation
            auto_approved = []
            needs_confirmation = []
            for tc in tool_calls:
                tool_name = tc.function.name
                if self._tool_needs_confirmation(tool_name):
                    needs_confirmation.append(tc)
                else:
                    auto_approved.append(tc)

            # Show all tools as running first
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                arguments = tool_call.function.arguments
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                tool_panel.add_tool(tool_call.id, tool_name, arguments)

            # Start spinner animation for running tools
            self._tools_timer = self.set_interval(0.1, self._animate_running_tools)

            try:
                # Execute auto-approved tools in parallel
                async def execute_tool_async(tool_call):
                    """Execute a single tool call asynchronously."""
                    tool_name = tool_call.function.name
                    arguments = tool_call.function.arguments

                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError as e:
                            return {
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "result": f"Error: Invalid JSON arguments: {e}"
                            }

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

                tool_results = []
                if auto_approved:
                    auto_tasks = [execute_tool_async(tc) for tc in auto_approved]
                    auto_results = await asyncio.gather(*auto_tasks, return_exceptions=True)
                    tool_results.extend(auto_results)

                # Execute needs-confirmation tools sequentially with user prompts
                custom_instructions = None
                for tc in needs_confirmation:
                    tool_name = tc.function.name
                    arguments = tc.function.arguments
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError as e:
                            tool_results.append({
                                "tool_call_id": tc.id,
                                "name": tool_name,
                                "result": f"Error: Invalid JSON arguments: {e}"
                            })
                            continue

                    confirm_result = await self._request_confirmation(tool_name, arguments)

                    if confirm_result is not None and confirm_result.action == "approve":
                        result = await asyncio.to_thread(
                            self.registry.execute,
                            tool_name,
                            arguments
                        )
                        tool_results.append({
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "result": result
                        })
                    elif confirm_result is not None and confirm_result.action == "instruct":
                        # Deny this tool and capture instructions
                        tool_results.append({
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "result": "Tool call denied by user."
                        })
                        custom_instructions = confirm_result.instructions
                        # Skip remaining unconfirmed tools
                        remaining = needs_confirmation[needs_confirmation.index(tc) + 1:]
                        for remaining_tc in remaining:
                            tool_results.append({
                                "tool_call_id": remaining_tc.id,
                                "name": remaining_tc.function.name,
                                "result": "Tool call skipped (user provided instructions)."
                            })
                        break
                    else:
                        # Denied or dismissed (None)
                        tool_results.append({
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "result": "Tool call denied by user."
                        })

                # Process results and mark tools as complete
                for i, result_data in enumerate(tool_results):
                    if isinstance(result_data, Exception):
                        # Recover the real tool_call_id and name from auto_approved
                        if i < len(auto_approved):
                            err_tc = auto_approved[i]
                            err_id = err_tc.id
                            err_name = err_tc.function.name
                        else:
                            err_id = "error"
                            err_name = "unknown"
                        error_msg = f"Error: {str(result_data)}"
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": err_id,
                            "name": err_name,
                            "content": error_msg
                        })
                    else:
                        tool_call_id = result_data["tool_call_id"]
                        tool_name = result_data["name"]
                        result = result_data["result"]

                        # Update ToolPanel (tool display is handled there, not in ChatView)
                        self.call_later(
                            lambda tid=tool_call_id, res=result: tool_panel.complete_tool(tid, str(res))
                        )

                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "content": str(result)
                        })

                # If user provided custom instructions, inject them as a user message
                if custom_instructions:
                    self.messages.append({
                        "role": "user",
                        "content": custom_instructions
                    })

                # Schedule panel cleanup after a short delay
                self.set_timer(2.0, lambda: tool_panel.clear_completed())

                worker = get_current_worker()
                if not worker.is_cancelled:
                    # Re-show thinking spinner while waiting for next LLM response
                    chat_view.show_thinking()
                    self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
                    await self._process_llm_response(_is_continuation=True)

            finally:
                # Ensure _tools_timer is always stopped even on exceptions
                if self._tools_timer:
                    self._tools_timer.stop()
                    self._tools_timer = None

        elif content and "<function=" in content:
            # XML tool call fallback — matches chat_loop.py:ToolCallHandler pattern
            from ayder_cli.parser import parse_custom_tool_calls

            custom_calls = parse_custom_tool_calls(content)
            # Filter out parser errors
            valid_calls = [c for c in custom_calls if "error" not in c]

            if valid_calls:
                results_text = []
                for call in valid_calls:
                    tool_name = call.get("name", "unknown")
                    arguments = call.get("arguments", {})
                    try:
                        result = self.registry.execute(tool_name, arguments)
                        results_text.append(f"[{tool_name}] {result}")
                    except Exception as e:
                        results_text.append(f"[{tool_name}] Error: {e}")

                # Feed results back as user role (custom call convention)
                self.messages.append({
                    "role": "user",
                    "content": "\n".join(results_text)
                })

                worker = get_current_worker()
                if not worker.is_cancelled:
                    chat_view.show_thinking()
                    self._thinking_timer = self.set_interval(0.1, self._animate_thinking)
                    await self._process_llm_response(_is_continuation=True)

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

    def action_clear(self) -> None:
        """Clear chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        do_clear(self, chat_view)
