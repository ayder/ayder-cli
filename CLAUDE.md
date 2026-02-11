## Project Overview

ayder-cli is an interactive AI agent chat client for local LLMs. It connects to an Ollama instance running `qwen3-coder:latest` and provides an autonomous coding assistant with file system tools and shell access. Built with Python 3.12+, using the OpenAI SDK (for Ollama compatibility), prompt-toolkit for the CLI interface, and Textual for an optional TUI dashboard. Current version is defined in `pyproject.toml` (see `version` field).

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

**Performance Note**: Sequential execution is fastest for the current test suite (~615 tests in ~1.6s). Use `-n auto` only when the suite grows significantly or includes slow integration tests.

### System Utilities

**uutils-coreutils** is available at `/opt/homebrew/bin/` and provides GNU-compatible utilities:
- `uu-timeout` - Timeout command (alternative to GNU timeout)
- Other uu-* commands for cross-platform compatibility

Example:
```bash
/opt/homebrew/bin/uu-timeout 5 .venv/bin/ayder "test command"
```

**Test Structure** (615+ tests, 96% coverage):
- `test_client.py` - ChatSession, Agent classes
- `test_chat_loop.py` - ChatLoop, IterationController, ToolCallHandler, CheckpointManager
- `test_checkpoint_manager.py` - CheckpointManager for checkpoint/restore cycles
- `test_cli_file_stdin.py` - CLI file/stdin handling, piped input auto-detection, command mode
- `test_cli_tui.py` - CLI TUI flag integration
- `test_commands.py` - Slash commands (/help, /tools, etc.)
- `test_config.py` - Configuration loading
- `test_config_coverage.py` - Extended config validation coverage
- `test_diff_preview.py` - Diff generation and preview
- `test_main.py` - Entry point (__main__)
- `test_memory.py` - Cross-session memory tools (save_memory, load_memory) in `memory.py`
- `test_checkpoint_manager.py` - Checkpoint management in `checkpoint_manager.py`
- `test_notes.py` - Note creation functionality
- `test_process_manager.py` - Background process management (ProcessManager, 4 tool functions, config validation)
- `test_parameter_aliasing.py` - Tool parameter normalization
- `test_parser.py` - XML tool call parser (standard + lazy format)
- `test_search_codebase.py` - Code search functionality
- `test_tasks.py` - Task management functionality
- `test_ui.py` - Terminal UI components
- `test_ui_coverage.py` - Extended UI coverage
- `tools/test_impl.py` - File system tool implementations (incl. insert_line, delete_line, get_file_info)
- `tools/test_impl_coverage.py` - Extended tool implementation coverage
- `tools/test_registry.py` - Tool registry and execution
- `tools/test_registry_coverage.py` - Extended registry coverage
- `tools/test_schemas.py` - Schema validation
- `tools/test_utils.py` - Tool utilities
- `tools/test_path_security.py` - Path traversal and sandboxing security tests

All tests use pytest fixtures and mocking (no live LLM calls required).

## Architecture

The application is organized into several modules:

- **`src/ayder_cli/client.py`** — `ChatSession` class, `Agent` class, and `call_llm_async()` for async LLM calls (used by the TUI). The `ChatSession` class manages conversation state, history, user input via prompt-toolkit (emacs keybindings, persistent history at `~/.ayder_chat_history`). The `get_input()` method displays a cyan `❯` prompt. The `Agent` class delegates to `ChatLoop` for the agentic loop. Supports both standard OpenAI tool calls and custom XML-parsed calls. Slash commands are delegated to `handle_command()` from `commands/`.

- **`src/ayder_cli/chat_loop.py`** — **Core chat loop logic** with separated concerns:
  - `ChatLoop` — Orchestrates the agentic conversation loop, manages iteration counting, memory checkpoints, and tool execution
  - `IterationController` — Manages iteration counting and triggers memory checkpoints when limits are reached
  - `ToolCallHandler` — Parses and executes tool calls (both standard OpenAI and custom XML)
  - `CheckpointManager` — Creates memory checkpoints by asking LLM to summarize and resets conversation context
  - `LoopConfig` — Configuration dataclass for loop parameters (max_iterations, model, permissions, etc.)
  - Memory checkpoint cycle: When iteration limit reached → Ask LLM to write summary → Reset conversation → Load memory → Continue with fresh context (prevents context window overflow)

- **`src/ayder_cli/checkpoint_manager.py`** — **Checkpoint management**. `CheckpointManager` class handles saving/loading conversation summaries to `.ayder/memory/current_memory.md`. Used by `ChatLoop` to prevent "content rotting" during long-running tasks. Tracks checkpoint cycles and provides prompt builders (`build_checkpoint_prompt()`, `build_restore_prompt()`, `build_quick_restore_message()`). All prompt templates imported from `prompts.py` (no hardcoded prompts).

- **`src/ayder_cli/cli.py`** — CLI entry point with argument parsing. Handles CLI flags (`--version`, `--tui`, `-f/--file`, `--stdin`, `-I/--iterations`), auto-detection of piped input, and delegates execution to `cli_runner.py`. Supports Unix-style piping: `echo "create test.py" | ayder` auto-enables stdin mode without requiring `--stdin` flag. Contains only `create_parser()` and `read_input()` — all execution logic moved to `cli_runner.py`.

- **`src/ayder_cli/cli_runner.py`** — **CLI execution logic** with separated concerns:
  - `_build_services()` — Composition root that creates `ProcessManager` and `CheckpointManager`, returns 6-tuple `(config, llm_provider, tool_executor, project_ctx, enhanced_system, checkpoint_manager)`. Enhances system prompt with project structure macro.
  - `InteractiveRunner` — Runner class for REPL mode (`run_interactive()`). Manages session lifecycle, command dispatch, and agent interaction loop.
  - `CommandRunner` — Runner class for single command execution (`run_command()`). Executes one prompt and exits.
  - `TaskRunner` — Runner class for task CLI operations (`--tasks`, `--implement`, `--implement-all`).
  - Clean separation: CLI parsing (cli.py) → Execution (cli_runner.py) → Core logic (client.py/chat_loop.py)

- **`src/ayder_cli/prompts.py`** — **Centralized prompt templates** organized by usage. Each prompt has a REASON comment explaining why the LLM is being prompted:
  - **Core prompts**: `SYSTEM_PROMPT` — defines AI role and capabilities
  - **Project structure**: `PROJECT_STRUCTURE_MACRO_TEMPLATE` — provides codebase overview at startup so LLM knows what files exist
  - **Task planning**: `PLANNING_PROMPT_TEMPLATE` — transforms high-level requests into actionable tasks
  - **Task execution**: `TASK_EXECUTION_PROMPT_TEMPLATE`, `TASK_EXECUTION_ALL_PROMPT_TEMPLATE` — implements specific or all pending tasks
  - **Conversation management**: `CLEAR_COMMAND_RESET_PROMPT`, `SUMMARY_COMMAND_PROMPT_TEMPLATE`, `LOAD_MEMORY_COMMAND_PROMPT_TEMPLATE`, `COMPACT_COMMAND_PROMPT_TEMPLATE` — manage conversation state
  - **Memory checkpoints**: `MEMORY_CHECKPOINT_PROMPT_TEMPLATE`, `MEMORY_RESTORE_PROMPT_TEMPLATE`, `MEMORY_QUICK_RESTORE_MESSAGE_TEMPLATE`, `MEMORY_NO_MEMORY_MESSAGE` — automatic checkpoint/restore at iteration limits

- **`src/ayder_cli/commands/`** — Command registry system for slash commands. Uses a class-based registry pattern (`@register_command` decorator on `BaseCommand` subclasses). The `handle_command()` function dispatches to registered handlers with a `SessionContext` dataclass. 14 commands registered: `/help`, `/tools`, `/tasks`, `/task-edit`, `/implement`, `/implement-all`, `/edit`, `/verbose`, `/clear`, `/compact`, `/summary`, `/load`, `/undo`, `/plan`. `commands/system.py` imports all prompt templates from `prompts.py` (no hardcoded prompts).

- **`src/ayder_cli/parser.py`** — Enhanced XML tool call parser. Handles standard format (`<function=name><parameter=key>value</parameter></function>`), lazy format for single-param tools (`<function=name>value</function>` with parameter name inference via `_infer_parameter_name()`), and returns `{"error": "message"}` objects for malformed input.

- **`src/ayder_cli/core/config.py`** — Configuration loading from `~/.ayder/config.toml` with Pydantic validation. The `load_config()` function returns a `Config` model with validated settings for LLM, editor preferences, UI options, and `max_background_processes` (1-20, default 5). Automatically creates default config on first run.

- **`src/ayder_cli/core/context.py`** — `ProjectContext` class for path validation and sandboxing. Prevents path traversal attacks (`../`), validates absolute paths stay within project root, handles tilde expansion. Also defines `SessionContext` dataclass (holds `config`, `project`, `messages`, `state`, `system_prompt`) used by commands.

- **`src/ayder_cli/core/result.py`** — Shared result types: `ToolSuccess(str)` and `ToolError(str)` — str subclasses for zero-breakage. All tool functions in `impl.py`, `tasks.py`, `notes.py`, `memory.py`, and `process_manager.py` return these types. `ToolError` has a `.category` property (`"security"`, `"validation"`, `"execution"`, `"general"`). Re-exported from `tools/__init__.py`.

- **`src/ayder_cli/banner.py`** — Welcome banner with version detection (via `importlib.metadata`), gothic ASCII art, model/path display, and random tips. Exposes `__version__` and `print_welcome_banner(model, cwd)`.

- **`src/ayder_cli/console.py`** — Centralized Rich console instance with custom theme (`CUSTOM_THEME`) and file extension-to-syntax-language mapping (`EXTENSION_MAP`, 20+ file types). Provides `get_console()` and `get_language_from_path()` helpers.

- **`src/ayder_cli/tui.py`** — Textual TUI (Terminal User Interface) providing an interactive dashboard. Components: `AyderApp` (main app with header, chat view, context panel, input bar, footer), `ChatView` (scrollable message display with Rich panels), `InputBar` (text input + submit button), `ContextPanel` (model info, token usage, file tree), `ConfirmActionScreen` (modal for tool confirmations with diff preview), `SafeModeBlockScreen` (modal for blocked tools). Supports safe mode (blocks `write_file`, `replace_string`, `run_shell_command`, `run_background_process`, `kill_background_process`), registry middleware/callbacks for TUI integration, and async LLM calls via workers. Entry point: `run_tui(model)`.

- **`src/ayder_cli/tui_helpers.py`** — Helper functions for TUI operations. Contains `is_tool_blocked_in_safe_mode(tool_name, safe_mode)` for safe mode checks.

- **`src/ayder_cli/tools/`** — **Core tools package** with modular architecture:
  - **`definition.py`** — `ToolDefinition` frozen dataclass with tool metadata. `TOOL_DEFINITIONS` list (20 tools) and `TOOL_DEFINITIONS_BY_NAME` dict for lookup.
  - **`impl.py`** — Core tool implementations (`list_files`, `read_file`, `write_file`, `replace_string`, `insert_line`, `delete_line`, `get_file_info`, `run_shell_command`, `search_codebase`, `get_project_structure`)
  - **`schemas.py`** — OpenAI-format JSON schemas (`tools_schema = [td.to_openai_schema() for td in TOOL_DEFINITIONS]`)
  - **`registry.py`** — Tool registry and execution system:
    - `ToolRegistry` class with middleware support, pre/post-execute callbacks, execution timing, and `process_manager` DI
    - `get_schemas()` — Returns all tool schemas
    - `validate_tool_call()` — Validates against `TOOL_DEFINITIONS_BY_NAME` (all tools, not mode-filtered)
    - `create_default_registry(project_ctx, process_manager=None)` factory function for fully configured registry
    - `normalize_tool_arguments()` for parameter aliasing, path resolution via ProjectContext, and data-driven type coercion from schema
    - DI injection: inspects tool function signatures and injects `project_ctx` and/or `process_manager` as needed
  - **`utils.py`** — Utility functions for tool operations, including `prepare_new_content()` for preparing file content before write/replace/insert/delete operations (supports both JSON string and dict arguments)
  - **`__init__.py`** — Complete public API exports (all tools, schemas, registry, and utilities)

- **`src/ayder_cli/notes.py`** — Note management. Creates markdown notes in `.ayder/notes/` with YAML frontmatter (title, date, tags). `create_note()` function with slugified filenames. Imports from `core/result.py` (NOT from `tools/`) to avoid circular imports.

- **`src/ayder_cli/memory.py`** — Cross-session memory storage. Saves memories as JSON Lines (`.jsonl`) in `.ayder/memory/memories.jsonl`. Each entry has `id`, `content`, `category`, `tags`, `timestamp`. `save_memory()` appends entries; `load_memory()` reads, filters by category/query, and returns most recent first. Imports from `core/result.py` (NOT from `tools/`) to avoid circular imports.

- **`src/ayder_cli/process_manager.py`** — Background process management. `ProcessManager` class manages long-running processes (dev servers, watchers, builds) with `ManagedProcess` dataclass tracking id, command, Popen, status, exit_code, and ring-buffer output capture (stdout/stderr, maxlen=500 lines each via daemon threads). Enforces configurable max running process limit, provides SIGTERM/SIGKILL lifecycle, and atexit cleanup. Exposes 4 tool functions: `run_background_process`, `get_background_output`, `kill_background_process`, `list_background_processes`. Imports from `core/result.py` (NOT from `tools/`) to avoid circular imports.

- **`src/ayder_cli/tasks.py`** — Task management system for creating, listing, showing, and implementing tasks stored in `.ayder/tasks/`. Uses slug-based filenames (`TASK-001-add-auth.md`) with backwards-compatible support for legacy `TASK-001.md` format. Includes `_title_to_slug()` helper and `_get_task_path_by_id()` glob-based lookup. Exposes two tool functions: `list_tasks(project_ctx, format="list", status="pending")` returns newline-separated relative paths of pending tasks by default (or formatted table with `format="table"`; use `status="all"` for all tasks, `status="done"` for completed), and `show_task(project_ctx, identifier)` accepts flexible input (relative path, filename, task ID, or slug) with fallback strategies for task lookup.

- **`src/ayder_cli/ui.py`** — Terminal UI utilities for formatted output, boxes, and user prompts using Rich

Entry points:
- **CLI**: `ayder_cli.cli:main` (registered as the `ayder` CLI script in pyproject.toml)
- **Legacy/TUI**: `ayder_cli.client:run_chat` (can be called directly for programmatic use)

### ChatSession, Agent, and ChatLoop Classes

The `client.py` module implements two core classes, delegating loop logic to `chat_loop.py`:

**ChatSession** — Manages conversation state, history, and user input:
```python
class ChatSession:
    def __init__(self, config, system_prompt, permissions=None, iterations=50, checkpoint_manager=None)
    def start()                        # Initialize prompt session, print banner
    def add_message(role, content, **kwargs)
    def append_raw(message)            # Append pre-formed message (e.g., tool_calls)
    def get_input() -> str | None      # Cyan "❯" prompt
    def get_messages() -> list
    def clear_messages(keep_system=True)
    def render_history()               # Debug display
```

**Agent** — High-level interface that delegates to `ChatLoop`:
```python
class Agent:
    def __init__(self, llm_provider: LLMProvider, tools: ToolExecutor, session: ChatSession)
    def chat(user_input) -> str | None  # Delegates to ChatLoop.run()
```

**ChatLoop** — Orchestrates the agentic conversation loop (in `chat_loop.py`):
```python
class ChatLoop:
    def __init__(self, llm_provider, tool_executor, session, config: LoopConfig, checkpoint_manager=None)
    def run(user_input) -> str | None   # Main loop with memory checkpoint support
    
# Supporting classes:
class IterationController:    # Manages iteration counting and checkpoint triggers
class ToolCallHandler:        # Parses and executes tool calls
class CheckpointManager:      # Creates/restores memory checkpoints
```

**Memory Checkpoint Cycle:**
The `-I/--iterations` flag sets a high-watermark for automatic memory checkpoints. When the iteration limit is reached:
1. `CheckpointManager` asks the LLM to summarize the conversation
2. Summary is saved to `.ayder/memory/current_memory.md`
3. Conversation is reset (keeping only system prompt)
4. Memory is loaded back as a user message
5. Iteration counter resets to 0, allowing the agent to continue with fresh context

This prevents "content rotting" in long-running tasks while maintaining task continuity.

### Tools Package Details

The `tools/` package and `chat_loop.py` follow a modular architecture with clear separation of concerns:

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
from ayder_cli.process_manager import ProcessManager

# Create a registry with project context and process manager (DI)
ctx = ProjectContext(".")
pm = ProcessManager(max_processes=5)
registry = create_default_registry(ctx, process_manager=pm)
result = registry.execute("read_file", {"file_path": "test.py"})
```

**Registry Features:**
- Middleware support: `registry.add_middleware(func)` — Pre-execution checks (e.g., safe mode blocking via `PermissionError`)
- Pre-execute callbacks: `registry.add_pre_execute_callback(func)` — Called before tool runs
- Post-execute callbacks: `registry.add_post_execute_callback(func)` — Receives `ToolExecutionResult` with timing
- Schema access: `registry.get_schemas()` — Returns all tool schemas

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

**Integration:** At startup, `cli.py:_build_services()` creates a `ProjectContext` and `MemoryManager`, then injects them into `ToolRegistry`, `ToolExecutor`, and `ChatSession` via constructor arguments. The `prepare_new_content()` utility accepts an optional `project_ctx` parameter for path resolution.

### Command Registry Pattern

The `commands/` package uses a class-based registry pattern for slash command handling:

**Command Registration:**
- `CommandRegistry` — Singleton registry mapping command names to `BaseCommand` instances
- `@register_command` — Class decorator that instantiates and registers a `BaseCommand` subclass
- Each command subclass implements `name`, `description` (properties) and `execute(args, session) -> bool`

**Session Object:**
- `SessionContext` dataclass from `core/context.py` containing `config`, `project`, `messages`, `state`, `system_prompt`
- The enhanced prompts (with project structure macro) are passed through `SessionContext` so commands like `/plan` can use them when swapping modes
- `handle_command()` dispatches to the correct command handler

**Adding New Commands:**
```python
@register_command
class MyCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/mycommand"

    @property
    def description(self) -> str:
        return "Does something useful"

    def execute(self, args: str, session: SessionContext) -> bool:
        # Implementation
        return True
```

### Adding New Tools

When adding a new tool to ayder-cli, follow these steps:

1. **Implement the tool function** in the appropriate module:
   - Core file operations → `tools/impl.py`
   - Task management → `tasks.py`
   - Note management → `notes.py`
   - Memory management → `memory.py`
   - Background processes → `process_manager.py`
   - Or create a new module if it's a new category

2. **Add ToolDefinition** to `tools/definition.py`:
   ```python
   ToolDefinition(
       name="my_new_tool",
       description="Clear description of what this tool does",
       description_template="Action description with {param} placeholders",
       func_ref="module.path:function_name",  # e.g., "ayder_cli.tools.impl:my_new_tool"
       parameters={
           "type": "object",
           "properties": {
               "param_name": {
                   "type": "string",
                   "description": "Parameter description",
               },
           },
           "required": ["param_name"],
       },
       permission="r",  # "r" (read), "w" (write), or "x" (execute)
       safe_mode_blocked=False,  # True if tool should be blocked in safe mode
   ),
   ```

3. **Update `prompts.py`** — **CRITICAL**: Add the new tool to the CAPABILITIES section in `SYSTEM_PROMPT` so the LLM knows it exists:
   ```python
   ### CAPABILITIES:
   You can perform these actions:
   - **Category Name**: `my_new_tool` to do something useful, ...
   ```

4. **Add tests** in `tests/` directory:
   - Test the tool function implementation
   - Test error cases
   - Update `tests/tools/test_schemas.py` to include the new tool in `expected_tools` set
   - Update tool count in `tests/tools/test_registry.py` (e.g., from 19 to 20)

5. **Update documentation**:
   - Add to tool table in `README.md`
   - Update tool count in `CLAUDE.md` (e.g., "19 tools" → "20 tools")
   - Update permission tables if adding a new permission category

The tool will be automatically registered via the `func_ref` auto-discovery mechanism in `create_default_registry()`.

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

**Safe Mode:** Blocks `run_shell_command`, `write_file`, `replace_string`, `insert_line`, `delete_line`, `run_background_process`, `kill_background_process` via registry middleware.

**Entry Point:** `run_tui(model="default")` or `python -m ayder_cli.tui`

## Key Design Details

- **Dependency Injection**: `_build_services()` is the composition root, creating all dependencies. `ChatSession` and `Agent` accept injected providers. Testing uses mocks throughout — no live LLM calls required.

- **CLI with Piped Input Auto-Detection**: The CLI automatically detects piped input (e.g., `echo "text" | ayder`) by checking `sys.stdin.isatty()`. When stdin is piped and no explicit mode flags are set (`--file`, `--stdin`, `--tui`), the CLI auto-enables stdin mode, matching behavior of standard Unix tools. Explicit `--stdin` flag still supported for backwards compatibility.

- **Modular Tools and Chat Loop**: The `tools/` package provides clean separation with `impl.py` (10 core tool implementations), `schemas.py` (definitions), `registry.py` (execution + middleware + callbacks + DI), `definition.py` (ToolDefinition dataclass), and `utils.py` (helpers). The `chat_loop.py` module separates iteration management, tool handling, and memory checkpoints from `client.py`. Additional modules `notes.py`, `memory.py`, `checkpoint_manager.py`, `process_manager.py`, and `tasks.py` provide specialized functionality (3 memory/note tools, 4 background process tools, 2 task management tools, checkpoint management). 20 tools total.

- **Planning Mode**: Activated via `/plan` command. Injects `PLANNING_PROMPT` as a user message to guide the LLM to act as a "Task Master" for task creation.

- **Tool Registry with Middleware**: `ToolRegistry` class supports middleware for pre-execution checks (safe mode), pre/post-execute callbacks for UI integration (TUI tool call display), and execution timing via `ToolExecutionResult`.

- **Path Security via ProjectContext**: All file tool operations are sandboxed to the project root. `ProjectContext` validates paths, blocks traversal attacks, and handles tilde expansion. Injected via DI at startup.

- **Configuration with Pydantic**: Config validation using Pydantic models with field validators. The `Config` model validates `base_url` (http/https), `num_ctx` (positive integer), `max_background_processes` (1-20, default 5), and other settings. Supports both dict and Config model formats throughout.

- **Dual tool calling**: Supports both standard OpenAI function calling (`msg.tool_calls`) and a custom XML-like fallback parsed by `parse_custom_tool_calls()` using `<function=name><parameter=key>value</parameter></function>` syntax (plus lazy format for single-param tools). Standard calls feed results back as `tool` role messages; custom calls feed results back as `user` role messages.

- **Async LLM Support**: `call_llm_async()` wraps synchronous OpenAI calls in a `ThreadPoolExecutor` for non-blocking TUI interaction.

- **Shell command timeout**: `run_shell_command` has a 60-second timeout. For long-running commands (servers, watchers, builds), use `run_background_process` instead.

- **Background Process Management**: `ProcessManager` manages long-running processes with ring-buffer output capture (500 lines each for stdout/stderr via daemon reader threads). Enforces a configurable max running process limit (`max_background_processes` in config). Process lifecycle: SIGTERM → 5s wait → SIGKILL fallback. All running processes are cleaned up at exit via `atexit`. Injected into `ToolRegistry` via `create_default_registry(project_ctx, process_manager=pm)`.
