## Project Overview

ayder-cli is an interactive AI agent chat client for local LLMs. It connects to an Ollama instance running `qwen3-coder:latest` and provides an autonomous coding assistant with file system tools and shell access. Built with Python 3.12+, using the OpenAI SDK (for Ollama compatibility) and prompt-toolkit for terminal UI.

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
PYTHONPATH=src python3 -c "from ayder_cli import fs_tools"

# Run the CLI
.venv/bin/python3 -m ayder_cli
# or if installed: ayder
```

## Testing

The project uses **pytest** for testing. All tests are located in the `tests/` directory.

```bash
# Run all tests (most reliable method)
.venv/bin/python3 -m pytest tests/ -v

# Run specific test file
.venv/bin/python3 -m pytest tests/test_fs_tools.py -v

# Run tests with coverage
.venv/bin/python3 -m pytest --cov=ayder_cli --cov-report=term-missing tests/

# Quick verification that imports work
PYTHONPATH=src python3 -c "from ayder_cli import fs_tools; print(len(fs_tools.tools_schema))"
```

**Test Structure:**
- `test_fs_tools.py` - File system tool implementations
- `test_client.py` - Main chat loop and UI
- `test_commands.py` - Slash commands (/help, /tools, etc.)
- `test_tasks.py` - Task management functionality
- `test_parameter_aliasing.py` - Tool parameter normalization
- `test_config.py` - Configuration loading
- `test_ui.py` - Terminal UI components
- `test_diff_preview.py` - Diff generation and preview
- `test_search_codebase.py` - Code search functionality

All tests use pytest fixtures and mocking (no live LLM calls required).

## Architecture

The application is organized into several modules:

- **`src/ayder_cli/client.py`** — Main chat loop and terminal UI. Imports `SYSTEM_PROMPT` from `prompts.py`. The `run_chat()` function now supports dependency injection via optional `openai_client` and `config` parameters for improved testability. Handles user input via prompt-toolkit (emacs keybindings, persistent history at `~/.ayder_chat_history`), slash commands (`/help`, `/tools`, `/clear`, `/undo`), and the agentic loop that allows up to 5 consecutive tool calls per user message. Defines `TERMINAL_TOOLS` set for tools that end the agentic loop.

- **`src/ayder_cli/prompts.py`** — System prompts and prompt templates. Contains the `SYSTEM_PROMPT` constant that defines the AI agent's behavior and operational principles (extracted from `client.py` for better separation of concerns).

- **`src/ayder_cli/commands.py`** — Command registry system for slash commands. Uses a decorator-based registry pattern (`@register_command("/name")`) for extensibility. Contains `COMMANDS` dict that maps command names to handler functions. The `handle_command()` function dispatches to registered handlers with a session dict containing `messages`, `system_prompt`, and `state` (will be migrated to ChatSession object in TASK-013). All 8 commands are registered: `/help`, `/tools`, `/tasks`, `/task-edit`, `/edit`, `/verbose`, `/clear`, `/undo`.

- **`src/ayder_cli/config.py`** — Configuration loading from `~/.ayder/config.toml` with Pydantic validation. The `load_config()` function returns a `Config` model with validated settings for LLM, editor preferences, and UI options. Automatically creates default config on first run.

- **`src/ayder_cli/fs_tools.py`** — **Thin compatibility layer** that re-exports all functionality from the `tools/` package. Exists solely for backwards compatibility. New code should import from `ayder_cli.tools` directly. Re-exports: tool implementations, schemas, registry functions, and task management functions.

- **`src/ayder_cli/tools/`** — **Core tools package** with modular architecture:
  - **`impl.py`** — Actual tool implementations (`list_files`, `read_file`, `write_file`, `replace_string`, `run_shell_command`, `search_codebase`, `get_project_structure`)
  - **`schemas.py`** — OpenAI-format JSON schemas for all available tools (10 tools total)
  - **`registry.py`** — Tool registry and execution system:
    - `ToolRegistry` class for registering and executing tools
    - `execute_tool_call()` convenience function using singleton registry
    - `create_default_registry()` factory function for fully configured registry
    - `normalize_tool_arguments()` for parameter aliasing and path resolution
    - `validate_tool_call()` for schema validation
    - `PARAMETER_ALIASES` and `PATH_PARAMETERS` constants
    - `_MockableToolRegistry` internal class for test compatibility (dynamic function lookup)
  - **`utils.py`** — Utility functions for tool operations, including `prepare_new_content()` for preparing file content before write/replace operations (supports both JSON string and dict arguments)
  - **`__init__.py`** — Complete public API exports (all tools, schemas, registry, and utilities)

- **`src/ayder_cli/tasks.py`** — Task management system for creating, listing, showing, and implementing tasks stored in `.ayder/tasks/`

- **`src/ayder_cli/ui.py`** — Terminal UI utilities for formatted output, boxes, and user prompts

Entry point: `ayder_cli.client:run_chat` (registered as the `ayder` CLI script in pyproject.toml).

### Tools Package Details

The `tools/` package follows a modular architecture with clear separation of concerns:

**Import Paths:**
- **Preferred (new code)**: `from ayder_cli.tools import execute_tool_call, ToolRegistry, normalize_tool_arguments`
- **Backwards compatible**: `from ayder_cli.fs_tools import execute_tool_call, normalize_tool_arguments`
- Both import paths work identically (fs_tools re-exports from tools package)

**Module Organization:**

1. **`tools/impl.py`** — Tool implementations
   - File operations: `list_files`, `read_file`, `write_file`, `replace_string`
   - Shell execution: `run_shell_command`
   - Code navigation: `search_codebase`, `get_project_structure`

2. **`tools/schemas.py`** — Tool schemas
   - OpenAI-format JSON schemas for all 10 tools
   - Includes task management tools (create_task, show_task, implement_task, implement_all_tasks)

3. **`tools/registry.py`** — Tool registry and execution
   - `ToolRegistry` class: Registry pattern for tool management
   - `execute_tool_call(tool_name, arguments)`: Convenience function with singleton registry
   - `create_default_registry()`: Factory for fully configured registry
   - `normalize_tool_arguments()`: Parameter aliasing and path resolution
   - `validate_tool_call()`: Schema validation
   - `PARAMETER_ALIASES`: Maps parameter variations to canonical names
   - `PATH_PARAMETERS`: Defines which parameters need absolute path resolution
   - `_MockableToolRegistry`: Internal class for test compatibility (dynamic lookup)

4. **`tools/utils.py`** — Tool utilities
   - `prepare_new_content(fname, args)`: Prepares content for file operations
   - Handles both JSON string and dict arguments
   - Used by diff preview system

**Tool Execution Flow:**
```python
# Option 1: Use execute_tool_call (recommended for most cases)
from ayder_cli.tools import execute_tool_call
result = execute_tool_call("read_file", {"file_path": "test.py"})

# Option 2: Use ToolRegistry directly (for custom registries)
from ayder_cli.tools import ToolRegistry, create_default_registry
registry = create_default_registry()
result = registry.execute("read_file", {"file_path": "test.py"})

# Option 3: Backwards compatible (via fs_tools)
from ayder_cli import fs_tools
result = fs_tools.execute_tool_call("read_file", {"file_path": "test.py"})
```

**Parameter Normalization:**
```python
from ayder_cli.tools import normalize_tool_arguments

# Input: Various parameter names
args = {"path": "file.txt"}  # alias
normalized = normalize_tool_arguments("read_file", args)
# Output: {"file_path": "/absolute/path/to/file.txt"}  # canonical + resolved
```

**Dependency Injection (TASK-010):**
The `run_chat()` function now supports optional parameters for testing:
```python
def run_chat(openai_client=None, config=None):
    """
    Args:
        openai_client: Optional OpenAI client (for testing with mocks)
        config: Optional config dict or Config model (for testing)
    """
    # If None, loads defaults (config from file, client from config)
```

### Command Registry Pattern

The `commands.py` module uses a registry pattern for slash command handling:

**Command Registration:**
- `COMMANDS` — Dictionary mapping command names (e.g., `/help`) to handler functions
- `register_command(name)` — Decorator for registering command handlers
- Each command handler has signature: `def cmd_name(args: str, session: dict) -> bool`

**Session Object:**
- Currently a dict containing `messages`, `system_prompt`, and `state`
- Will be migrated to a unified `ChatSession` object in TASK-013
- Provides commands with access to conversation history and runtime state

**Adding New Commands:**
```python
@register_command("/newcmd")
def cmd_newcmd(args, session):
    """Command description.

    Args:
        args: Command arguments as string
        session: Session dict (or ChatSession in TASK-013)
    """
    # Implementation
    return True
```

**Backwards Compatibility:**
- `handle_command()` maintains original signature: `(cmd, messages, system_prompt, state=None)`
- Internal session dict created for command handlers
- Ensures existing code continues to work during refactoring

## Recent Refactoring (2026-02-01)

**TASK-007: Pydantic Config Model**
- Replaced dict-based config with `Pydantic` models for type safety and validation
- Added field validators for `num_ctx` (positive integer) and `base_url` (valid URL)
- Maintains backwards compatibility with dict-style access where needed

**TASK-010: Dependency Injection for Client**
- Modified `run_chat(openai_client=None, config=None)` to accept optional parameters
- Supports both dict and `Config` model for the config parameter
- Enables mock injection for testing without requiring actual OpenAI/Ollama instance
- Prepares foundation for TASK-013 (ChatSession/Agent class extraction)

**TASK-011: Tools Package Integration and Cleanup**
- Consolidated `fs_tools.py` into a thin compatibility layer (54 lines, all re-exports)
- Moved all tool logic into modular `tools/` package structure
- Added `execute_tool_call()` convenience function to `tools/registry.py`
- Created `_MockableToolRegistry` for test compatibility (dynamic function lookup)
- All 243 tests pass without modification (full backwards compatibility maintained)
- Both import styles work: `from ayder_cli.fs_tools` and `from ayder_cli.tools`

**Testing Impact:**
- All existing tests continue to pass without modification
- Test mocking works through dynamic function lookup in `_MockableToolRegistry`
- 243 tests passing, 1 skipped (timeout test), 0 failures

## Key Design Details

- **Dependency Injection (TASK-010)**: The `run_chat()` function accepts optional `openai_client` and `config` parameters, enabling easier testing with mocks and preparing for class extraction (TASK-013).

- **Modular Tools Package (TASK-011)**: The `tools/` package provides a clean separation with `impl.py` (implementations), `schemas.py` (definitions), `registry.py` (execution), and `utils.py` (helpers). The `fs_tools.py` module serves as a thin compatibility layer.

- **Tool Registry Pattern**: Uses `ToolRegistry` class with `execute_tool_call()` convenience function. The singleton registry uses `_MockableToolRegistry` internally for test compatibility (dynamic function lookup for task tools).

- **Configuration with Pydantic (TASK-007)**: Config validation using Pydantic models with field validators. The `Config` model validates `base_url`, `num_ctx`, and other settings. Supports both dict and Config model formats.

- **Dual tool calling**: Supports both standard OpenAI function calling (`msg.tool_calls`) and a custom XML-like fallback parsed by `parse_custom_tool_calls()` using `<function=name><parameter=key>value</parameter></function>` syntax. Standard calls feed results back as `tool` role messages; custom calls feed results back as `user` role messages.

- **Shell command timeout**: `run_shell_command` has a 60-second timeout.