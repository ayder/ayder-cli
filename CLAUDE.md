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

- **`src/ayder_cli/client.py`** — Main chat loop and terminal UI. Handles user input via prompt-toolkit (emacs keybindings, persistent history at `~/.ayder_chat_history`), slash commands (`/help`, `/tools`, `/clear`, `/undo`), and the agentic loop that allows up to 5 consecutive tool calls per user message.

- **`src/ayder_cli/commands.py`** — Command registry system for slash commands. Uses a decorator-based registry pattern (`@register_command("/name")`) for extensibility. Contains `COMMANDS` dict that maps command names to handler functions. The `handle_command()` function dispatches to registered handlers with a session dict containing `messages`, `system_prompt`, and `state` (will be migrated to ChatSession object in TASK-013). All 8 commands are registered: `/help`, `/tools`, `/tasks`, `/task-edit`, `/edit`, `/verbose`, `/clear`, `/undo`.

- **`src/ayder_cli/fs_tools.py`** — Legacy dispatcher `execute_tool_call()`. Re-exports tool implementations, schemas, and parameter normalization utilities from the `tools/` package for backwards compatibility.

- **`src/ayder_cli/tools/`** — Tools package containing:
  - **`impl.py`** — Actual tool implementations (`list_files`, `read_file`, `write_file`, `replace_string`, `run_shell_command`, `search_codebase`, `get_project_structure`)
  - **`schemas.py`** — OpenAI-format JSON schemas for all available tools
  - **`registry.py`** — `ToolRegistry` class for tool execution with built-in parameter normalization (`normalize_tool_arguments()`, `validate_tool_call()`) and validation (`PARAMETER_ALIASES`, `PATH_PARAMETERS`)
  - **`__init__.py`** — Exports all tools, schemas, registry, and utilities

- **`src/ayder_cli/tasks.py`** — Task management system for creating, listing, showing, and implementing tasks stored in `.ayder/tasks/`

- **`src/ayder_cli/config.py`** — Configuration loading from `~/.config/ayder/config.toml` with support for LLM settings, editor preferences, and UI options

- **`src/ayder_cli/ui.py`** — Terminal UI utilities for formatted output, boxes, and user prompts

Entry point: `ayder_cli.client:run_chat` (registered as the `ayder` CLI script in pyproject.toml).

### Tools Package Details

The `tools/` package follows a modular architecture:

**Import Paths:**
- Primary: `from ayder_cli.tools import normalize_tool_arguments, validate_tool_call`
- Backwards compatible: `from ayder_cli.fs_tools import normalize_tool_arguments, validate_tool_call`

**Parameter Normalization:**
- `PARAMETER_ALIASES` — Maps common parameter variations to canonical names (e.g., `path` → `file_path`)
- `PATH_PARAMETERS` — Defines which parameters should be resolved to absolute paths via `Path.resolve()`
- `normalize_tool_arguments()` — Applies aliases, resolves paths, and performs type coercion (e.g., string "10" → int 10)
- `validate_tool_call()` — Validates tool calls against schemas, checking required parameters and types

**Tool Registry Pattern:**
```python
from ayder_cli.tools import ToolRegistry

registry = ToolRegistry()
registry.register("read_file", read_file)
result = registry.execute("read_file", {"file_path": "test.py"})
# Automatically normalizes parameters, validates, and executes
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

## Key Design Details

- **Dual tool calling**: Supports both standard OpenAI function calling (`msg.tool_calls`) and a custom XML-like fallback parsed by `parse_custom_tool_calls()` using `<function=name><parameter=key>value</parameter></function>` syntax. Standard calls feed results back as `tool` role messages; custom calls feed results back as `user` role messages.

- **Shell command timeout**: `run_shell_command` has a 60-second timeout.