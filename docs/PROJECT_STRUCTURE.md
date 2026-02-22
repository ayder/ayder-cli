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
7. [Convergence History](#convergence-history)

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
│  │                  TUI Mode (Default)                       │  │
│  │  tui/app.py (AyderApp) → tui/chat_loop.py (TuiChatLoop)  │  │
│  │  AppCallbacks implements TuiCallbacks protocol            │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   CLI Mode                                │  │
│  │  cli_runner.py → client.py (Agent) → chat_loop.py        │  │
│  │  (ChatLoop — sync, extends AgentLoopBase)                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │            Shared Application Modules                     │  │
│  │  application/execution_policy.py   (ExecutionPolicy)      │  │
│  │  application/validation.py         (ValidationAuthority)  │  │
│  │  application/checkpoint_orchestrator.py (orchestration)   │  │
│  │  application/runtime_factory.py    (create_runtime())     │  │
│  │  loops/base.py                     (AgentLoopBase)        │  │
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
│  │tools/builtins│  │tools/registry│  │tools/schemas.│          │
│  │ filesys.py   │  │   .py (with  │  │ py (OpenAI   │          │
│  │ search.py    │  │ middleware)  │  │   schemas)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

1. **Layered Architecture**: Clear separation between entry → app → service → core → tools
2. **Protocol-Based**: `TuiCallbacks` protocol decouples TUI from business logic; `InteractionSink`/`ConfirmationPolicy` decouple `ToolExecutor` from UI
3. **Single Composition Root**: `application/runtime_factory.create_runtime()` assembles all dependencies — no duplicated wiring between CLI and TUI
4. **Shared Loop Base**: `AgentLoopBase` (in `loops/base.py`) owns iteration counting, checkpoint trigger detection, and tool-call routing; both `ChatLoop` and `TuiChatLoop` extend it
5. **Single Execution Path**: `ExecutionPolicy.execute_with_registry()` is the sole tool execution entry point; validation → permission → execute, no inline policy in loop code
6. **Single Validation Path**: `ValidationAuthority → SchemaValidator` is the only validation stage; schema derived from live `TOOL_DEFINITIONS` registry (no hardcoded lists)
7. **Sandboxed Paths**: All file operations go through `ProjectContext` for security
8. **Async-First**: TUI uses async/await with Textual workers; CLI is synchronous via `llm.chat()`

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
| `cli_runner.py` | Command execution | `CommandRunner`, `TaskRunner`, `run_command()` |
| `chat_loop.py` | Sync CLI agent loop | `ChatLoop`, `LoopConfig`, `ToolCallHandler` |

### Shared Application Modules (`application/`)

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `application/execution_policy.py` | Shared tool permission + execution policy | `ExecutionPolicy`, `PermissionDeniedError`, `ToolRequest`, `ConfirmationRequirement` |
| `application/validation.py` | Single validation path (schema only) | `ValidationAuthority`, `SchemaValidator`, `ToolRequest` |
| `application/checkpoint_orchestrator.py` | Shared checkpoint orchestration | `CheckpointOrchestrator`, `CheckpointTrigger`, `RuntimeContext`, `EngineState` |
| `application/runtime_factory.py` | Single composition root | `create_runtime()`, `RuntimeComponents` |
| `application/message_contract.py` | LLM message format contracts | DTOs for message interchange |

### Shared Loop Modules (`loops/`)

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `loops/base.py` | Shared agent loop base class | `AgentLoopBase` — iteration, checkpoint, tool routing, escalation |
| `loops/config.py` | Shared loop configuration | `LoopConfig` dataclass |

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
| `services/interactions.py` | UI-decoupling protocols | `InteractionSink`, `ConfirmationPolicy`, `NullInteractionSink`, `AutoApproveConfirmationPolicy` |
| `services/tools/executor.py` | CLI tool execution with diff preview | `ToolExecutor` |

### Tool Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `tools/definition.py` | Tool definitions + auto-discovery | `ToolDefinition`, `TOOL_DEFINITIONS`, `_discover_definitions()` |
| `tools/registry.py` | Tool registry with middleware | `ToolRegistry`, `create_default_registry()` |
| `tools/schemas.py` | Generated OpenAI schemas | `tools_schema`, `TOOL_PERMISSIONS` |
| `tools/utils.py` | Tool utilities | `prepare_new_content()` |
| `tools/builtins/filesystem.py` | File system tool impls | `read_file()`, `write_file()`, `replace_string()` |
| `tools/builtins/python_editor.py` | CST-based Python structural editor | `python_editor()`, `PythonEditorBackend` |
| `tools/builtins/search.py` | Search tool impls | `search_codebase()`, `get_project_structure()` |
| `tools/builtins/shell.py` | Shell execution impl | `run_shell_command()` |
| `tools/builtins/*_definitions.py` | Per-domain tool definitions (12 files) | `TOOL_DEFINITIONS` tuples auto-discovered at import |

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

The `TuiCallbacks` protocol in `tui/chat_loop.py` decouples `TuiChatLoop` from all UI concerns:

```python
@runtime_checkable
class TuiCallbacks(Protocol):
    def on_thinking_start(self) -> None: ...
    def on_thinking_stop(self) -> None: ...
    def on_assistant_content(self, text: str) -> None: ...
    def on_thinking_content(self, text: str) -> None: ...
    def on_token_usage(self, total_tokens: int) -> None: ...
    def on_iteration_update(self, current: int, maximum: int) -> None: ...
    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None: ...
    def on_tool_complete(self, call_id: str, result: str) -> None: ...
    def on_tools_cleanup(self) -> None: ...
    def on_system_message(self, text: str) -> None: ...
    async def request_confirmation(self, name: str, arguments: dict) -> object | None: ...
    def is_cancelled(self) -> bool: ...
```

**`AppCallbacks`** (in `tui/app.py`) implements this protocol to update Textual widgets.

Because the protocol is `@runtime_checkable`, `isinstance(cb, TuiCallbacks)` can be used to verify any adapter at construction time.

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
from ayder_cli.tools.builtins.filesystem import read_file, write_file

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

1. **New Tools**: Create `tools/builtins/<domain>_definitions.py` with a `TOOL_DEFINITIONS` tuple + implement in `tools/builtins/<domain>.py`. Auto-discovery handles the rest — no edits to `definition.py` needed.
2. **New Application-Layer Shared Logic**: Add to `application/` and import from both `chat_loop.py` and `tui/chat_loop.py`.
3. **New TUI Commands**: Add to `tui/commands.py`, add to `COMMAND_MAP`.
4. **New Widgets**: Add to `tui/widgets.py`, import in `tui/app.py`.
5. **New Screens**: Add to `tui/screens.py`, push via `app.push_screen()`.
6. **New Themes**: Add to `themes/<name>.py`, import in `themes/__init__.py`.

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

`TuiChatLoop` (extends `AgentLoopBase`) implements the core async agentic process:
- Handles repeated LLM calls with tool execution until completion
- Supports multiple tool call formats: OpenAI native (`tool_calls`), XML custom, JSON fallback
- Manages iteration counting via `AgentLoopBase._increment_iteration()` with checkpoint system
- Communicates with UI exclusively through `TuiCallbacks` protocol (no Textual imports)
- Extracts and emits `<think>` blocks separately from display content

Key features:
- Auto-approved tools run in parallel (`asyncio.gather`); confirmation-required tools run sequentially
- Confirmation gate applies to **both** OpenAI-format and XML/JSON custom tool calls
- `ExecutionPolicy.execute_with_registry()` is the single execution entry (validate → permission → execute)
- Memory checkpoint creation/restore to prevent context-window overflow
- Token usage tracking and iteration limiting
- Graceful cancellation via `is_cancelled()`

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

Schema-driven tool definitions with auto-discovery:
- **Auto-discovery**: `_discover_definitions()` scans all `*_definitions.py` files in `tools/builtins/` at import time — no manual registration
- **Duplicate detection**: Tracks `(definition, source_module)` pairs; raises `ValueError` with accurate module names if a tool name appears twice
- **Required-tool validation**: Raises `ImportError` if core tools (`list_files`, `read_file`, `write_file`, `run_shell_command`) are absent
- **Permissions**: `"r"` (read), `"w"` (write), `"x"` (execute), `"http"` (network)
- **Safety flags**: `safe_mode_blocked`, `is_terminal` per definition
- **Path parameters**: Names listed in `path_parameters` are automatically resolved via `ProjectContext`
- **Aliases**: `parameter_aliases` tuples for common name normalisation
- **Schema generation**: `to_openai_schema()` returns the OpenAI function-calling dict

28 tools across 12 definition files:
- Filesystem (7), Python editor (1), Search (2), Shell (1), Memory (2), Notes (1)
- Background Processes (4), Tasks (2), Environment (1), Virtual Environments (5), Web (1), Temporal (1)

---

**For coding standards, testing, and workflows, see [AGENTS.md](../AGENTS.md).**

---

## Convergence History

### Phase 05 — Single Execution / Validation / Checkpoint Paths

- **`ExecutionPolicy.execute_with_registry()`** became the sole tool-execution entry point. Both CLI and TUI call it; no parallel paths remain.
- **`CheckpointOrchestrator.orchestrate_checkpoint()`** became the only checkpoint transition method; previous per-interface variants removed.
- **`ValidationAuthority → SchemaValidator`** became the only validation stage (schema-derived from live `TOOL_DEFINITIONS`, no hardcoded lists).
- **`create_runtime()`** became the single composition root for all runtime dependencies.

### Phase 06 — Scaffolding Removal

| Removed | Reason |
|---------|--------|
| `tui_theme_manager.py` | Empty shim, real code in `tui/theme_manager.py` |
| `tui_helpers.py` | Backward-compat shim, real code in `tui/helpers.py` |
| `PermissionValidator` class | Always returned `True`, no real logic |
| `ValidationStage.PERMISSION` | No real permission validation stage |
| `CheckpointOrchestrator.get_transition_source()` | Introspection scaffolding |
| `CheckpointOrchestrator.supports_context()` | Always returned `True`, scaffolding |
| `chat_loop._extract_think_blocks` wrapper | Delegated to `tui.parser` content_processor |
| `chat_loop._strip_tool_markup` wrapper | Delegated to `tui.parser` content_processor |

### Phase — Shared Agent Loop Base (`loops/base.py`)

`AgentLoopBase` extracted to `loops/base.py`. Both `ChatLoop` and `TuiChatLoop` extend it:

- `_increment_iteration()` / `_reset_iterations()` — shared iteration counting
- `_should_trigger_checkpoint()` — delegates to `CheckpointTrigger`
- `_route_tool_calls()` — shared OpenAI / XML / JSON / none routing logic
- `_is_escalation()` — shared escalation detection

### Phase — Validation Unification (Phase 4)

- `validate_tool_call()` removed from `execution.py` — double-validation eliminated. Single path: `ExecutionPolicy → ValidationAuthority → SchemaValidator → registry.execute()`.
- `validate_args()` removed from `ToolRegistry` — all validation goes through `ValidationAuthority`.
- `SchemaValidator` gained type checking (integer/string) derived from tool definition schemas.

### Architecture Bug Fixes

| Bug | Fix |
|-----|-----|
| Double `on_thinking_stop()` on LLM exception | Removed from `except` blocks in `run()` and `_handle_checkpoint()`; kept only in `finally` |
| Stale loop variable in `_discover_definitions()` | Collect `(definition, source_module)` tuples; unpack in duplicate-check loop |
| XML tool calls bypass confirmation gate | `_execute_custom_tool_calls()` now calls `_tool_needs_confirmation()` before `execute_with_registry()` |
| Silent post-execute callback failure | Added `logger.warning()` in `registry.py` post-execute exception handler |
| Dead `FileDiffConfirmation` + `confirm_file_diff()` | Removed from `execution_policy.py`; real confirmation goes through `TuiCallbacks.request_confirmation()` |

### Pending: CLI → TUI Loop Unification

See `chat_loop_integration_refactor_plan.md` in the project root.

Goal: replace sync `ChatLoop` with `TuiChatLoop` driven by a `CliCallbacks` adapter so
there is one execution engine instead of two. Phases A–E are defined and awaiting review.
