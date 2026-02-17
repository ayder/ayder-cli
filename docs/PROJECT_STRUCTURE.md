# Project Structure & Architecture

This document provides detailed architecture notes for the ayder-cli project.

**For general coding standards and workflows, see [AGENTS.md](../AGENTS.md).**

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Entry Points](#entry-points)
3. [Module Map](#module-map)
4. [TUI Architecture](#tui-architecture)
5. [Import Paths](#import-paths)
6. [Code Analysis Summaries](#code-analysis-summaries)
7. [Phase 05 Convergence](#phase-05-convergence)

---

## Architecture Overview

ayder-cli is an AI agent chat client with a modular, layered architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                         Entry Points                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   cli.py     │  │  __main__.py │  │   pyproject.toml     │  │
│  │  (argparse)  │  │  (python -m) │  │    (ayder script)    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
          └─────────────────┴─────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Application Layer                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                      TUI Mode (Default)                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │  │
│  │  │  tui/app.py  │──│ tui/chat_    │──│   client.py  │     │  │
│  │  │  (AyderApp)  │  │    loop.py   │  │(ChatSession) │     │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 CLI Mode (Deprecated)                     │  │
│  │         cli_runner.py → chat_loop.py → client.py          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                     Service Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │services/llm. │  │services/tools│  │process_manager.py  │    │
│  │py (OpenAI    │  │  /executor.py│  │(Background Process)│    │
│  │  Provider)   │  │(ToolExecutor)│  │                    │    │
│  └──────────────┘  └──────────────┘  └────────────────────┘    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                      Core Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ core/config. │  │core/context. │  │ core/result. │          │
│  │ py (Pydantic │  │ py (Project  │  │ py (ToolSucc-│          │
│  │   Config)    │  │   Context)   │  │ ess/Error)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                     Tools Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │tools/filesys.│  │tools/registry│  │tools/schemas.│          │
│  │py, search.py │  │   .py (with  │  │ py (OpenAI   │          │
│  │   shell.py   │  │ middleware)  │  │   schemas)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

1. **Layered Architecture**: Clear separation between entry → app → service → core → tools
2. **Protocol-Based**: `TuiCallbacks` protocol decouples TUI from business logic
3. **Dependency Injection**: Services built via `_build_services()` in cli_runner.py
4. **Sandboxed Paths**: All file operations go through `ProjectContext` for security
5. **Async-First**: TUI uses async/await with Textual workers

### Phase 05 Convergence (current)

- **Single execution path**: `ExecutionPolicy.execute_with_registry()` is the sole tool-execution entry point. Both CLI and TUI call it; no parallel paths remain.
- **Single transition method**: `CheckpointOrchestrator.orchestrate_checkpoint()` is the only checkpoint transition method. Previous per-interface variants were removed in Phase 05.
- **Single validation authority**: `ValidationAuthority` (in `application/validation.py`) is the only validation entry point. `PermissionValidator` stub removed in Phase 06 — validation pipeline is `[SCHEMA]` only.
- **No CLI/TUI divergence**: `ValidationAuthority.validate()` accepts an optional `RuntimeContext` but ignores it; identical rules apply from both entry points.

---

## Entry Points

### 1. Console Script (Production)
```bash
ayder [args]
```
**Defined in**: `pyproject.toml`
```toml
[project.scripts]
ayder = "ayder_cli.cli:main"
```

### 2. Module Execution
```bash
python3 -m ayder_cli [args]
```
**File**: `src/ayder_cli/__main__.py`
```python
from ayder_cli.cli import main
main()
```

### 3. Direct Python
```bash
python3 src/ayder_cli/cli.py [args]
```

### Entry Point Flow

```
cli.py:main()
    ├── --tasks → TaskRunner.list_tasks()
    ├── --implement → TaskRunner.implement_task()
    ├── --implement-all → TaskRunner.implement_all()
    ├── --file/--stdin/command → run_command() (one-shot mode)
    └── (no args) → run_tui() (default TUI mode)
```

---

## Module Map

### Core Modules (Always Loaded)

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `core/config.py` | Configuration management | `Config`, `load_config()` |
| `core/context.py` | Project sandboxing | `ProjectContext` |
| `core/result.py` | Tool result types | `ToolSuccess`, `ToolError` |
| `console.py` | Rich console singleton | `console` |

### Application Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `cli.py` | Entry point, argument parsing | `main()`, `create_parser()` |
| `client.py` | LLM client and chat session | `ChatSession`, `Agent`, `call_llm_async()` |
| `cli_runner.py` | Command execution | `run_command()`, `InteractiveRunner` |
| `chat_loop.py` | Deprecated CLI loop | `ChatLoop`, `IterationController` |

### TUI Modules (Textual-based)

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `tui/app.py` | Main TUI application | `AyderApp`, `AppCallbacks` |
| `tui/chat_loop.py` | TUI chat loop logic | `TuiChatLoop`, `TuiLoopConfig` |
| `tui/commands.py` | Slash command handlers | `COMMAND_MAP`, `handle_*()` |
| `tui/widgets.py` | Custom widgets | `ChatView`, `ToolPanel`, `CLIInputBar` |
| `tui/screens.py` | Modal screens | `CLIConfirmScreen`, `CLISelectScreen` |
| `tui/parser.py` | TUI-specific parsing | `content_processor()` |
| `tui/helpers.py` | UI helpers | `create_tui_banner()` |
| `tui/theme_manager.py` | Theme/CSS management | `get_theme_css()` |

### Service Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `services/llm.py` | LLM provider | `LLMProvider`, `OpenAIProvider` |
| `services/tools/executor.py` | Tool execution | `ToolExecutor` |

### Tool Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `tools/filesystem.py` | File system tools | `read_file()`, `write_file()` |
| `tools/search.py` | Search tools | `search_codebase()` |
| `tools/shell.py` | Shell execution | `run_shell_command()` |
| `tools/registry.py` | Tool registry | `ToolRegistry`, `create_default_registry()` |
| `tools/schemas.py` | Tool schemas | `tools_schema`, `TOOL_PERMISSIONS` |
| `tools/definition.py` | Tool definitions | `ToolDefinition`, `TOOL_DEFINITIONS` |
| `tools/utils.py` | Tool utilities | `prepare_content_for_diff()` |

### Feature Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `tasks.py` | Task management | `list_tasks()`, `show_task()` |
| `memory.py` | Cross-session memory | `MemoryManager`, `save_memory()`, `load_memory()` |
| `notes.py` | Note creation | `create_note()` |
| `checkpoint_manager.py` | Memory checkpoints | `CheckpointManager` |
| `process_manager.py` | Background processes | `ProcessManager`, `run_background_process()` |
| `prompts.py` | System prompts | `SYSTEM_PROMPT`, `PLANNING_PROMPT_TEMPLATE` |
| `parser.py` | XML parsing | `parse_custom_tool_calls()` |

### Theme Modules

| Module | Purpose |
|--------|---------|
| `themes/__init__.py` | Theme registry |
| `themes/claude.py` | Claude theme CSS |
| `themes/original.py` | Original theme CSS |

---

## TUI Architecture

### Component Hierarchy

```
AyderApp (Textual App)
├── CSS (from theme_manager.py)
├── Compose:
│   ├── Banner (Static)
│   ├── ChatView (custom widget) ← Messages displayed here
│   ├── ToolPanel (custom widget) ← Tool calls shown here
│   ├── ActivityBar (custom widget) ← Status indicators
│   ├── CLIInputBar (custom widget) ← User input
│   └── StatusBar (custom widget) ← Model, tokens, iterations
│
├── Screens (Modal):
│   ├── CLIConfirmScreen ← Tool confirmation with diff
│   ├── CLISelectScreen ← Model/task selection
│   ├── CLIPermissionScreen ← Permission toggles
│   └── TaskEditScreen ← In-app task editor
│
└── Workers:
    └── _process_message_worker() ← Runs TuiChatLoop
```

### TUI Data Flow

```
User Input → CLIInputBar
                │
                ▼
         AyderApp._handle_command() ──→ COMMAND_MAP[cmd]
                │                              │
                │ (regular message)            │ (slash command)
                ▼                              ▼
         AyderApp._process_message()    handle_*(app, args, chat_view)
                │
                ▼
         TuiChatLoop.process_message()
                │
                ├── LLM Call ──→ services/llm.py
                │
                ├── Tool Parse ──→ parser.py
                │
                └── Tool Exec ──→ services/tools/executor.py
                        │
                        ▼
                ToolRegistry.execute()
                        │
                        ▼
                tools/impl.py (actual tool)
```

### TuiCallbacks Protocol

The `TuiCallbacks` protocol in `tui/chat_loop.py` decouples business logic from UI:

```python
class TuiCallbacks(Protocol):
    def on_thinking_start(self) -> None: ...
    def on_thinking_stop(self) -> None: ...
    def on_assistant_content(self, text: str) -> None: ...
    def on_tool_start(self, call_id: str, name: str, args: dict) -> None: ...
    def on_tool_complete(self, call_id: str, result: str) -> None: ...
    async def request_confirmation(self, name: str, args: dict) -> ConfirmResult: ...
```

**AppCallbacks** (in `tui/app.py`) implements this protocol to update Textual widgets.

### Command Dispatch

Commands are defined in `tui/commands.py` and registered in `COMMAND_MAP`:

```python
COMMAND_MAP: dict[str, Callable] = {
    "/help": handle_help,
    "/model": handle_model,
    "/tasks": handle_tasks,
    "/implement": handle_implement,
    "/compact": handle_compact,
    # ... etc
}
```

Each handler receives `(app: AyderApp, args: str, chat_view: ChatView)`.

---

## Import Paths

### Standard Import Patterns

```python
# Core imports
from ayder_cli.core.config import load_config, Config
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

# Console (Rich)
from ayder_cli.console import console

# Services
from ayder_cli.services.llm import OpenAIProvider, LLMProvider
from ayder_cli.services.tools.executor import ToolExecutor

# Tools
from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.tools.schemas import tools_schema, TOOL_PERMISSIONS
from ayder_cli.tools.impl import read_file, write_file

# TUI
from ayder_cli.tui.app import AyderApp
from ayder_cli.tui.commands import COMMAND_MAP
from ayder_cli.tui.widgets import ChatView, ToolPanel
from ayder_cli.tui.screens import CLIConfirmScreen
```

### Import Order Convention

```python
# 1. Standard library
import json
import sys
from pathlib import Path

# 2. Third-party
import openai
from rich.panel import Panel
from textual.app import App

# 3. Local (ayder_cli)
from ayder_cli.core.config import Config
from ayder_cli.tools.registry import ToolRegistry
```

### Circular Import Avoidance

Use `TYPE_CHECKING` for type-only imports:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ayder_cli.memory import MemoryManager
    from ayder_cli.checkpoint_manager import CheckpointManager
```

### Protocol-Based Imports

The TUI uses protocols to avoid circular imports:

```python
# tui/chat_loop.py
from typing import Protocol

class TuiCallbacks(Protocol):
    ...

# tui/app.py
class AppCallbacks:
    """Implements TuiCallbacks"""
    ...
```

---

## Common Patterns

### Building Services

```python
# From cli_runner.py
def _build_services(config=None, project_root="."):
    cfg = config or load_config()
    llm_provider = OpenAIProvider(base_url=cfg.base_url, api_key=cfg.api_key)
    project_ctx = ProjectContext(project_root)
    tool_registry = create_default_registry(project_ctx)
    tool_executor = ToolExecutor(tool_registry)
    # ... returns tuple of services
```

### Path Security Pattern

```python
# All file operations MUST use ProjectContext
project_ctx = ProjectContext(".")
file_path = project_ctx.validate_path("src/main.py")  # Sanitizes path
```

### Tool Registration

```python
# Tools are auto-registered via create_default_registry()
registry = create_default_registry(project_ctx, process_manager)
registry.execute("read_file", {"file_path": "main.py"})
```

---

## File Organization Tips

1. **New Tools**: Add to `tools/<domain>.py`, register in `tools/definition.py`
2. **New TUI Commands**: Add to `tui/commands.py`, add to `COMMAND_MAP`
3. **New Widgets**: Add to `tui/widgets.py`, import in `tui/app.py`
4. **New Screens**: Add to `tui/screens.py`, push via `app.push_screen()`
5. **New Themes**: Add to `themes/<name>.py`, import in `themes/__init__.py`

---

## Code Analysis Summaries

### CLI Entry Point Summary (src/ayder_cli/cli.py)

The main CLI entry point handles argument parsing and delegates to different execution modes:
- **Task-related operations**: --tasks, --implement, --implement-all
- **Input methods**: --file, --stdin, or positional command argument
- **Permission system**: -r (read), -w (write), -x (execute) flags
- **Default behavior**: Launches TUI mode when no arguments provided
- **One-shot mode**: Executes single commands when provided

The CLI builds granted permissions, resolves iterations count, and routes to appropriate handlers based on arguments.

### Default TUI Implementation Summary (src/ayder_cli/tui/__init__.py)

The TUI module provides a clean, terminal-like interface with:
- Simple text output with prefixes
- Minimal borders and chrome design
- Slash command auto-completion
- Status bar with contextual information
- Mouse-free operation optimized for keyboard

It exposes key components like AyderApp, widgets (ChatView, ToolPanel), and screens (CLIConfirmScreen) for building the terminal interface.

### TUI Application File Summary (src/ayder_cli/tui/app.py)

AyderApp is the main Textual application implementing a chat-style interface:
- **Layout**: Banner, ChatView, ToolPanel, ActivityBar, CLIInputBar, StatusBar
- **Keybindings**: Ctrl+Q (quit), Ctrl+C/X (cancel), Ctrl+L (clear), Ctrl+O (toggle tools)
- **Features**: 
  - Async processing with worker threads
  - Tool confirmation with diff previews
  - Activity animations and status updates
  - Safe mode with middleware checks
  - Memory checkpoint system integration
- **Architecture**: Uses AppCallbacks to implement TuiCallbacks protocol, decoupling business logic from UI

The application manages:
- LLM provider setup and configuration
- Tool registry initialization with middleware
- System prompt construction with project structure
- Process manager for background operations
- Checkpoint and memory managers

### TUI Chat Loop Summary (src/ayder_cli/tui/chat_loop.py)

TuiChatLoop implements the core agentic process:
- Handles repeated LLM calls with tool execution until completion
- Supports multiple tool call formats: OpenAI native, XML custom, JSON fallback
- Manages iteration counting with checkpoint system for long conversations
- Communicates with UI exclusively through TuiCallbacks protocol
- Processes thinking blocks and content display separately

Key features:
- Automatic tool execution for pre-approved permissions
- Confirmation workflow for sensitive operations
- Memory checkpoint creation to prevent context overflow
- Token usage tracking and iteration limiting
- Graceful cancellation handling

### Tool Registry Summary (src/ayder_cli/tools/registry.py)

The tool registry provides a comprehensive tool execution system:
- **Registration**: Auto-discovers tools from TOOL_DEFINITIONS via func_ref
- **Middleware system**: Pre-execution checks (e.g., safe mode blocking)
- **Callbacks**: Pre/Post execution hooks for monitoring
- **Normalization**: Parameter aliasing, path resolution, type coercion
- **Validation**: Schema-based argument validation

Execution pipeline:
1. Argument normalization (aliases, paths, types)
2. Schema validation
3. Middleware checks (permissions, safe mode)
4. Dependency injection (project_ctx, process_manager)
5. Tool function execution with timing
6. Callback notifications

Supports both synchronous tool execution and integrated with asyncio for TUI.

### Tool Definitions Summary (src/ayder_cli/tools/definition.py)

Comprehensive schema-driven tool definitions:
- **Categories**: File system, search, shell, processes, tasks, memory, environment, virtual environments
- **Permissions**: "r" (read), "w" (write), "x" (execute)
- **Safety**: Safe mode blocking for dangerous operations
- **Path parameters**: Automatic validation via ProjectContext
- **Aliases**: Common parameter name mappings
- **Schema generation**: OpenAI-compatible function schemas

Available tools cover full development lifecycle:
- File operations: read, write, search, edit
- System commands: shell execution, process management
- Project management: tasks, notes, memory
- Environment: virtual envs, environment variables
- Utilities: project structure, file info

All tool schemas are centralized for consistency and easy maintenance.

---

**For coding standards, testing, and workflows, see [AGENTS.md](../AGENTS.md).**

---

## Phase 05 Convergence

Phase 05 established single execution, transition, and validation paths shared by both CLI and TUI runtimes. Phase 06 cleaned up all temporary scaffolding.

### Single Execution Path

`application/execution_policy.py` — `ExecutionPolicy` is the sole authority for tool confirmation requirements. Both `cli/chat_loop.py` and `tui/chat_loop.py` delegate to it via `get_confirmation_requirement()`. No inline permission logic exists in either runtime.

### Single Checkpoint/Transition Path

`application/checkpoint_orchestrator.py` — `CheckpointOrchestrator` handles checkpoint triggers, state reset, restore, and summary generation for both CLI and TUI. It accepts an optional `RuntimeContext` but applies identical logic regardless of interface.

`application/checkpoint_orchestrator.py` — `CheckpointTrigger` and `create_checkpoint_trigger()` create trigger configs from `RuntimeContext`; both CLI and TUI receive identical configs.

### Single Validation Path

`application/validation.py` — `ValidationAuthority` is the sole validation entry point. It runs `SchemaValidator` (the only stage as of Phase 06 cleanup). `PermissionValidator` and `ValidationStage.PERMISSION` were removed as scaffolding in Phase 06.

### Removed Scaffolding (Phase 06)

| Removed | Reason |
|---------|--------|
| `tui_theme_manager.py` | Empty shim, real code in `tui/theme_manager.py` |
| `tui_helpers.py` | Backward-compat shim, real code in `tui/helpers.py` |
| `application/__init__.py` placeholder docstring | Stale placeholder |
| `PermissionValidator` class | Always returned `True`, no real logic |
| `ValidationStage.PERMISSION` | No real permission validation exists |
| `CheckpointOrchestrator.get_transition_source()` | Introspection scaffolding |
| `CheckpointOrchestrator.supports_context()` | Always returned `True`, scaffolding |
| `chat_loop._extract_think_blocks` wrapper | Delegated to `tui.parser.extract_think_blocks` |
| `chat_loop._strip_tool_markup` wrapper | Delegated to `tui.parser.strip_for_display` |
| `chat_loop._parse_json_tool_calls` wrapper | Delegated to `tui.parser.parse_json_tool_calls` |
| `chat_loop._regex_extract_json_tool_calls` wrapper | Delegated to `tui.parser.content_processor` |
