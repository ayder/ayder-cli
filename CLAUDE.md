## Project Overview

ayder-cli is an AI agent chat client for local LLMs. It connects to an Ollama instance running `qwen3-coder:latest` and provides an autonomous coding assistant with file system tools and shell access. Built with Python 3.12+, using the OpenAI SDK (for Ollama compatibility), Textual for the default TUI dashboard, and prompt-toolkit for a fallback CLI REPL (`--cli`). Current version is defined in `pyproject.toml` (see `version` field).

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

# Run the app (launches TUI by default)
.venv/bin/python3 -m ayder_cli
# or if installed: ayder
# Classic CLI REPL: ayder --cli
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

**Performance Note**: Sequential execution is fastest for the current test suite (~796 tests in ~1.5s). Use `-n auto` only when the suite grows significantly or includes slow integration tests.

### System Utilities

**uutils-coreutils** is available at `/opt/homebrew/bin/` and provides GNU-compatible utilities:
- `uu-timeout` - Timeout command (alternative to GNU timeout)
- Other uu-* commands for cross-platform compatibility

Example:
```bash
/opt/homebrew/bin/uu-timeout 5 .venv/bin/ayder "test command"
```

**Test Structure** (796+ tests, 96% coverage):
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

The application has two interfaces: a **Textual TUI** (default) and a **prompt-toolkit CLI REPL** (`--cli`). Both share the same core: tools package, prompts, config, and services.

### Entry Points

- **Default (TUI)**: `ayder` → `cli.py:main()` → `tui/__init__.py:run_tui()` → `tui/app.py:AyderApp`
- **CLI REPL**: `ayder --cli` → `cli.py:main()` → `cli_runner.py:run_interactive()`
- **Command mode**: `ayder "prompt"` → `cli.py:main()` → `cli_runner.py:run_command()`
- **Task CLI**: `ayder --tasks` / `--implement` / `--implement-all` → `cli_runner.py`

### Module Map

- **`src/ayder_cli/cli.py`** — CLI entry point with argument parsing. Handles flags (`--version`, `--cli`, `-f/--file`, `--stdin`, `-I/--iterations`, `--tasks`, `--implement`, `--implement-all`), auto-detection of piped input. TUI is the default; `--cli` falls back to prompt-toolkit REPL. Contains only `create_parser()` and `read_input()` — all execution logic in `cli_runner.py`.

- **`src/ayder_cli/tui/`** — **Textual TUI package** (default interface). Modular architecture split across multiple files:
  - **`__init__.py`** — `run_tui(model, safe_mode, permissions)` entry point. Runs `AyderApp` inline.
  - **`app.py`** — `AyderApp` main Textual application. Manages LLM pipeline (`_process_llm_response`, `_handle_llm_response`), tool execution with parallel auto-approved + sequential confirmation flow, `ProcessManager` injection, safe mode middleware, diff preview generation, async LLM calls via workers, XML tool call fallback, and `json.loads` error handling. Timer management: `_thinking_timer` for LLM wait animation, `_tools_timer` for tool execution spinner (wrapped in try/finally to prevent leaks).
  - **`commands.py`** — TUI slash command handlers. Each handler has signature `(app, args, chat_view) -> None`. `COMMAND_MAP` dict dispatches by command name. 13 commands: `/help`, `/model`, `/tasks`, `/tools`, `/verbose`, `/compact`, `/plan`, `/ask`, `/implement`, `/implement-all`, `/task-edit`, `/archive-completed-tasks`, `/permission`. TUI `/help` shows commands from `COMMAND_MAP` (not CLI registry).
  - **`widgets.py`** — UI widgets: `ChatView` (scrollable message display), `ToolPanel` (tool execution display with spinners), `CLIInputBar` (text input with Enter-to-submit via `_SubmitTextArea`, tab completion, command history), `StatusBar` (model, permissions, token count), `AutoCompleteInput`.
  - **`screens.py`** — Modal screens: `CLIConfirmScreen` (tool confirmation with diff preview and approve/deny/instruct actions), `CLIPermissionScreen` (toggle r/w/x permissions), `CLISafeModeScreen` (blocked tool notification), `CLISelectScreen` (generic list selector), `TaskEditScreen` (in-app task editor with TextArea).
  - **`types.py`** — Shared types: `MessageType` enum, `ConfirmResult` dataclass.
  - **`helpers.py`** — `is_tool_blocked_in_safe_mode()` helper function.
  - **`theme_manager.py`** — `get_theme_css()` loads CSS from the active theme in `themes/`.

- **`src/ayder_cli/themes/`** — Theme CSS files (`claude.py`, `original.py`). Each exports a CSS string used by `AyderApp`.

- **`src/ayder_cli/client.py`** — `ChatSession` class (conversation state, prompt-toolkit input for `--cli` mode, persistent history at `~/.ayder_chat_history`), `Agent` class (delegates to `ChatLoop`), and `call_llm_async()` for non-blocking LLM calls (used by TUI).

- **`src/ayder_cli/chat_loop.py`** — **Core chat loop logic** (used by `--cli` mode via `Agent`):
  - `ChatLoop` — Orchestrates the agentic conversation loop, manages iteration counting, memory checkpoints, and tool execution
  - `IterationController` — Manages iteration counting and triggers memory checkpoints when limits are reached
  - `ToolCallHandler` — Parses and executes tool calls (both standard OpenAI and custom XML)
  - `CheckpointManager` — Creates memory checkpoints by asking LLM to summarize and resets conversation context
  - `LoopConfig` — Configuration dataclass for loop parameters (max_iterations, model, permissions, etc.)

- **`src/ayder_cli/checkpoint_manager.py`** — `CheckpointManager` class handles saving/loading conversation summaries to `.ayder/memory/current_memory.md`. Used by `ChatLoop` to prevent "content rotting" during long-running tasks. All prompt templates imported from `prompts.py`.

- **`src/ayder_cli/cli_runner.py`** — **CLI execution logic** (for `--cli` REPL and command mode):
  - `_build_services()` — Composition root that creates `ProcessManager` and `CheckpointManager`, returns services tuple. Enhances system prompt with project structure macro.
  - `InteractiveRunner` — Runner class for REPL mode (`run_interactive()`).
  - `CommandRunner` — Runner class for single command execution (`run_command()`).
  - `TaskRunner` — Runner class for task CLI operations (`--tasks`, `--implement`, `--implement-all`).

- **`src/ayder_cli/prompts.py`** — **Centralized prompt templates** organized by usage. Each prompt has a REASON comment:
  - **Core**: `SYSTEM_PROMPT` — defines AI role and capabilities
  - **Project structure**: `PROJECT_STRUCTURE_MACRO_TEMPLATE` — codebase overview at startup
  - **Task planning**: `PLANNING_PROMPT_TEMPLATE` — transforms requests into tasks
  - **Task execution**: `TASK_EXECUTION_PROMPT_TEMPLATE`, `TASK_EXECUTION_ALL_PROMPT_TEMPLATE`
  - **Conversation management**: `COMPACT_COMMAND_PROMPT_TEMPLATE`
  - **Memory checkpoints**: `MEMORY_CHECKPOINT_PROMPT_TEMPLATE`, `MEMORY_RESTORE_PROMPT_TEMPLATE`, `MEMORY_QUICK_RESTORE_MESSAGE_TEMPLATE`, `MEMORY_NO_MEMORY_MESSAGE`

- **`src/ayder_cli/commands/`** — Command registry for `--cli` REPL mode. Class-based registry pattern (`@register_command` on `BaseCommand` subclasses). `handle_command()` dispatches to handlers with `SessionContext`. Commands: `/help`, `/tools`, `/tasks`, `/task-edit`, `/implement`, `/implement-all`, `/verbose`, `/compact`, `/plan`, `/model`, `/ask`, `/undo`.

- **`src/ayder_cli/parser.py`** — Enhanced XML tool call parser. Handles standard format (`<function=name><parameter=key>value</parameter></function>`), lazy format for single-param tools, and returns `{"error": "message"}` for malformed input.

- **`src/ayder_cli/core/config.py`** — Configuration loading from `~/.ayder/config.toml` with Pydantic validation. `Config` model validates `base_url`, `num_ctx`, `max_background_processes` (1-20, default 5), etc.

- **`src/ayder_cli/core/context.py`** — `ProjectContext` class for path validation and sandboxing. Prevents path traversal attacks. Also defines `SessionContext` dataclass used by `--cli` commands.

- **`src/ayder_cli/core/result.py`** — Shared result types: `ToolSuccess(str)` and `ToolError(str)` — str subclasses. `ToolError` has `.category` property. Re-exported from `tools/__init__.py`.

- **`src/ayder_cli/tui/helpers.py`** — TUI helper functions including banner creation with ASCII art and gradients. `create_tui_banner()` for TUI.
- **`src/ayder_cli/ui.py`** — Rich terminal UI components. `print_welcome_banner()` for CLI.

- **`src/ayder_cli/console.py`** — Centralized Rich console with custom theme and file extension mapping.

- **`src/ayder_cli/tools/`** — **Core tools package** with modular architecture:
  - **`definition.py`** — `ToolDefinition` frozen dataclass. `TOOL_DEFINITIONS` list (20 tools) and `TOOL_DEFINITIONS_BY_NAME` dict.
  - **`impl.py`** — Core tool implementations (10 tools: file ops, line editing, file info, shell, search, project structure)
  - **`schemas.py`** — OpenAI-format JSON schemas
  - **`registry.py`** — `ToolRegistry` with middleware, callbacks, execution timing, DI injection. `create_default_registry(project_ctx, process_manager=None)` factory.
  - **`utils.py`** — Tool utilities (`prepare_new_content()`)
  - **`__init__.py`** — Public API exports

- **`src/ayder_cli/notes.py`** — Note management in `.ayder/notes/`. Imports from `core/result.py` (NOT `tools/`) to avoid circular imports.

- **`src/ayder_cli/memory.py`** — Cross-session memory storage in `.ayder/memory/memories.jsonl`. Imports from `core/result.py`.

- **`src/ayder_cli/process_manager.py`** — `ProcessManager` class for background processes. Ring-buffer output capture (500 lines), SIGTERM/SIGKILL lifecycle, atexit cleanup. 4 tool functions. Imports from `core/result.py`.

- **`src/ayder_cli/tasks.py`** — Task management in `.ayder/tasks/`. Slug-based filenames. 2 tool functions: `list_tasks`, `show_task`. Imports from `core/result.py`.

- **`src/ayder_cli/ui.py`** — Rich terminal UI utilities (boxes, message formatting, diff previews). Used by `--cli` REPL mode.

### TUI Architecture (tui/)

The TUI is the default interface. Key flow:

1. **Startup**: `AyderApp.__init__()` loads config, creates `OpenAIProvider`, creates `ToolRegistry` with `ProcessManager` injected, builds system prompt with project structure macro.
2. **Input**: `CLIInputBar` uses `_SubmitTextArea` (TextArea subclass where Enter submits instead of inserting newlines). Tab completes slash commands. Up/Down navigates history.
3. **Commands**: `_handle_command()` dispatches to `COMMAND_MAP` handlers in `tui/commands.py`.
4. **LLM pipeline**: `_process_llm_response()` → `call_llm_async()` → `_handle_llm_response()`. Supports `<think>` block extraction, tool call splitting (auto-approved vs needs-confirmation), parallel execution of auto-approved tools, sequential confirmation for others, and XML tool call fallback.
5. **Tool confirmation**: `_request_confirmation()` pushes `CLIConfirmScreen` with diff preview. User can approve, deny, or provide alternative instructions.
6. **Input disable**: Input bar is disabled during LLM processing and re-enabled in `_finish_processing()`.

### CLI REPL Architecture (--cli)

The `--cli` flag activates the prompt-toolkit REPL:

1. **Startup**: `_build_services()` creates all dependencies. `InteractiveRunner` creates `ChatSession` and `Agent`.
2. **Input**: `ChatSession.get_input()` via prompt-toolkit (emacs keybindings, cyan `❯` prompt).
3. **Commands**: `handle_command()` dispatches to `commands/` registry (`BaseCommand` subclasses).
4. **Agent loop**: `Agent.chat()` → `ChatLoop.run()` → `ToolCallHandler` parses/executes tool calls, `IterationController` manages checkpoint triggers.

### Tools Package Details

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

ctx = ProjectContext(".")
pm = ProcessManager(max_processes=5)
registry = create_default_registry(ctx, process_manager=pm)
result = registry.execute("read_file", {"file_path": "test.py"})
```

**Registry Features:**
- Middleware: `registry.add_middleware(func)` — Pre-execution checks (safe mode blocking)
- Pre/post callbacks for UI integration and timing
- DI injection: inspects function signatures, injects `project_ctx` and/or `process_manager`

### ProjectContext and Path Security

All file operations are sandboxed via `ProjectContext`:

```python
from ayder_cli.core.context import ProjectContext

ctx = ProjectContext(".")             # Root is current directory (resolved)
path = ctx.validate_path("src/main.py")   # Returns absolute Path within root
path = ctx.validate_path("../../etc/passwd")  # Raises ValueError (traversal blocked)
relative = ctx.to_relative(absolute_path)     # Convert back to relative string
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

3. **Update `prompts.py`** — **CRITICAL**: Add the new tool to the CAPABILITIES section in `SYSTEM_PROMPT` so the LLM knows it exists.

4. **Add tests** in `tests/` directory:
   - Test the tool function implementation
   - Test error cases
   - Update `tests/tools/test_schemas.py` to include the new tool in `expected_tools` set
   - Update tool count in `tests/tools/test_registry.py`

5. **Update documentation**:
   - Add to tool table in `README.md`
   - Update tool count in `CLAUDE.md`
   - Update permission tables if adding a new permission category

The tool will be automatically registered via the `func_ref` auto-discovery mechanism in `create_default_registry()`.

## Key Design Details

- **TUI as Default**: Running `ayder` launches the Textual TUI. The `--cli` flag falls back to the prompt-toolkit REPL. Command mode (`ayder "prompt"`) and piped input work without either interface.

- **Dependency Injection**: Both interfaces use DI. TUI: `AyderApp.__init__()` creates its own registry with `ProcessManager`. CLI: `_build_services()` is the composition root. Testing uses mocks throughout.

- **Dual Command Systems**: TUI has its own `COMMAND_MAP` in `tui/commands.py` (13 commands including TUI-only `/permission` and `/archive-completed-tasks`). CLI REPL uses `commands/` registry (class-based `@register_command` pattern). Both share the same prompts from `prompts.py`.

- **Modular Tools**: The `tools/` package provides clean separation with `impl.py` (10 core implementations), `schemas.py`, `registry.py` (execution + middleware + callbacks + DI), `definition.py`, and `utils.py`. Additional modules provide specialized functionality: `notes.py`, `memory.py`, `process_manager.py`, `tasks.py`. 20 tools total.

- **Dual Tool Calling**: Supports standard OpenAI function calling (`msg.tool_calls`) and custom XML-like fallback parsed by `parse_custom_tool_calls()`. Both TUI and CLI support this — TUI checks for XML after standard calls fail.

- **Planning Mode**: `/plan` command injects `PLANNING_PROMPT_TEMPLATE` to guide the LLM for task creation.

- **Path Security via ProjectContext**: All file tool operations sandboxed to project root. Injected via DI at startup.

- **Configuration with Pydantic**: `Config` model validates `base_url`, `num_ctx`, `max_background_processes`, etc.

- **Async LLM Support**: `call_llm_async()` wraps synchronous OpenAI calls in `ThreadPoolExecutor` for non-blocking TUI interaction.

- **Shell command timeout**: `run_shell_command` has a 60-second timeout. For long-running commands, use `run_background_process`.

- **Background Process Management**: `ProcessManager` manages long-running processes with ring-buffer output capture. Injected into `ToolRegistry` via `create_default_registry(project_ctx, process_manager=pm)`.

- **Memory Checkpoint Cycle**: When iteration limit reached → LLM summarizes → saved to `.ayder/memory/current_memory.md` → conversation reset → memory loaded → iteration counter resets.

- **Circular Import Prevention**: `tools/__init__.py` imports from `tools/impl.py` which imports from `tasks.py`. Therefore `tasks.py`, `notes.py`, `memory.py`, and `process_manager.py` import from `core/result.py` (NOT from `tools/`).
