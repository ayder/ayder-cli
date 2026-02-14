# Agent Guidelines for ayder-cli

This document provides coding standards, tool configurations, and workflows for AI agents working on the ayder-cli project.

## Project Overview

- **Language**: Python 3.12+
- **Package Manager**: `uv` (installed at `/opt/homebrew/bin/uv`)
- **Task Runner**: `poe` (Poe the Poet)
- **Virtual Environment**: `.venv` (already configured)
- **Project Structure**: Standard Python package in `src/ayder_cli/`

> **📖 For detailed architecture notes, module relationships, and TUI structure, see [.ayder/PROJECT_STRUCTURE.md](.ayder/PROJECT_STRUCTURE.md)**

## Tech Stack

### Core Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| **openai** | OpenAI-compatible API client for LLM calls | latest |
| **textual** | Terminal User Interface (TUI) framework | >=0.50.0 |
| **rich** | Rich text and beautiful formatting | >=13.0.0 |
| **prompt-toolkit** | Interactive CLI prompts and auto-completion | latest |
| **python-dotenv** | Environment variable management | >=1.0.0 |

### Development Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| **pytest** | Testing framework | >=9.0.2 |
| **pytest-xdist** | Parallel test execution | >=3.5.0 |
| **pytest-timeout** | Test timeout protection | >=2.2.0 |
| **pytest-instafail** | Show failures immediately | >=0.5.0 |
| **pytest-sugar** | Beautiful progress bar | >=1.0.0 |
| **pytest-cov** | Code coverage | >=7.0.0 |
| **ruff** | Fast Python linter | latest |
| **mypy** | Static type checker | latest |
| **uv** | Fast Python package manager | >=0.10.0 |
| **poethepoet** | Task runner | >=0.24.0 |

### Build System

- **Build Backend**: `hatchling`
- **Package Format**: PEP 621 compliant pyproject.toml

## Project Structure

```
ayder-cli/
├── src/ayder_cli/              # Main source code
│   ├── cli.py                  # Entry point (argparse)
│   ├── cli_runner.py           # Command execution logic
│   ├── client.py               # ChatSession + Agent classes
│   ├── console.py              # Rich console instance
│   ├── version.py              # Version info
│   │
│   ├── core/                   # Core infrastructure
│   │   ├── config.py           # Pydantic config with validation
│   │   ├── context.py          # ProjectContext (path sandboxing)
│   │   └── result.py           # ToolSuccess/ToolError types
│   │
│   ├── services/               # Service layer
│   │   ├── llm.py              # OpenAI/Ollama LLM provider
│   │   └── tools/
│   │       └── executor.py     # Tool execution with confirmation
│   │
│   ├── tools/                  # Tool implementations (25 tools)
│   │   ├── definition.py       # ToolDefinition base + auto-discovery
│   │   ├── *_definitions.py    # Distributed tool definitions (9 files)
│   │   ├── filesystem.py       # File system tools
│   │   ├── search.py           # Search tools
│   │   ├── shell.py            # Shell tools
│   │   ├── venv.py             # Virtualenv tools
│   │   ├── utils_tools.py      # Utility tools
│   │   ├── registry.py         # Tool registry with middleware
│   │   ├── schemas.py          # OpenAI-format JSON schemas
│   │   └── utils.py            # Tool utilities
│   │
│   ├── tui/                    # Textual TUI (main interface)
│   │   ├── app.py              # AyderApp main application
│   │   ├── chat_loop.py        # TUI chat loop logic
│   │   ├── commands.py         # Slash command handlers
│   │   ├── helpers.py          # TUI helper functions
│   │   ├── parser.py           # XML tool call parser
│   │   ├── screens.py          # Modal screens (confirm, select, etc.)
│   │   ├── theme_manager.py    # Theme loading and CSS
│   │   ├── types.py            # Shared types
│   │   └── widgets.py          # ChatView, ToolPanel, etc.
│   │
│   ├── themes/                 # TUI themes
│   │   ├── __init__.py         # Theme registry
│   │   ├── claude.py           # Claude theme CSS
│   │   └── original.py         # Original theme CSS
│   │
│   ├── chat_loop.py            # Core agentic loop
│   ├── checkpoint_manager.py   # Memory checkpoint/restore
│   ├── memory.py               # Cross-session memory storage
│   ├── notes.py                # Note management (.ayder/notes/)
│   ├── parser.py               # XML tool call parser
│   ├── process_manager.py      # Background process management
│   ├── prompts.py              # System prompts templates
│   ├── tasks.py                # Task management (.ayder/tasks/)
│   ├── tui_helpers.py          # TUI helper re-exports
│   ├── tui_theme_manager.py    # Theme manager re-exports
│   └── ui.py                   # Rich terminal UI
│
├── tests/                      # Test suite
│   ├── client/                 # Client tests
│   ├── core/                   # Core tests
│   ├── services/               # Services tests
│   ├── tools/                  # Tool tests
│   ├── ui/                     # TUI tests
│   └── *.py                    # Top-level tests
│
├── docs/                       # Documentation
├── .ayder/                     # Project-specific data (tasks, notes, memory)
├── pyproject.toml              # Project configuration
├── AGENTS.md                   # This file
├── CLAUDE.md                   # Redirects to AGENTS.md and PROJECT_STRUCTURE.md
├── GEMINI.md                   # Additional notes
└── README.md                   # Project overview
```

### Key Files Reference

| File | Purpose |
|------|---------|
| `cli.py` | Entry point, argument parsing |
| `tui/app.py` | Main TUI application (AyderApp) |
| `tui/commands.py` | Slash command handlers (/help, /model, etc.) |
| `tui/chat_loop.py` | LLM interaction loop for TUI |
| `client.py` | ChatSession and Agent classes |
| `tools/filesystem.py` | File system tool implementations |
| `tools/search.py` | Search tool implementations |
| `core/config.py` | Configuration with Pydantic validation |
| `core/context.py` | ProjectContext for path sandboxing |

## Environment Setup

This project uses `uv` as the package manager with a pre-configured `.venv`:

```bash
# Install dependencies (uv uses .venv automatically)
/opt/homebrew/bin/uv pip install -e ".[dev]"
```

## Running Commands - Three Options

### Option 1: Using `poe` (RECOMMENDED - Default)

Poe the Poet is the preferred task runner. It automatically uses the `.venv`:

```bash
# Run tests (excludes slow TUI tests) - uses pytest-timeout, instafail, sugar
uv run poe test

# Run tests in parallel (fastest - uses pytest-xdist)
uv run poe test-fast

# Run tests with coverage report (uses pytest-cov)
uv run poe test-cov

# Run all tests including TUI
uv run poe test-all

# Run tests with verbose output
uv run poe test-verbose

# Lint code
uv run poe lint

# Lint and auto-fix
uv run poe lint-fix

# Type check
uv run poe typecheck

# Clean cache files
uv run poe clean

# Run all checks (lint + typecheck + test)
uv run poe check-all

# List all available tasks
uv run poe --help
```

**Pytest Plugins Used:**
- **pytest-timeout** (30s) - Prevents tests from hanging
- **pytest-instafail** - Shows failures immediately
- **pytest-sugar** - Beautiful progress bar
- **pytest-xdist** (-n auto) - Parallel execution (test-fast only)
- **pytest-cov** - Coverage reporting (test-cov only)

**Poe tasks are defined in `pyproject.toml` under `[tool.poe.tasks]`**

### Option 2: Using `uv run` (Fallback)

If poe is not available, use `uv run` directly:

```bash
# Run tests
uv run pytest tests/ -x --timeout=30 --ignore=tests/ui/test_tui_chat_loop.py

# Run with coverage
uv run pytest tests/ --cov=src/ayder_cli --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_cli.py -v

# Run specific test
uv run pytest tests/test_cli.py::TestMainFunction -v

# Lint
uv run ruff check src/

# Type check
uv run mypy src/
```

**Note**: `uv run` automatically detects and uses the `.venv` virtual environment.

### Option 3: Manual venv activation (Last Resort)

If neither poe nor uv run work, activate the venv manually:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run tests using python3 (not python)
python3 -m pytest tests/ -x --timeout=30 --ignore=tests/ui/test_tui_chat_loop.py

# Lint
python3 -m ruff check src/

# Type check
python3 -m mypy src/

# Deactivate when done
deactivate
```

## Python Coding Standards

### Code Style

- **Line Length**: 88 characters (Black-compatible)
- **Quotes**: Use double quotes for strings
- **Imports**: Sort with `isort` style (standard lib → third-party → local)
- **Type Hints**: Use Python 3.12+ syntax (`str | None` instead of `Optional[str]`)
- **Docstrings**: Use Google-style docstrings

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Modules | `snake_case` | `cli_runner.py` |
| Classes | `PascalCase` | `ChatSession` |
| Functions | `snake_case` | `run_command()` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT` |
| Private | `_leading_underscore` | `_internal_func()` |

### Import Guidelines

```python
# Correct order:
import json
import sys
from pathlib import Path

import openai
from rich.panel import Panel

from ayder_cli.core.config import Config
from ayder_cli.ui import console
```

**Never use bare `*` imports.**

## Linting with Ruff

### Using poe (Recommended)

```bash
# Check all source files
uv run poe lint

# Check with auto-fix
uv run poe lint-fix
```

### Using uv run (Fallback)

```bash
# Check all source files
uv run ruff check src/

# Check with auto-fix (safe fixes only)
uv run ruff check src/ --fix

# Check specific file
uv run ruff check src/ayder_cli/cli_runner.py

# Show all enabled rules
uv run ruff linter
```

### Using manual venv (Last Resort)

```bash
source .venv/bin/activate
python3 -m ruff check src/
python3 -m ruff check src/ --fix
deactivate
```

### Ruff Standards

- **F Rules**: Pyflakes (undefined names, unused imports)
- **E/W Rules**: pycodestyle (formatting)
- **I Rules**: isort (import sorting)
- **N Rules**: pep8-naming (naming conventions)

**Before committing, ensure:**
```bash
uv run poe lint  # Must pass with no errors
```

## Type Checking with Mypy

### Using poe (Recommended)

```bash
uv run poe typecheck
```

### Using uv run (Fallback)

```bash
# Check all source files
uv run mypy src/

# Check specific file
uv run mypy src/ayder_cli/cli_runner.py

# Check with detailed output
uv run mypy src/ --show-error-codes
```

### Using manual venv (Last Resort)

```bash
source .venv/bin/activate
python3 -m mypy src/
deactivate
```

### Type Annotation Standards

```python
# Use modern Union syntax
def func(x: str | None) -> int: ...

# Instead of old Optional syntax
def func(x: Optional[str]) -> int: ...  # Don't use

# Use built-in generics
def process(items: list[str]) -> dict[str, int]: ...

# Explicit None defaults require Optional
def greet(name: str | None = None) -> str: ...
```

**Note**: Mypy errors about `Optional` defaults are expected in some places due to historical code. New code should use proper `| None` annotations.

## Testing with pytest

### Using poe (Recommended)

```bash
# Run tests (excludes slow TUI tests)
uv run poe test

# Run all tests including TUI
uv run poe test-all

# Run tests with verbose output
uv run poe test-verbose
```

### Using uv run (Fallback)

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=src/ayder_cli --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_cli.py -v

# Run specific test
uv run pytest tests/test_cli.py::TestMainFunction -v

# Run with timeout (recommended)
uv run pytest tests/ -x --timeout=30

# Run parallel (fastest)
uv run pytest tests/ -n auto --timeout=30

# Run excluding slow TUI tests
uv run pytest tests/ --ignore=tests/ui/test_tui_chat_loop.py
```

### Using manual venv (Last Resort)

```bash
source .venv/bin/activate

# Run tests using python3 (not python)
python3 -m pytest tests/ -x --timeout=30 --ignore=tests/ui/test_tui_chat_loop.py

# Run with verbose output
python3 -m pytest tests/ -v

deactivate
```

### Test Standards

- **Framework**: pytest with pytest-timeout, pytest-cov
- **Structure**: Mirror source structure in `tests/`
- **Naming**: `test_*.py` files, `test_*` functions, `Test*` classes
- **Coverage**: Maintain existing coverage levels
- **Timeout**: Use `--timeout=30` to prevent hanging tests

### Writing Tests

```python
import pytest
from unittest.mock import patch, Mock

from ayder_cli import some_module


class TestFeature:
    """Test suite for feature."""
    
    def test_basic_functionality(self):
        """Test normal operation."""
        result = some_module.function()
        assert result == expected
    
    @patch("ayder_cli.module.subprocess.run")
    def test_with_mocking(self, mock_run):
        """Test with external dependencies mocked."""
        mock_run.return_value = Mock(returncode=0)
        result = some_module.function()
        assert mock_run.called
```

## Pre-Commit Checklist

Before submitting changes, run:

### Option 1: Using poe (RECOMMENDED)

```bash
cd /Users/sinanalyuruk/Vscode/ayder-cli

# Run all checks (lint + typecheck + test)
# Note: typecheck may show pre-existing errors, but lint and test must pass
uv run poe check-all

# Or run individually:
uv run poe lint      # Must pass
uv run poe test      # Must pass
uv run poe typecheck # Review errors (pre-existing issues exist)
```

### Option 2: Using uv run (Fallback)

```bash
cd /Users/sinanalyuruk/Vscode/ayder-cli

# 1. Linting (must pass)
uv run ruff check src/ tests/

# 2. Type checking (review errors)
uv run mypy src/

# 3. Tests (must pass)
uv run pytest tests/ -x --timeout=30 --ignore=tests/ui/test_tui_chat_loop.py

# 4. All checks in one go
uv run ruff check src/ tests/ && echo "✅ Ruff passed" || echo "❌ Ruff failed"
uv run pytest tests/ -x --timeout=30 --ignore=tests/ui/test_tui_chat_loop.py -q && echo "✅ Tests passed" || echo "❌ Tests failed"
```

### Option 3: Manual venv (Last Resort)

```bash
cd /Users/sinanalyuruk/Vscode/ayder-cli
source .venv/bin/activate

# 1. Linting (must pass)
python3 -m ruff check src/ tests/

# 2. Type checking (review errors)
python3 -m mypy src/

# 3. Tests (must pass)
python3 -m pytest tests/ -x --timeout=30 --ignore=tests/ui/test_tui_chat_loop.py

deactivate
```

## Common Issues & Fixes

### Unused Imports

```bash
# Using poe
uv run poe lint-fix

# Using uv run
uv run ruff check src/ --fix

# Using manual venv
source .venv/bin/activate && python3 -m ruff check src/ --fix && deactivate
```

### Type Errors

```python
# Error: Incompatible default for argument "x" (default has type "None")
# Fix: Add | None annotation
def func(x: str | None = None) -> None: ...
```

### Test Failures

```bash
# Using poe
uv run poe test-verbose

# Using uv run
uv run pytest tests/test_failing.py -vvs

# Using manual venv
source .venv/bin/activate && python3 -m pytest tests/test_failing.py -vvs && deactivate
```

## Project-Specific Guidelines

### Architecture

- **Core**: `src/ayder_cli/core/` - Configuration, context, result types
- **Tools**: `src/ayder_cli/tools/` - Tool implementations and registry
- **TUI**: `src/ayder_cli/tui/` - Textual-based terminal UI
- **Services**: `src/ayder_cli/services/` - LLM providers, tool executor

### Pluggable Tool System

ayder-cli features a **pluggable tool architecture** with dynamic auto-discovery:

**Adding a New Tool:**
1. Create `src/ayder_cli/tools/mytool_definitions.py` with `TOOL_DEFINITIONS` tuple
2. Implement the tool function
3. **Auto-discovery handles the rest** - no manual registration needed

**Tool Definition Pattern:**
```python
# src/ayder_cli/tools/mytool_definitions.py
from ayder_cli.tools.definition import ToolDefinition

TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="my_tool",
        description="What it does",
        func_ref="ayder_cli.tools.mytool:my_function",
        parameters={...},
        permission="r",
    ),
)
```

**Current Tools (25 total):**
- **Filesystem** (7): list_files, read_file, write_file, replace_string, insert_line, delete_line, get_file_info
- **Search** (2): search_codebase, get_project_structure
- **Shell** (1): run_shell_command
- **Memory** (2): save_memory, load_memory
- **Notes** (1): create_note
- **Background Processes** (4): run_background_process, get_background_output, kill_background_process, list_background_processes
- **Tasks** (2): list_tasks, show_task
- **Environment** (1): manage_environment_vars
- **Virtual Environments** (6): create_virtualenv, install_requirements, list_virtualenvs, activate_virtualenv, remove_virtualenv

**Discovery Features:**
- Automatic detection of `*_definitions.py` files
- Duplicate tool name validation
- Required tools validation
- Graceful error handling
- Zero maintenance overhead

### Key Patterns

1. **Tool Results**: Use `ToolSuccess` and `ToolError` from `core.result`
2. **Project Context**: Always use `ProjectContext` for path operations
3. **Config**: Use `load_config()` for configuration access
4. **Console Output**: Use `console` from `ayder_cli.console` for Rich output



## Resources

- **README.md**: Project overview and usage
- **.ayder/PROJECT_STRUCTURE.md**: Architecture, module map, TUI structure, import paths ⭐ **Start here for code navigation**
- **CLAUDE.md**: Redirects to AGENTS.md and PROJECT_STRUCTURE.md
- **docs/**: Additional documentation
- **tests/**: Test suites mirror source structure

## Quick Reference

### Priority 1: Using `poe` (Recommended)

| Task | Command | Plugins Used |
|------|---------|--------------|
| Install dev deps | `/opt/homebrew/bin/uv pip install -e ".[dev]"` | - |
| Run tests | `uv run poe test` | timeout, instafail, sugar |
| Run tests (fast) | `uv run poe test-fast` | + xdist (parallel) |
| Run tests (coverage) | `uv run poe test-cov` | + cov |
| Run all tests | `uv run poe test-all` | timeout, instafail, sugar |
| Run tests (verbose) | `uv run poe test-verbose` | timeout, instafail, sugar |
| Lint | `uv run poe lint` | - |
| Lint & fix | `uv run poe lint-fix` | - |
| Type check | `uv run poe typecheck` | - |
| Clean caches | `uv run poe clean` | - |
| All checks | `uv run poe check-all` | lint + typecheck + test |

### Priority 2: Using `uv run` (Fallback)

| Task | Command |
|------|---------|
| Run tests | `uv run pytest tests/ -x --timeout=30` |
| Run tests (fast) | `uv run pytest tests/ -n auto --timeout=30` |
| Lint | `uv run ruff check src/` |
| Lint & fix | `uv run ruff check src/ --fix` |
| Type check | `uv run mypy src/` |
| Coverage | `uv run pytest tests/ --cov=src/ayder_cli` |

### Priority 3: Manual venv (Last Resort)

| Task | Command |
|------|---------|
| Activate | `source .venv/bin/activate` |
| Run tests | `python3 -m pytest tests/ -x --timeout=30` |
| Lint | `python3 -m ruff check src/` |
| Type check | `python3 -m mypy src/` |
| Deactivate | `deactivate` |

---

**Remember**: 
- When in doubt, run `uv run poe check-all`
- For architecture questions, module relationships, or TUI structure, see [.ayder/PROJECT_STRUCTURE.md](.ayder/PROJECT_STRUCTURE.md)
- All changes should maintain or improve test coverage
