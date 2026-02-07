## Project Overview

ayder-cli is an interactive AI agent chat client for local LLMs. It connects to an Ollama instance running `qwen3-coder:latest` and provides an autonomous coding assistant with file system tools and shell access. Built with Python 3.12+, using the OpenAI SDK (for Ollama compatibility), prompt-toolkit for the CLI interface, and Textual for an optional TUI dashboard. Current version: **0.7.3**.

## Virtual Environment Setup

The project uses a virtual environment located at `.venv/`. Here's how to work with it:

```bash
# Install dependencies using uv (preferred)
source .venv/bin/activate
uv pip install -e .

# Or install pytest for testing
uv pip install pytest

# Note: On macOS, 'python' may not be available in PATH
# Use 'python3' or the direct venv path instead
```

**Important**: The `source .venv/bin/activate` command may not make `python` or `pytest` available in PATH on some systems. Use these alternatives:

```bash
# Run Python directly from venv (most reliable)
.venv/bin/python3 -m pytest tests/ -v

# Or set PYTHONPATH for imports without installing
PYTHONPATH=src python3 -c "from ayder_cli.tools import tools_schema"

# Run the CLI
.venv/bin/python3 -m ayder_cli
# or if installed: ayder
```

## Testing

The project uses **pytest** for testing with performance-enhancing plugins. All tests are located in the `tests/` directory.

### Installed Pytest Plugins

- **pytest-xdist** - Parallel test execution (use for 100+ tests)
- **pytest-timeout** - Prevent tests from hanging indefinitely
- **pytest-instafail** - Show failures immediately
- **pytest-sugar** - Beautiful progress bar and cleaner output

### Running Tests

```bash
# Run all tests (most reliable method) - fastest for current suite size
.venv/bin/python3 -m pytest tests/ -v

# Run with timeout protection (recommended)
.venv/bin/python3 -m pytest tests/ --timeout=10 -v

# Run with instant failure feedback
.venv/bin/python3 -m pytest tests/ --instafail -v

# Run specific test file
.venv/bin/python3 -m pytest tests/test_cli_file_stdin.py -v

# Run tests with coverage
.venv/bin/python3 -m pytest --cov=ayder_cli --cov-report=term-missing tests/

# Parallel execution (only beneficial for 100+ tests or slow tests)
.venv/bin/python3 -m pytest tests/ -n auto --timeout=10

# Quick verification that imports work
PYTHONPATH=src python3 -c "from ayder_cli.tools import tools_schema; print(len(tools_schema))"
```

**Performance Note**: Sequential execution is fastest for the current test suite (38 tests in ~0.25s). Use `-n auto` only when the suite grows to 100+ tests or includes slow integration tests.

### System Utilities

**uutils-coreutils** is available at `/opt/homebrew/bin/` and provides GNU-compatible utilities:
- `uu-timeout` - Timeout command (alternative to GNU timeout)
- Other uu-* commands for cross-platform compatibility

Example:
```bash
/opt/homebrew/bin/uu-timeout 5 .venv/bin/ayder "test command"
```

**Test Structure** (464+ tests, 96% coverage):
- `test_client.py` - ChatSession, Agent classes, and main chat loop
- `test_cli_file_stdin.py` - CLI file/stdin handling, piped input auto-detection, command mode
- `test_cli_tui.py` - CLI TUI flag integration
- `test_commands.py` - Slash commands (/help, /tools, etc.)
- `test_config.py` - Configuration loading
- `test_config_coverage.py` - Extended config validation coverage
- `test_diff_preview.py` - Diff generation and preview
- `test_main.py` - Entry point (__main__)
- `test_parameter_aliasing.py` - Tool parameter normalization
- `test_parser.py` - XML tool call parser (standard + lazy format)
- `test_search_codebase.py` - Code search functionality
- `test_tasks.py` - Task management functionality
- `test_ui.py` - Terminal UI components
- `test_ui_coverage.py` - Extended UI coverage
- `tools/test_impl.py` - File system tool implementations
- `tools/test_impl_coverage.py` - Extended tool implementation coverage
- `tools/test_registry.py` - Tool registry and execution
- `tools/test_registry_coverage.py` - Extended registry coverage
- `tools/test_schemas.py` - Schema validation
- `tools/test_utils.py` - Tool utilities
- `tools/test_path_security.py` - Path traversal and sandboxing security tests

All tests use pytest fixtures and mocking (no live LLM calls required).

## Architecture

The application is organized into several modules:

- **`src/ayder_cli/client.py`** — Main chat loop, `ChatSession` class, and `Agent` class. Contains the `run_chat()` entry point which supports dependency injection via optional `openai_client`, `config`, and `project_root` parameters. Also contains `call_llm_async()` for async LLM calls (used by the TUI). The `ChatSession` class manages conversation state, history, and user input via prompt-toolkit (emacs keybindings, persistent history at `~/.ayder_chat_history`). The `Agent` class handles the agentic loop (up to 5 consecutive tool calls per user message), tool validation, diff preview for file-modifying tools, and both standard OpenAI tool calls and custom XML-parsed calls. Defines `TERMINAL_TOOLS` set for tools that end the agentic loop. Slash commands are delegated to `handle_command()` from `commands.py`.

- **`src/ayder_cli/cli.py`** — Command-line interface with argparse. Handles CLI flags (`--version`, `--tui`, `-f/--file`, `--stdin`), direct command execution (non-interactive mode), and auto-detection of piped input. The `main()` function routes execution: TUI mode (`--tui`), command mode (direct command passed as positional arg), or interactive chat mode. Supports Unix-style piping: `echo "create test.py" | ayder` auto-enables stdin mode without requiring `--stdin` flag. The `read_input()` function reads from files or stdin with UTF-8 encoding. The `run_command()` function executes a single command via the Agent and returns appropriate exit codes (0=success, 1=error, 2=no response).

- **`src/ayder_cli/prompts.py`** — System prompts and prompt templates. Contains the `SYSTEM_PROMPT` constant that defines the AI agent's behavior and operational principles (extracted from `client.py` for better separation of concerns).

- **`src/ayder_cli/commands.py`** — Command registry system for slash commands. Uses a decorator-based registry pattern (`@register_command("/name")`) for extensibility. Contains `COMMANDS` dict that maps command names to handler functions. The `handle_command()` function dispatches to registered handlers with a session dict containing `messages`, `system_prompt`, and `state`. All 8 commands are registered: `/help`, `/tools`, `/tasks`, `/task-edit`, `/edit`, `/verbose`, `/clear`, `/undo`.

- **`src/ayder_cli/config.py`** — Configuration loading from `~/.ayder/config.toml` with Pydantic validation. The `load_config()` function returns a `Config` model with validated settings for LLM, editor preferences, and UI options. Automatically creates default config on first run.

- **`src/ayder_cli/parser.py`** — Enhanced XML tool call parser. Handles standard format (`<function=name><parameter=key>value</parameter></function>`), lazy format for single-param tools (`<function=name>value</function>` with parameter name inference via `_infer_parameter_name()`), and returns `{"error": "message"}` objects for malformed input.

- **`src/ayder_cli/core/context.py`** — Path validation and sandboxing via `ProjectContext` class. Prevents path traversal attacks (`../`), validates absolute paths stay within project root, handles tilde expansion (`~` paths), and converts between relative/absolute paths. Injected via dependency injection at startup.

- **`src/ayder_cli/banner.py`** — Welcome banner with version detection (via `importlib.metadata`), gothic ASCII art, model/path display, and random tips. Exposes `__version__` and `print_welcome_banner(model, cwd)`.

- **`src/ayder_cli/console.py`** — Centralized Rich console instance with custom theme (`CUSTOM_THEME`) and file extension-to-syntax-language mapping (`EXTENSION_MAP`, 20+ file types). Provides `get_console()` and `get_language_from_path()` helpers.

- **`src/ayder_cli/tui.py`** — Textual TUI (Terminal User Interface) providing an interactive dashboard. Components: `AyderApp` (main app with header, chat view, context panel, input bar, footer), `ChatView` (scrollable message display with Rich panels), `InputBar` (text input + submit button), `ContextPanel` (model info, token usage, file tree), `ConfirmActionScreen` (modal for tool confirmations with diff preview), `SafeModeBlockScreen` (modal for blocked tools). Supports safe mode (blocks `write_file`, `replace_string`, `run_shell_command`), registry middleware/callbacks for TUI integration, and async LLM calls via workers. Entry point: `run_tui(model)`.

- **`src/ayder_cli/tui_helpers.py`** — Helper functions for TUI operations. Contains `is_tool_blocked_in_safe_mode(tool_name, safe_mode)` for safe mode checks.

- **`src/ayder_cli/tools/`** — **Core tools package** with modular architecture:
  - **`impl.py`** — Actual tool implementations (`list_files`, `read_file`, `write_file`, `replace_string`, `run_shell_command`, `search_codebase`, `get_project_structure`)
  - **`schemas.py`** — OpenAI-format JSON schemas for all available tools (10 tools total)
  - **`registry.py`** — Tool registry and execution system:
    - `ToolRegistry` class with middleware support, pre/post-execute callbacks, and execution timing
    - `ToolExecutionStatus` enum (`STARTED`, `SUCCESS`, `ERROR`)
    - `ToolExecutionResult` dataclass (tool_name, arguments, status, result, error, duration_ms)
    - `create_default_registry()` factory function for fully configured registry
    - `normalize_tool_arguments()` for parameter aliasing, path resolution via ProjectContext, and type coercion
    - `validate_tool_call()` for schema validation
    - `PARAMETER_ALIASES` and `PATH_PARAMETERS` constants
  - **`utils.py`** — Utility functions for tool operations, including `prepare_new_content()` for preparing file content before write/replace operations (supports both JSON string and dict arguments)
  - **`__init__.py`** — Complete public API exports (all tools, schemas, registry, and utilities)

- **`src/ayder_cli/tasks.py`** — Task management system for creating, listing, showing, and implementing tasks stored in `.ayder/tasks/`

- **`src/ayder_cli/ui.py`** — Terminal UI utilities for formatted output, boxes, and user prompts using Rich

Entry points:
- **CLI**: `ayder_cli.cli:main` (registered as the `ayder` CLI script in pyproject.toml)
- **Legacy/TUI**: `ayder_cli.client:run_chat` (can be called directly for programmatic use)

### ChatSession and Agent Classes

The `client.py` module implements two core classes extracted from the original monolithic `run_chat()`:

**ChatSession** — Manages conversation state, history, and user input:
```python
class ChatSession:
    def __init__(self, config, system_prompt)
    def start()            # Initialize prompt session, print banner
    def add_message(role, content, **kwargs)
    def get_input() -> str | None  # prompt-toolkit input, returns None for exit
    def get_messages() -> list
    def clear_messages(keep_system=True)
    def render_history()   # Debug display
```

**Agent** — Handles LLM API interaction and the agentic tool execution loop:
```python
class Agent:
    def __init__(self, openai_client, config, session: ChatSession)
    def chat(user_input)           # Main agentic loop (up to 5 tool calls)
    def _execute_tool_loop(tool_calls) -> bool  # Standard OpenAI tool calls
    def _handle_tool_call(tool_call) -> dict | None  # Single tool: validate, confirm, execute
    def _handle_custom_calls(custom_calls) -> bool   # XML-parsed tool calls
```

### Tools Package Details

The `tools/` package follows a modular architecture with clear separation of concerns:

**Import Paths:**
```python
from ayder_cli.tools import ToolRegistry, create_default_registry, normalize_tool_arguments
from ayder_cli.tools.schemas import tools_schema
from ayder_cli.core.context import ProjectContext
```

**Tool Execution Flow:**
```python
from ayder_cli.tools import ToolRegistry, create_default_registry
from ayder_cli.core.context import ProjectContext

# Create a registry with project context (DI)
ctx = ProjectContext(".")
registry = create_default_registry(ctx)
result = registry.execute("read_file", {"file_path": "test.py"})
```

**Registry Features:**
- Middleware support: `registry.add_middleware(func)` — Pre-execution checks (e.g., safe mode blocking via `PermissionError`)
- Pre-execute callbacks: `registry.add_pre_execute_callback(func)` — Called before tool runs
- Post-execute callbacks: `registry.add_post_execute_callback(func)` — Receives `ToolExecutionResult` with timing
- Schema access: `registry.get_schemas()` — Returns OpenAI-format tool schemas

**Parameter Normalization:**
```python
from ayder_cli.tools import normalize_tool_arguments

# Input: Various parameter names
args = {"path": "file.txt"}  # alias
normalized = normalize_tool_arguments("read_file", args)
# Output: {"file_path": "/absolute/path/to/file.txt"}  # canonical + resolved via ProjectContext
```

### ProjectContext and Path Security

All file operations are sandboxed via `ProjectContext`:

```python
from ayder_cli.core.context import ProjectContext

ctx = ProjectContext(".")             # Root is current directory (resolved)
path = ctx.validate_path("src/main.py")   # Returns absolute Path within root
path = ctx.validate_path("../../etc/passwd")  # Raises ValueError (traversal blocked)
relative = ctx.to_relative(absolute_path)     # Convert back to relative string
```

**Integration:** At startup, `cli.py:_build_services()` creates a `ProjectContext` and injects it into `ToolRegistry` and `ToolExecutor` via constructor arguments. The `prepare_new_content()` utility accepts an optional `project_ctx` parameter for path resolution.

### Command Registry Pattern

The `commands.py` module uses a registry pattern for slash command handling:

**Command Registration:**
- `COMMANDS` — Dictionary mapping command names (e.g., `/help`) to handler functions
- `register_command(name)` — Decorator for registering command handlers
- Each command handler has signature: `def cmd_name(args: str, session: dict) -> bool`

**Session Object:**
- Currently a dict containing `messages`, `system_prompt`, and `state`
- `handle_command()` bridges the ChatSession attributes into this dict format

**Adding New Commands:**
```python
@register_command("/newcmd")
def cmd_newcmd(args, session):
    """Command description."""
    # Implementation
    return True
```

### Textual TUI

The TUI (`tui.py`) provides an alternative dashboard interface built with Textual:

**Layout:** Header (title + clock) | Main area: ChatView (3fr) + ContextPanel (1fr) | InputBar | Footer (shortcuts)

**Key Components:**
- `AyderApp` — Main application with safe mode support, registry callbacks/middleware, async LLM workers
- `ChatView` — Scrollable chat with typed messages (USER/ASSISTANT/TOOL_CALL/TOOL_RESULT/SYSTEM)
- `InputBar` — Text input + Send button with enable/disable support
- `ContextPanel` — Model info, token counter, active file tree
- `ConfirmActionScreen` — Modal with diff preview for file-modifying tool confirmations
- `SafeModeBlockScreen` — Modal shown when a tool is blocked in safe mode

**Keybindings:** Ctrl+Q (quit), Ctrl+C (cancel operation), Ctrl+L (clear chat)

**Safe Mode:** Blocks `run_shell_command`, `write_file`, `replace_string` via registry middleware.

**Entry Point:** `run_tui(model="default")` or `python -m ayder_cli.tui`

## Key Design Details

- **Dependency Injection**: The `run_chat()` function accepts optional `openai_client`, `config`, and `project_root` parameters, enabling testing with mocks and custom configurations.

- **CLI with Piped Input Auto-Detection**: The CLI automatically detects piped input (e.g., `echo "text" | ayder`) by checking `sys.stdin.isatty()`. When stdin is piped and no explicit mode flags are set (`--file`, `--stdin`, `--tui`), the CLI auto-enables stdin mode, matching behavior of standard Unix tools. Explicit `--stdin` flag still supported for backwards compatibility.

- **Modular Tools Package**: The `tools/` package provides a clean separation with `impl.py` (implementations), `schemas.py` (definitions), `registry.py` (execution + middleware + callbacks), `definition.py` (ToolDefinition dataclass), and `utils.py` (helpers).

- **Tool Registry with Middleware**: `ToolRegistry` class supports middleware for pre-execution checks (safe mode), pre/post-execute callbacks for UI integration (TUI tool call display), and execution timing via `ToolExecutionResult`.

- **Path Security via ProjectContext**: All file tool operations are sandboxed to the project root. `ProjectContext` validates paths, blocks traversal attacks, and handles tilde expansion. Injected via DI at startup.

- **Configuration with Pydantic**: Config validation using Pydantic models with field validators. The `Config` model validates `base_url` (http/https), `num_ctx` (positive integer), and other settings. Supports both dict and Config model formats throughout.

- **Dual tool calling**: Supports both standard OpenAI function calling (`msg.tool_calls`) and a custom XML-like fallback parsed by `parse_custom_tool_calls()` using `<function=name><parameter=key>value</parameter></function>` syntax (plus lazy format for single-param tools). Standard calls feed results back as `tool` role messages; custom calls feed results back as `user` role messages.

- **Async LLM Support**: `call_llm_async()` wraps synchronous OpenAI calls in a `ThreadPoolExecutor` for non-blocking TUI interaction.

- **Shell command timeout**: `run_shell_command` has a 60-second timeout.
