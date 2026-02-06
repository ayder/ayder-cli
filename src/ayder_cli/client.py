import json
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from ayder_cli import fs_tools
from ayder_cli.config import load_config, Config
from ayder_cli.path_context import ProjectContext
from ayder_cli.ui import draw_box, print_running, print_assistant_message, print_tool_result, confirm_tool_call, describe_tool_action, print_file_content, confirm_with_diff, print_tool_skipped
from ayder_cli.banner import print_welcome_banner
from ayder_cli.parser import parse_custom_tool_calls
from ayder_cli.commands import handle_command
from ayder_cli.tools import prepare_new_content
from ayder_cli.tools.schemas import TOOL_PERMISSIONS
from ayder_cli.prompts import SYSTEM_PROMPT
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import ANSI

# Tools that end the agentic loop after execution
TERMINAL_TOOLS = {"create_task", "list_tasks", "show_task", "implement_task", "implement_all_tasks"}

# Thread pool for running sync code
_executor = ThreadPoolExecutor(max_workers=2)


async def call_llm_async(
    client: OpenAI,
    messages: list,
    model: str,
    tools: list = None,
    num_ctx: int = 65536
) -> dict:
    """
    Async wrapper for LLM calls.
    
    Runs the synchronous LLM call in a thread pool to avoid blocking the UI.
    
    Args:
        client: OpenAI client instance
        messages: Conversation history
        model: Model name
        tools: Available tools (optional)
        num_ctx: Context window size
        
    Returns:
        LLM response object
    """
    loop = asyncio.get_event_loop()
    
    def call_sync():
        kwargs = {
            "model": model,
            "messages": messages,
            "extra_body": {"options": {"num_ctx": num_ctx}}
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        return client.chat.completions.create(**kwargs)
    
    return await loop.run_in_executor(_executor, call_sync)


class ChatSession:
    """Manage conversation state, history, and user input."""

    def __init__(self, config, system_prompt):
        """Initialize chat session.
        
        Args:
            config: Config object from TASK-007
            system_prompt: Base SYSTEM_PROMPT (enhanced with project structure)
        """
        self.config = config
        self.system_prompt = system_prompt
        self.messages = []
        self.state = {"verbose": config.verbose if hasattr(config, "verbose") else False}
        self.session = None

    def start(self):
        """Initialize the session, load history, print banner."""
        # Initialize message history with system prompt
        self.messages = [{"role": "system", "content": self.system_prompt}]
        
        # Create history file in home directory
        history_file = str(Path("~/.ayder_chat_history").expanduser())
        
        # Create prompt session with emacs keybindings and history
        self.session = PromptSession(
            history=FileHistory(history_file),
            enable_history_search=True,
            multiline=False,
            vi_mode=False  # Emacs mode is default
        )
        
        # Print welcome banner
        model_name = self.config.model if hasattr(self.config, "model") else "qwen3-coder:latest"
        print_welcome_banner(model_name, str(Path.cwd()))

    def add_message(self, role: str, content: str, **kwargs):
        """Add a message to conversation history.
        
        Args:
            role: Message role (user, assistant, system, tool)
            content: Message content
            **kwargs: Additional message fields (tool_call_id, name, etc.)
        """
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.messages.append(message)

    def get_input(self) -> str | None:
        """Get user input via prompt_toolkit.
        
        Returns:
            User input string, or None for exit/quit/EOF
        """
        try:
            user_input = self.session.prompt(ANSI("\n\033[1;36m❯\033[0m "), vi_mode=False)
            
            if not user_input.strip():
                return ""  # Empty input - continue loop
            
            if user_input.lower() in ["exit", "quit"]:
                print("\n\033[33mGoodbye!\033[0m\n")
                return None
            
            return user_input.strip()
            
        except KeyboardInterrupt:
            print("\n\033[33m\nUse 'exit' or Ctrl+D to quit.\033[0m")
            return ""  # Continue loop
        except EOFError:
            print("\n\033[33mGoodbye!\033[0m\n")
            return None

    def render_history(self):
        """Render conversation history (for debugging/display)."""
        for msg in self.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            print(f"[{role}] {content[:100]}...")

    def get_messages(self) -> list:
        """Get current message history for API calls."""
        return self.messages

    def clear_messages(self, keep_system: bool = True):
        """Clear conversation history, optionally keeping system message.
        
        Args:
            keep_system: If True, keeps the system message
        """
        if keep_system and len(self.messages) > 0:
            system_msg = self.messages[0]
            self.messages = [system_msg]
        else:
            self.messages = []


class Agent:
    """Handle OpenAI/Ollama API interaction and tool execution."""

    def __init__(self, openai_client, config, session: ChatSession,
                 permissions=None, iterations=10):
        """Initialize agent.

        Args:
            openai_client: OpenAI client (injected)
            config: Config object
            session: Reference to ChatSession
            permissions: Set of granted permission categories (e.g. {"r", "w", "x"})
            iterations: Max agentic iterations per message (default: 10)
        """
        self.client = openai_client
        self.config = config
        self.session = session
        self.terminal_tools = TERMINAL_TOOLS
        self.granted_permissions = permissions or set()
        self.max_iterations = iterations

    def chat(self, user_input: str):
        """Process user input through the agentic loop.
        
        Args:
            user_input: User's input message
        """
        try:
            print_running()
            self.session.add_message("user", user_input)

            # Support both dict and Config model for config
            if isinstance(self.config, dict):
                model = self.config.get("model", "qwen3-coder:latest")
                num_ctx = self.config.get("num_ctx", 65536)
            else:
                model = self.config.model
                num_ctx = self.config.num_ctx

            # Main Loop for Agentic Steps
            for _ in range(self.max_iterations):
                response = self.client.chat.completions.create(
                    model=model,
                    messages=self.session.get_messages(),
                    tools=fs_tools.tools_schema,
                    tool_choice="auto",
                    extra_body={"options": {"num_ctx": num_ctx}}
                )

                msg = response.choices[0].message
                content = msg.content or ""

                tool_calls = msg.tool_calls
                custom_calls = []
                if not tool_calls:
                    custom_calls = parse_custom_tool_calls(content)

                    # Check for parser errors
                    for call in custom_calls:
                        if "error" in call:
                            self.session.add_message(
                                "user",
                                f"Tool parsing error: {call['error']}"
                            )
                            custom_calls = []
                            break

                if not tool_calls and not custom_calls:
                    # No tools used, just conversation
                    if content:
                        print_assistant_message(content)
                        self.session.add_message("assistant", content)
                    break  # Wait for user input

                # If tools were called: add the message with tool_calls
                self.session.messages.append(msg)

                # Execute tool calls
                if tool_calls:
                    if self._execute_tool_loop(tool_calls):
                        break  # Terminal tool hit
                elif custom_calls:
                    if self._handle_custom_calls(custom_calls):
                        break  # Terminal tool hit

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            draw_box(error_msg, title="Error", width=80, color_code="31")

    def _execute_tool_loop(self, tool_calls) -> bool:
        """Execute the tool call loop.
        
        Args:
            tool_calls: List of tool call objects from OpenAI response
            
        Returns:
            True if terminal tool was hit, False otherwise
        """
        for tc in tool_calls:
            result_msg = self._handle_tool_call(tc)
            if result_msg is None:
                # Tool was declined
                return True
            
            self.session.messages.append(result_msg)
            
            # Check if terminal tool
            if tc.function.name in self.terminal_tools:
                return True
        
        return False

    def _handle_tool_call(self, tool_call) -> dict | None:
        """Handle a single tool call: validation, confirmation, execution.
        
        Args:
            tool_call: Tool call object from OpenAI response
            
        Returns:
            Result message dict for the conversation, or None if declined
        """
        fname = tool_call.function.name
        fargs = tool_call.function.arguments

        # Parse and normalize arguments
        parsed = json.loads(fargs) if isinstance(fargs, str) else fargs
        normalized = fs_tools.normalize_tool_arguments(fname, parsed)

        # Validate before confirmation
        is_valid, error_msg = fs_tools.validate_tool_call(fname, normalized)
        if not is_valid:
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": fname,
                "content": f"Validation Error: {error_msg}"
            }

        description = describe_tool_action(fname, normalized)

        # Check if tool is auto-approved by permission flags
        tool_perm = TOOL_PERMISSIONS.get(fname, "x")
        auto_approved = tool_perm in self.granted_permissions

        if auto_approved:
            confirmed = True
        elif fname in ("write_file", "replace_string"):
            file_path = normalized.get("file_path", "")
            new_content = prepare_new_content(fname, normalized)
            confirmed = confirm_with_diff(file_path, new_content, description)
        else:
            confirmed = confirm_tool_call(description)

        if not confirmed:
            print_tool_skipped()
            return None

        result = fs_tools.execute_tool_call(fname, normalized)
        print_tool_result(result)

        if self.session.state["verbose"] and fname == "write_file" and str(result).startswith("Successfully"):
            print_file_content(normalized.get("file_path", ""))

        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": fname,
            "content": str(result)
        }

    def _handle_custom_calls(self, custom_calls) -> bool:
        """Handle custom XML-parsed tool calls.
        
        Args:
            custom_calls: List of custom parsed tool calls
            
        Returns:
            True if terminal tool was hit, False otherwise
        """
        for call in custom_calls:
            fname = call['name']
            fargs = call['arguments']

            # Normalize and validate custom calls
            normalized = fs_tools.normalize_tool_arguments(fname, fargs)
            is_valid, error_msg = fs_tools.validate_tool_call(fname, normalized)
            if not is_valid:
                self.session.add_message(
                    "user",
                    f"Validation Error for tool '{fname}': {error_msg}"
                )
                return True  # Stop on validation error

            description = describe_tool_action(fname, normalized)

            # Check if tool is auto-approved by permission flags
            tool_perm = TOOL_PERMISSIONS.get(fname, "x")
            auto_approved = tool_perm in self.granted_permissions

            if auto_approved:
                confirmed = True
            elif fname in ("write_file", "replace_string"):
                file_path = normalized.get("file_path", "")
                new_content = prepare_new_content(fname, normalized)
                confirmed = confirm_with_diff(file_path, new_content, description)
            else:
                confirmed = confirm_tool_call(description)

            if not confirmed:
                print_tool_skipped()
                return True  # Stop on decline

            result = fs_tools.execute_tool_call(fname, normalized)
            print_tool_result(result)

            if self.session.state["verbose"] and fname == "write_file" and str(result).startswith("Successfully"):
                print_file_content(normalized.get("file_path", ""))

            # Feed back as user message since it's a custom parsing loop
            self.session.add_message(
                "user",
                f"Tool '{fname}' execution result: {result}"
            )

            if fname in self.terminal_tools:
                return True

        return False


def set_project_context_for_modules(context):
    """Propagate project context to all tool modules.

    Args:
        context: ProjectContext instance to set in all modules
    """
    import ayder_cli.tools.impl as impl
    import ayder_cli.tools.utils as utils
    import ayder_cli.tools.registry as registry
    import ayder_cli.tasks as tasks

    impl._default_project_ctx = context
    utils._default_project_ctx = context
    registry._default_project_ctx = context
    tasks._default_project_ctx = context


def run_chat(openai_client=None, config=None, project_root=".",
             permissions=None, iterations=10):
    """
    Main entry point - initializes and delegates to ChatSession and Agent.
    Maintains the dependency injection pattern from TASK-010.

    Args:
        openai_client: Optional OpenAI client instance. If None, creates from config.
        config: Optional config dict/model. If None, loads from file.
        project_root: Optional project root directory (defaults to "."). Used to initialize
            ProjectContext at startup for all tool modules.
        permissions: Set of granted permission categories (e.g. {"r", "w", "x"}).
            Tools matching a granted category are auto-approved without confirmation.
        iterations: Max agentic iterations per message (default: 10).
    """
    # Load config and client (dependency injection from TASK-010)
    cfg = config or load_config()
    
    # Support both dict and Config model for cfg
    if isinstance(cfg, dict):
        base_url = cfg.get("base_url", "http://localhost:11434/v1")
        api_key = cfg.get("api_key", "ollama")
    else:
        base_url = cfg.base_url
        api_key = cfg.api_key
    
    client = openai_client or OpenAI(base_url=base_url, api_key=api_key)

    # Initialize ProjectContext at startup and propagate to all tool modules
    project_ctx = ProjectContext(project_root)
    set_project_context_for_modules(project_ctx)

    # Prepare system prompt with project structure (from TASK-009)
    try:
        project_structure = fs_tools.get_project_structure(max_depth=3)
        macro_context = f"""

### PROJECT STRUCTURE:
```
{project_structure}
```

This is the current project structure. Use `search_codebase` to locate specific code before reading files.
"""
    except Exception:
        macro_context = ""

    enhanced_prompt = SYSTEM_PROMPT + macro_context

    # Initialize session
    chat_session = ChatSession(cfg, enhanced_prompt)
    chat_session.start()

    # Initialize agent with session reference
    agent = Agent(client, cfg, chat_session,
                  permissions=permissions, iterations=iterations)

    # Main loop - now simple and readable
    while True:
        user_input = chat_session.get_input()
        if user_input is None:
            break
        
        # Skip empty input
        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith('/'):
            # Create session dict for backwards compatibility with handle_command
            session_dict = {
                "messages": chat_session.messages,
                "system_prompt": chat_session.system_prompt,
                "state": chat_session.state
            }
            handle_command(user_input, session_dict["messages"], session_dict["system_prompt"], session_dict["state"])
            continue

        # Delegate to agent
        agent.chat(user_input)

if __name__ == "__main__":
    run_chat()
