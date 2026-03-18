# Agent Guidelines for ayder-cli

This document provides coding standards, tool configurations, and workflows for AI agents working on the ayder-cli project.

## Project Overview

- **Language**: Python 3.12+
- **Package Manager**: `uv` (installed at `/opt/homebrew/bin/uv`)
- **Task Runner**: `poe` (Poe the Poet)
- **Virtual Environment**: `.venv` (already configured)
- **Project Structure**: Standard Python package in `src/ayder_cli/`

## Tech Stack

### Core Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| **openai** | OpenAI-compatible API client for LLM calls | latest |
| **textual** | Terminal User Interface (TUI) framework | >=0.50.0 |
| **rich** | Rich text and beautiful formatting | >=13.0.0 |
| **prompt-toolkit** | Interactive CLI prompts and auto-completion | latest |
| **python-dotenv** | Environment variable management | >=1.0.0 |
| **httpx** | Async HTTP client (Ollama API, fetch_web) | latest |

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
│   ├── cli_runner.py           # CLI command execution logic
│   ├── cli_callbacks.py        # CLI callback implementations
│   ├── client.py               # ChatSession helpers
│   ├── console.py              # Rich console instance
│   ├── version.py              # Version info
│   ├── logging_config.py       # Loguru setup
│   │
│   ├── core/                   # Core infrastructure
│   │   ├── config.py           # Pydantic config with validation
│   │   ├── context.py          # ProjectContext (path sandboxing)
│   │   └── result.py           # ToolSuccess/ToolError types
│   │
│   ├── application/            # Shared application layer (CLI + TUI)
│   │   ├── execution_policy.py         # ExecutionPolicy, PermissionDeniedError
│   │   ├── message_contract.py         # LLM message format contracts
│   │   ├── runtime_factory.py          # create_runtime() composition root
│   │   ├── temporal_contract.py        # Temporal workflow contracts
│   │   ├── temporal_metadata.py        # Temporal metadata types
│   │   └── validation.py              # ValidationAuthority, SchemaValidator
│   │
│   ├── loops/                  # Shared agent loop base
│   │   ├── base.py             # AgentLoopBase (iteration, checkpoint, routing)
│   │   └── config.py           # Shared LoopConfig dataclass
│   │
│   ├── providers/              # LLM provider implementations
│   │   ├── base.py             # AIProvider protocol, NormalizedStreamChunk
│   │   ├── provider_orchestrator.py  # Factory: create(config) → provider
│   │   └── impl/               # Individual provider drivers
│   │       ├── openai.py       # OpenAIProvider (base for most drivers)
│   │       ├── ollama.py       # OllamaProvider (native + XML fallback)
│   │       ├── claude.py       # ClaudeProvider (Anthropic SDK)
│   │       ├── gemini.py       # GeminiProvider (Google GenAI SDK)
│   │       ├── deepseek.py     # DeepSeekProvider (OpenAI-compatible)
│   │       ├── qwen.py         # QwenNativeProvider (DashScope SDK)
│   │       └── glm.py          # GLMNativeProvider (ZhipuAI SDK)
│   │
│   ├── services/               # Service layer
│   │   ├── interactions.py     # InteractionSink, ConfirmationPolicy protocols
│   │   └── tools/
│   │       └── executor.py     # ToolExecutor (CLI confirmation + diff preview)
│   │
│   ├── tools/                  # Tool framework + implementations (25 tools)
│   │   ├── definition.py       # ToolDefinition dataclass + auto-discovery
│   │   ├── registry.py         # ToolRegistry (schema, execution, system prompts)
│   │   ├── schemas.py          # OpenAI-format JSON schemas
│   │   ├── execution.py        # Tool execution engine
│   │   ├── hooks.py            # Hook/middleware system
│   │   ├── normalization.py    # Argument normalization + path resolution
│   │   ├── utils.py            # Tool utilities
│   │   └── builtins/           # Built-in tool implementations
│   │       ├── *_definitions.py # Distributed tool definitions (13 files)
│   │       ├── filesystem.py   # file_explorer, read_file, file_editor
│   │       ├── python_editor.py # CST-based Python structural editor
│   │       ├── search.py       # search_codebase, get_project_structure
│   │       ├── shell.py        # run_shell_command
│   │       ├── venv.py         # Virtualenv management tools
│   │       ├── utils_tools.py  # manage_environment_vars
│   │       ├── web.py          # fetch_web
│   │       ├── dbs_tool.py     # DBS RAG API tool
│   │       └── temporal.py     # Temporal workflow tool
│   │
│   ├── tui/                    # Textual TUI (main interface)
│   │   ├── __init__.py         # run_tui() entry point
│   │   ├── app.py              # AyderApp main application
│   │   ├── chat_loop.py        # TUI async chat loop (TuiChatLoop)
│   │   ├── commands.py         # Slash command handlers (19 commands)
│   │   ├── helpers.py          # TUI helper functions
│   │   ├── adapter.py          # TUIInteractionSink (verbose debug)
│   │   ├── parser.py           # Message parsing
│   │   ├── screens.py          # Modal screens (confirm, select, permission, task edit)
│   │   ├── theme_manager.py    # Theme loading and CSS
│   │   ├── types.py            # MessageType, ConfirmResult
│   │   └── widgets.py          # ChatView, ToolPanel, CLIInputBar, StatusBar
│   │
│   ├── themes/                 # TUI themes
│   │   ├── __init__.py         # Theme registry
│   │   ├── claude.py           # Claude theme CSS
│   │   └── original.py         # Original theme CSS
│   │
│   ├── memory.py               # Cross-session memory storage
│   ├── notes.py                # Note management (.ayder/notes/)
│   ├── parser.py               # XML/JSON tool call parser
│   ├── process_manager.py      # Background process management
│   ├── prompts.py              # System prompt templates
│   ├── tasks.py                # Task management (.ayder/tasks/)
│   └── ui.py                   # Rich terminal UI helpers
│
├── tests/                      # Test suite (998+ tests)
│   ├── application/            # Application layer tests
│   ├── core/                   # Core tests
│   ├── services/               # Services tests
│   ├── tools/                  # Tool tests
│   ├── ui/                     # TUI tests
│   └── *.py                    # Top-level tests
│
├── .ayder/                     # Project-specific data (tasks, notes, memory, skills)
├── pyproject.toml              # Project configuration
├── AGENTS.md                   # This file
├── README.md                   # Project overview
└── .claude/                    # Claude Code configuration + skills
```

### Key Files Reference

| File | Purpose |
|------|---------|
| `cli.py` | Entry point, argument parsing |
| `tui/app.py` | Main TUI application (AyderApp) |
| `tui/commands.py` | Slash command handlers (19 commands) |
| `tui/chat_loop.py` | Async LLM loop for TUI (TuiChatLoop + TuiCallbacks protocol) |
| `cli_runner.py` | CLI command execution + sync agent loop |
| `application/runtime_factory.py` | `create_runtime()` — single composition root for CLI + TUI |
| `application/execution_policy.py` | Shared permission + tool execution policy |
| `application/validation.py` | ValidationAuthority + SchemaValidator (single validation path) |
| `loops/base.py` | AgentLoopBase shared by CLI and TUI loops |
| `tools/definition.py` | ToolDefinition dataclass + auto-discovery from `*_definitions.py` |
| `tools/registry.py` | ToolRegistry: schemas, execution, system prompts, tag filtering |
| `core/config.py` | Configuration with Pydantic validation |
| `core/context.py` | ProjectContext for path sandboxing |
| `providers/provider_orchestrator.py` | Factory dispatching to correct driver |

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
uv run --active poe test

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
source .venv/bin/activate
python3 -m pytest tests/ -x --timeout=30 --ignore=tests/ui/test_tui_chat_loop.py
python3 -m ruff check src/
python3 -m mypy src/
deactivate
```

## Python Coding Standards

### Code Style

- **Line Length**: 88 characters (Black-compatible)
- **Quotes**: Use double quotes for strings
- **Imports**: Sort with `isort` style (standard lib > third-party > local)
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

```bash
# Using poe (Recommended)
uv run poe lint
uv run poe lint-fix

# Using uv run (Fallback)
uv run ruff check src/
uv run ruff check src/ --fix
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

```bash
# Using poe (Recommended)
uv run poe typecheck

# Using uv run (Fallback)
uv run mypy src/
```

### Type Annotation Standards

```python
# Use modern Union syntax
def func(x: str | None) -> int: ...

# Use built-in generics
def process(items: list[str]) -> dict[str, int]: ...
```

## Testing with pytest

```bash
# Using poe (Recommended)
uv run poe test          # Excludes slow TUI tests
uv run poe test-all      # All tests including TUI
uv run poe test-fast     # Parallel execution
uv run poe test-verbose  # Verbose output
uv run poe test-cov      # With coverage report
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

## Architecture

### Runtime Factory

`application/runtime_factory.py` provides `create_runtime()` — the single composition root used by both CLI and TUI. It assembles a `RuntimeComponents` dataclass containing: `config`, `llm_provider`, `process_manager`, `project_ctx`, `tool_registry`, `memory_manager`, `system_prompt`.

### Pluggable Tool System

ayder-cli features a **pluggable tool architecture** with dynamic auto-discovery:

**Adding a New Tool:**
1. Create `src/ayder_cli/tools/builtins/mytool_definitions.py` with `TOOL_DEFINITIONS` tuple
2. Implement the tool function in `src/ayder_cli/tools/builtins/mytool.py`
3. **Auto-discovery and validation handle the rest** — no manual registration needed

**Tool Definition Pattern:**
```python
# src/ayder_cli/tools/builtins/mytool_definitions.py
from ..definition import ToolDefinition

TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="my_tool",
        description="What it does",
        func_ref="ayder_cli.tools.builtins.mytool:my_function",
        parameters={...},
        permission="r",
        tags=("core",),           # Tag for plugin filtering
        system_prompt="",         # Optional prompt injected when tool is enabled
    ),
)
```

**Current Tools (25 total):**

| Category | Tag | Tools |
|----------|-----|-------|
| **Filesystem** | `core` | `file_explorer`, `read_file`, `file_editor` |
| **Search** | `core` | `search_codebase`, `get_project_structure` |
| **Shell** | `core` | `run_shell_command` |
| **Memory** | `metadata` | `save_memory`, `load_memory` |
| **Notes** | `metadata` | `create_note` |
| **Tasks** | `metadata` | `list_tasks`, `show_task` |
| **Python Editor** | `python` | `python_editor` (CST-based structural editing) |
| **Background Processes** | `background` | `run_background_process`, `get_background_output`, `kill_background_process`, `list_background_processes` |
| **Virtual Environments** | `venv` | `create_virtualenv`, `install_requirements`, `list_virtualenvs`, `activate_virtualenv`, `remove_virtualenv` |
| **Web** | `http` | `fetch_web` |
| **DBS** | `dbs` | `dbs_tool` (RAG API for DBS issues) |
| **Environment** | `env` | `manage_environment_vars` |
| **Temporal** | `temporal` | `temporal_workflow` |

**Tag System:** Tools are filtered by tags. Default enabled tags: `["core", "metadata"]`. Use `/plugin` in TUI to toggle additional tags at runtime.

**Discovery Features:**
- Automatic detection of `*_definitions.py` files at import time
- Duplicate tool name validation
- Registry-backed input validation via `SchemaValidator`
- Tool-specific system prompts injected dynamically via `registry.get_system_prompts(tags)`

### Registry-Backed Validation

`SchemaValidator` (in `application/validation.py`) derives required-argument lists directly from `TOOL_DEFINITIONS_BY_NAME` — the same live registry the executor uses. There is **no hardcoded tool list** to keep in sync.

### Key Patterns

1. **Tool Results**: Use `ToolSuccess` and `ToolError` from `core.result`
2. **Project Context**: Always use `ProjectContext` for path operations
3. **Config**: Use `load_config()` for configuration access
4. **Console Output**: Use `console` from `ayder_cli.console` for Rich output

## Pre-Commit Checklist

```bash
# Run all checks (lint + typecheck + test)
uv run poe check-all

# Or individually:
uv run poe lint      # Must pass
uv run poe test      # Must pass
uv run poe typecheck # Review errors (pre-existing issues may exist)
```

## Quick Reference

| Task | Command |
|------|---------|
| Install dev deps | `/opt/homebrew/bin/uv pip install -e ".[dev]"` |
| Run tests | `uv run poe test` |
| Run tests (fast) | `uv run poe test-fast` |
| Run tests (coverage) | `uv run poe test-cov` |
| Lint | `uv run poe lint` |
| Lint & fix | `uv run poe lint-fix` |
| Type check | `uv run poe typecheck` |
| All checks | `uv run poe check-all` |
| Clean caches | `uv run poe clean` |

---

**Remember**: When in doubt, run `uv run poe check-all`.
