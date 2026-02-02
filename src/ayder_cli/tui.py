"""
Textual TUI (Terminal User Interface) for ayder-cli.

Provides an interactive dashboard with:
- Chat history view
- Input bar
- Context panel with file tree and model info
- Status bar
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll, Vertical
from textual.widgets import Header, Footer, Static, Input, Button, Tree, Label
from textual.reactive import reactive
from textual.message import Message
from textual.worker import Worker, get_current_worker
from textual.screen import ModalScreen
from rich.markdown import Markdown
from rich.text import Text
from rich.panel import Panel
from enum import Enum

from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.client import call_llm_async
from ayder_cli.config import load_config
from openai import OpenAI


class MessageType(Enum):
    """Types of chat messages."""
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"


class ConfirmActionScreen(ModalScreen[bool]):
    """
    Modal screen for confirming actions with optional diff preview.
    
    Returns:
        True if approved, False if rejected
    """
    
    DEFAULT_CSS = """
    ConfirmActionScreen {
        align: center middle;
    }
    
    ConfirmActionScreen > Vertical {
        width: 80;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    ConfirmActionScreen .title {
        text-style: bold;
        text-align: center;
        color: $primary;
        margin-bottom: 1;
    }
    
    ConfirmActionScreen .description {
        margin-bottom: 1;
    }
    
    ConfirmActionScreen .diff-container {
        height: 20;
        border: solid $primary-darken-2;
        margin: 1 0;
        padding: 1;
        overflow: auto scroll;
    }
    
    ConfirmActionScreen .buttons {
        height: auto;
        align: center middle;
    }
    
    ConfirmActionScreen Button {
        margin: 0 1;
    }
    """
    
    def __init__(
        self,
        title: str,
        description: str,
        diff_content: str = None,
        action_name: str = "Confirm"
    ):
        super().__init__()
        self.title = title
        self.description = description
        self.diff_content = diff_content
        self.action_name = action_name
    
    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Vertical():
            yield Label(self.title, classes="title")
            yield Label(self.description, classes="description")
            
            # Show diff if provided
            if self.diff_content:
                diff_widget = Static(
                    self._render_diff(),
                    classes="diff-container"
                )
                yield diff_widget
            
            with Horizontal(classes="buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button(self.action_name, variant="success", id="confirm-btn")
    
    def _render_diff(self) -> Panel:
        """Render diff content with syntax highlighting."""
        # Colorize diff lines
        lines = self.diff_content.split('\n')
        colorized = []
        
        for line in lines:
            if line.startswith('@@'):
                colorized.append(f"[cyan]{line}[/cyan]")
            elif line.startswith('-') and not line.startswith('---'):
                colorized.append(f"[red]{line}[/red]")
            elif line.startswith('+') and not line.startswith('+++'):
                colorized.append(f"[green]{line}[/green]")
            else:
                colorized.append(line)
        
        content = '\n'.join(colorized)
        return Panel(content, title="Preview")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)
    
    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "enter":
            self.dismiss(True)


class SafeModeBlockScreen(ModalScreen):
    """
    Modal screen shown when a tool is blocked in safe mode.
    """
    
    DEFAULT_CSS = """
    SafeModeBlockScreen {
        align: center middle;
    }
    
    SafeModeBlockScreen > Vertical {
        width: 60;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    
    SafeModeBlockScreen .title {
        text-style: bold;
        text-align: center;
        color: $error;
        margin-bottom: 1;
    }
    """
    
    def __init__(self, tool_name: str):
        super().__init__()
        self.tool_name = tool_name
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("⛔ Safe Mode", classes="title")
            yield Label(f"Tool '{self.tool_name}' is blocked in safe mode.")
            yield Label("Restart without --safe to enable this tool.")
            yield Button("OK", variant="primary", id="ok-btn")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class ChatMessage:
    """Represents a single chat message."""
    
    def __init__(self, content: str, msg_type: MessageType, metadata: dict = None):
        self.content = content
        self.type = msg_type
        self.metadata = metadata or {}
    
    def __rich__(self):
        """Render message as Rich content."""
        if self.type == MessageType.USER:
            return Panel(
                self.content,
                title="You",
                border_style="cyan",
                padding=(1, 2)
            )
        elif self.type == MessageType.ASSISTANT:
            # Render markdown for assistant messages
            md = Markdown(self.content)
            return Panel(
                md,
                title="Assistant",
                border_style="green",
                padding=(1, 2)
            )
        elif self.type == MessageType.TOOL_CALL:
            tool_name = self.metadata.get("tool_name", "unknown")
            return Panel(
                f"[yellow]{tool_name}[/yellow]({self.content})",
                title="Tool Call",
                border_style="yellow",
                padding=(1, 2)
            )
        elif self.type == MessageType.TOOL_RESULT:
            # Truncate long results
            content = self.content
            if len(content) > 500:
                content = content[:500] + "..."
            return Panel(
                f"[green]✓[/green] {content}",
                title="Result",
                border_style="bright_black",
                padding=(1, 2)
            )
        else:
            return Panel(
                self.content,
                border_style="white",
                padding=(1, 2)
            )


class ChatView(VerticalScroll):
    """
    Scrollable widget for displaying chat messages.
    
    Supports:
    - User messages (cyan panels)
    - Assistant messages (green panels with markdown)
    - Tool calls (yellow panels)
    - Tool results (dim panels)
    """
    
    DEFAULT_CSS = """
    ChatView {
        height: 100%;
        border: solid $primary;
        padding: 1;
    }
    """
    
    messages: reactive[list] = reactive(list)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._message_widgets: list[Static] = []
    
    def add_message(self, content: str, msg_type: MessageType, metadata: dict = None) -> None:
        """
        Add a message to the chat view.
        
        Args:
            content: Message content
            msg_type: Type of message
            metadata: Additional metadata (e.g., tool_name)
        """
        message = ChatMessage(content, msg_type, metadata)
        self.messages.append(message)
        
        # Create and mount the message widget
        msg_widget = Static(message, classes=f"message {msg_type.value}")
        self._message_widgets.append(msg_widget)
        self.mount(msg_widget)
        
        # Scroll to bottom
        self.scroll_end(animate=False)
    
    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self.add_message(content, MessageType.USER)
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message (rendered as markdown)."""
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
    
    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        for widget in self._message_widgets:
            widget.remove()
        self._message_widgets.clear()
        self.messages.clear()


class InputBar(Horizontal):
    """
    Input bar with text input and submit button.
    
    Emits:
        InputBar.Submitted: When user submits input
    """
    
    DEFAULT_CSS = """
    InputBar {
        height: auto;
        border-top: solid $primary;
        padding: 1;
    }
    
    InputBar Input {
        width: 1fr;
    }
    
    InputBar Button {
        margin-left: 1;
    }
    """
    
    class Submitted(Message):
        """Message sent when input is submitted."""
        
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._input = None
    
    def compose(self) -> ComposeResult:
        """Compose the input bar."""
        self._input = Input(placeholder="Type your message...", id="chat-input")
        yield self._input
        yield Button("Send", id="send-btn", variant="primary")
    
    def on_mount(self) -> None:
        """Focus input on mount."""
        self._input = self.query_one("#chat-input", Input)
        self._input.focus()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self._submit()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle Send button click."""
        if event.button.id == "send-btn":
            self._submit()
    
    def _submit(self) -> None:
        """Submit the current input value."""
        if self._input:
            value = self._input.value.strip()
            if value:
                self.post_message(self.Submitted(value))
                self._input.value = ""
    
    def focus_input(self) -> None:
        """Focus the input field."""
        if self._input:
            self._input.focus()
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable input."""
        if self._input:
            self._input.disabled = not enabled
        send_btn = self.query_one("#send-btn", Button)
        if send_btn:
            send_btn.disabled = not enabled


class ContextPanel(Vertical):
    """
    Sidebar panel showing context information:
    - Active model
    - Token usage
    - Active files
    - Project info
    """
    
    DEFAULT_CSS = """
    ContextPanel {
        width: 100%;
        height: 100%;
        border: solid $primary-darken-2;
        padding: 1;
    }
    
    ContextPanel .section-title {
        text-style: bold;
        color: $primary;
        margin: 1 0;
    }
    
    ContextPanel .info-row {
        margin: 0 0 1 0;
    }
    
    ContextPanel Tree {
        height: 1fr;
        border: none;
        padding: 0;
    }
    """
    
    def __init__(self, model: str = "default", **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.token_count = 0
        self.active_files: list[str] = []
        self._token_label = None
        self._file_tree = None
    
    def compose(self) -> ComposeResult:
        """Compose the context panel."""
        # Model info section
        yield Label("Model", classes="section-title")
        yield Label(f"  {self.model}", classes="info-row")
        
        # Token usage section
        yield Label("Token Usage", classes="section-title")
        self._token_label = Label("  0 tokens", classes="info-row")
        yield self._token_label
        
        # Active files section
        yield Label("Active Files", classes="section-title")
        
        # File tree
        tree: Tree[dict] = Tree("Project")
        tree.root.expand()
        self._file_tree = tree
        yield tree
    
    def set_model(self, model: str) -> None:
        """Update the displayed model."""
        self.model = model
        # Update UI (would need to store reference to label)
    
    def update_token_usage(self, count: int) -> None:
        """Update token count display."""
        self.token_count = count
        if self._token_label:
            self._token_label.update(f"  {count:,} tokens")
    
    def add_active_file(self, file_path: str) -> None:
        """Add a file to the active files list."""
        if file_path not in self.active_files:
            self.active_files.append(file_path)
            self._refresh_file_tree()
    
    def remove_active_file(self, file_path: str) -> None:
        """Remove a file from the active files list."""
        if file_path in self.active_files:
            self.active_files.remove(file_path)
            self._refresh_file_tree()
    
    def clear_active_files(self) -> None:
        """Clear all active files."""
        self.active_files.clear()
        self._refresh_file_tree()
    
    def _refresh_file_tree(self) -> None:
        """Refresh the file tree display."""
        if not self._file_tree:
            return
        
        self._file_tree.clear()
        root = self._file_tree.root
        root.label = "Active Files"
        
        for file_path in self.active_files:
            root.add_leaf(file_path)


class AyderApp(App):
    """
    Main Textual application for ayder-cli with integrated LLM agent.
    
    Layout:
    - Header: App title and current model
    - Main area: Chat view (left) + Context panel (right)
    - Footer: Status info and keyboard shortcuts
    """
    
    CSS = """
    /* Screen layout */
    Screen {
        layout: vertical;
    }
    
    /* Main container */
    #main-container {
        layout: horizontal;
        height: 1fr;
    }
    
    /* Chat view takes most space */
    #chat-view {
        width: 3fr;
        height: 100%;
        border: solid $primary;
    }
    
    /* Context panel on the right */
    #context-panel {
        width: 1fr;
        height: 100%;
        border: solid $primary-darken-2;
    }
    
    /* Input area at bottom */
    #input-bar {
        height: auto;
        border-top: solid $primary;
        padding: 1;
    }
    """
    
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+c", "cancel", "Cancel"),
        ("ctrl+l", "clear", "Clear Chat"),
    ]
    
    def __init__(self, model: str = "default", safe_mode: bool = False, **kwargs):
        """
        Initialize the TUI app.
        
        Args:
            model: The LLM model name to use
            safe_mode: Whether to enable safe mode (blocks destructive operations)
            **kwargs: Additional arguments for App
        """
        super().__init__(**kwargs)
        self.model = model
        self.safe_mode = safe_mode
        self.title = f"Ayder CLI - {model}"
        
        # Load config
        self.config = load_config()
        
        # Initialize OpenAI client
        if isinstance(self.config, dict):
            base_url = self.config.get("base_url", "http://localhost:11434/v1")
            api_key = self.config.get("api_key", "ollama")
        else:
            base_url = self.config.base_url
            api_key = self.config.api_key
        
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        
        # Conversation history
        self.messages: list[dict] = []
        
        # Tool registry with callbacks and middleware
        self.registry = create_default_registry()
        self._setup_registry_callbacks()
        self._setup_registry_middleware()
    
    def _setup_registry_callbacks(self) -> None:
        """Setup callbacks for tool registry."""
        # Pre-execute callback
        def on_tool_start(tool_name: str, arguments: dict):
            chat_view = self.query_one("#chat-view", ChatView)
            chat_view.add_tool_call(tool_name, str(arguments))
        
        # Post-execute callback
        def on_tool_complete(result):
            chat_view = self.query_one("#chat-view", ChatView)
            if result.result:
                chat_view.add_tool_result(result.result)
        
        self.registry.add_pre_execute_callback(on_tool_start)
        self.registry.add_post_execute_callback(on_tool_complete)
    
    def _setup_registry_middleware(self) -> None:
        """Setup middleware for safe mode and confirmations."""
        # Safe mode middleware
        def safe_mode_check(tool_name: str, arguments: dict):
            if self._is_tool_blocked_in_safe_mode(tool_name):
                # Show safe mode block screen (synchronous for now)
                # In a real async implementation, this would need to be awaited
                # For now, we'll raise PermissionError which will be caught by the registry
                raise PermissionError(f"Tool '{tool_name}' blocked in safe mode")
        
        if self.safe_mode:
            self.registry.add_middleware(safe_mode_check)
    
    def _is_tool_blocked_in_safe_mode(self, tool_name: str) -> bool:
        """
        Check if a tool should be blocked in safe mode.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            True if tool should be blocked
        """
        blocked_tools = [
            "run_shell_command",
            "write_file",
            "replace_string",
        ]
        
        return tool_name in blocked_tools
    
    def compose(self) -> ComposeResult:
        """
        Compose the UI layout.
        
        Yields:
            UI components
        """
        # Header with title
        yield Header(show_clock=True)
        
        # Main content area
        with Horizontal(id="main-container"):
            # Chat view
            yield ChatView(id="chat-view")
            
            # Context panel
            yield ContextPanel(model=self.model, id="context-panel")
        
        # Input bar
        yield InputBar(id="input-bar")
        
        # Footer with shortcuts
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = f"Ayder CLI - {self.model}"
        
        # Show welcome message
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_system_message("Welcome to Ayder CLI! Type your message to begin.")
    
    def on_input_bar_submitted(self, event: InputBar.Submitted) -> None:
        """Handle user input submission."""
        user_input = event.value
        
        # Add to chat view
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_user_message(user_input)
        
        # Add to conversation history
        self.messages.append({"role": "user", "content": user_input})
        
        # Disable input during processing
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.set_enabled(False)
        
        # Start LLM worker
        self.run_worker(self._process_llm_response(), exclusive=True)
    
    async def _process_llm_response(self) -> None:
        """
        Process LLM response (runs in worker thread).
        
        This runs asynchronously to not block the UI.
        """
        worker = get_current_worker()
        
        try:
            # Get tool schemas
            tool_schemas = self.registry.get_schemas()
            
            # Get model config
            if isinstance(self.config, dict):
                model = self.config.get("model", "qwen3-coder:latest")
                num_ctx = self.config.get("num_ctx", 65536)
            else:
                model = self.config.model
                num_ctx = self.config.num_ctx
            
            # Call LLM
            response = await call_llm_async(
                self.client,
                self.messages,
                model,
                tools=tool_schemas,
                num_ctx=num_ctx
            )
            
            # Handle response
            if worker.is_cancelled:
                return
            
            await self._handle_llm_response(response)
            
        except Exception as e:
            if not worker.is_cancelled:
                chat_view = self.query_one("#chat-view", ChatView)
                chat_view.add_system_message(f"Error: {str(e)}")
        finally:
            if not worker.is_cancelled:
                # Re-enable input
                self.call_from_thread(self._enable_input)
    
    async def _handle_llm_response(self, response) -> None:
        """
        Handle the LLM response, including tool calls.
        
        Args:
            response: LLM response object
        """
        # Extract message
        message = response.choices[0].message
        content = message.content or ""
        tool_calls = message.tool_calls
        
        # Build message dict for history
        msg_dict = {
            "role": "assistant",
            "content": content
        }
        
        if tool_calls:
            # Convert tool calls to dict format for history
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
        
        # Add assistant message to history
        self.messages.append(msg_dict)
        
        # Display content
        if content:
            chat_view = self.query_one("#chat-view", ChatView)
            chat_view.add_assistant_message(content)
        
        # Execute tool calls
        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                arguments = tool_call.function.arguments
                
                # Parse arguments if they're a string
                import json
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                
                # Execute tool
                result = self.registry.execute(tool_name, arguments)
                
                # Add tool result to messages
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": str(result)
                })
            
            # Check if we should continue the conversation
            worker = get_current_worker()
            if not worker.is_cancelled:
                # Recursive call for follow-up
                await self._process_llm_response()
    
    def _enable_input(self) -> None:
        """Re-enable input (called from worker thread)."""
        input_bar = self.query_one("#input-bar", InputBar)
        input_bar.set_enabled(True)
        input_bar.focus_input()
    
    def action_cancel(self) -> None:
        """Cancel current operation."""
        # Cancel any running workers
        for worker in self.workers:
            worker.cancel()
        
        self._enable_input()
        
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_system_message("Operation cancelled.")
    
    def action_clear(self) -> None:
        """Clear chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.clear_messages()
        self.messages.clear()
        
        chat_view.add_system_message("Chat history cleared.")


def run_tui(model: str = "default") -> None:
    """
    Run the Textual TUI application.
    
    Args:
        model: The LLM model name to use
    """
    app = AyderApp(model=model)
    app.run()


if __name__ == "__main__":
    run_tui()
