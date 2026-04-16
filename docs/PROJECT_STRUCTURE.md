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
│  │  tui/app.py (AyderApp) → loops/chat_loop.py (ChatLoop)    │  │
│  │  AppCallbacks implements ChatCallbacks protocol           │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   CLI Mode                                │  │
│  │  cli_runner.py → loops/chat_loop.py (ChatLoop)            │  │
│  │  CliCallbacks (cli_callbacks.py) implements ChatCallbacks │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │            Shared Application Modules                     │  │
│  │  application/execution_policy.py   (ExecutionPolicy)      │  │
│  │  application/validation.py         (ValidationAuthority)  │  │
│  │  application/runtime_factory.py    (create_runtime())     │  │
│  │  loops/chat_loop.py                (ChatLoop)             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                  Service / Provider Layer                      │
│  services/interactions.py  (InteractionSink protocol)          │
│  process_manager.py        (ProcessManager — background procs) │
│  providers/base.py         (AIProvider, NormalizedStreamChunk) │
│  providers/orchestrator.py (driver → provider factory)         │
│  providers/impl/<driver>.py (ollama, openai, claude, gemini,   │
│                              deepseek, qwen, glm)              │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                      Core Layer                                │
│  core/config.py              (Pydantic Config)                 │
│  core/context.py             (ProjectContext, sandboxing)      │
│  core/result.py              (ToolSuccess, ToolError)          │
│  core/context_manager.py     (ContextManagerProtocol)          │
│  core/default_context_manager.py                               │
│  core/ollama_context_manager.py  (KV-cache-aware)              │
│  core/context_manager_factory.py (driver → manager factory)    │
│  core/cache_monitor.py       (timing-based KV-cache detection) │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│                     Tools Layer                                │
│  tools/definition.py  (ToolDefinition + auto-discovery)        │
│  tools/registry.py    (ToolRegistry + middleware + DI)         │
│  tools/execution.py / normalization.py / hooks.py              │
│  tools/schemas.py     (generated OpenAI schemas)               │
│  tools/plugin_*.py    (external plugin system)                 │
│  tools/builtins/<domain>.py + <domain>_definitions.py          │
└────────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

1. **Layered Architecture**: Clear separation between entry → app → service → core → tools
2. **Protocol-Based**: `ChatCallbacks` protocol decouples the chat loop from UI concerns; `InteractionSink` decouples LLM providers from UI for debug events
3. **Single Composition Root**: `application/runtime_factory.create_runtime()` assembles all dependencies — no duplicated wiring between CLI and TUI
4. **Single Loop**: `ChatLoop` (in `loops/chat_loop.py`) owns the full async LLM + tool execution loop; both CLI and TUI route through it
5. **Single Execution Path**: `ExecutionPolicy.execute_with_registry()` is the sole tool execution entry point; validation → permission → execute, no inline policy in loop code
6. **Single Validation Path**: `ValidationAuthority → SchemaValidator` is the only validation stage; schema derived from live `TOOL_DEFINITIONS` registry (no hardcoded lists)
7. **Sandboxed Paths**: All file operations go through `ProjectContext` for security
8. **Single Execution Engine**: Both TUI and CLI drive `ChatLoop.run()` through the `ChatCallbacks` protocol (`AppCallbacks` and `CliCallbacks` respectively); CLI runs it via `asyncio.run`

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
| `core/config.py` | Configuration management | `Config`, `load_config()`, `load_config_for_provider()` |
| `core/config_migration.py` | TOML config migration helpers | migration routines for schema changes |
| `core/context.py` | Project sandboxing | `ProjectContext` |
| `core/result.py` | Tool result types | `ToolSuccess`, `ToolError` |
| `core/context_manager.py` | ContextManager Protocol + shared utilities | `ContextManagerProtocol`, `ContextStats`, `truncate_tool_result()` |
| `core/default_context_manager.py` | Tiered context manager for non-Ollama providers | `DefaultContextManager`, `TokenCounter`, `MessageTier` |
| `core/ollama_context_manager.py` | KV-cache-aware context manager for Ollama | `OllamaContextManager`, `OllamaContextStats` |
| `core/context_manager_factory.py` | Registry-based factory (OCP) | `ContextManagerFactory`, `context_manager_factory` |
| `core/cache_monitor.py` | Timing-based KV-cache hit detection | `CacheMonitor`, `CacheStatus`, `CacheSample` |
| `console.py` | Rich console singleton | `console` |
| `logging_config.py` | Logger setup (loguru + stdlib bridge) | `setup_logging()` |
| `version.py` | Package version constant | `__version__` |

### Root-Level Application Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `cli.py` | Entry point, argument parsing | `main()`, `create_parser()` |
| `cli_runner.py` | Command execution | `CommandRunner`, `TaskRunner`, `run_command()` |
| `cli_callbacks.py` | `ChatCallbacks` adapter for one-shot CLI mode | `CliCallbacks` |
| `ui.py` | Rich-based non-TUI rendering helpers | progress, panels, confirmations |
| `__main__.py` | `python -m ayder_cli` entry | delegates to `cli.main()` |


### Agent System Modules (`agents/`)

| Module | Purpose |
|--------|---------|
| `agents/config.py` | `AgentConfig` Pydantic model for `[agents.*]` TOML sections |
| `agents/summary.py` | `AgentSummary` dataclass — structured result of agent runs |
| `agents/callbacks.py` | `AgentCallbacks` — `ChatCallbacks` for autonomous agents |
| `agents/runner.py` | `AgentRunner` — wraps one `ChatLoop` per agent dispatch |
| `agents/registry.py` | `AgentRegistry` — dispatch, cancel, status, capability prompts |
| `agents/tool.py` | `call_agent` tool definition + handler factory |

**Agent dispatch flow (Approach A — all non-blocking):**
1. Config parsed → `AgentConfig` objects in `Config.agents`
2. `AyderApp.__init__` creates `AgentRegistry` if agents configured
3. LLM calls `call_agent` tool → `registry.dispatch()` (sync, fire-and-forget)
4. User runs `/agent <name> <task>` → same `registry.dispatch()`
5. Agent runs `ChatLoop` with isolated runtime + `AgentCallbacks` in background
6. Summary parsed from `<agent-summary>` block → `AgentSummary` → `_summary_queue`
7. `pre_iteration_hook` drains queue → injects summaries as system messages

### Shared Application Modules (`application/`)

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `application/execution_policy.py` | Shared tool permission + execution policy | `ExecutionPolicy`, `PermissionDeniedError`, `ToolRequest`, `ConfirmationRequirement` |
| `application/validation.py` | Single validation path (schema only) | `ValidationAuthority`, `SchemaValidator`, `ToolRequest` |
| `application/runtime_factory.py` | Single composition root | `create_runtime()`, `create_agent_runtime()`, `RuntimeComponents` |
| `application/message_contract.py` | LLM message format contracts | DTOs for message interchange |

### Loop Module (`loops/`)

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `loops/chat_loop.py` | Async agent chat loop — LLM + tool execution driver | `ChatLoop`, `ChatCallbacks` (Protocol), `ChatLoopConfig` |

> Note: earlier refactors split out `loops/base.py` (`AgentLoopBase`) and `loops/config.py` (`LoopConfig`); both were merged back into `loops/chat_loop.py`. `ChatLoopConfig` now lives at the top of `chat_loop.py`, and iteration/tool-routing helpers are private methods on `ChatLoop`.

### TUI Modules (Textual-based)

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `tui/app.py` | Main TUI application | `AyderApp`, `AppCallbacks` |
| `tui/adapter.py` | Adapter glue between `AyderApp` and `ChatLoop` | callback wiring helpers |
| `tui/commands.py` | Slash command handlers | `COMMAND_MAP`, `handle_*()` |
| `tui/widgets.py` | Custom widgets | `ChatView`, `ToolPanel`, `CLIInputBar`, `StatusBar`, `AutoCompleteInput` |
| `tui/screens.py` | Modal screens | `CLIConfirmScreen`, `CLIHelpScreen`, `CLIPermissionScreen`, `CLISafeModeScreen`, `CLISelectScreen`, `TaskEditScreen` |
| `tui/parser.py` | TUI-specific parsing | `content_processor()` |
| `tui/helpers.py` | UI helpers | `create_tui_banner()` |
| `tui/keybindings.py` | Keybinding declarations | `BINDINGS` |
| `tui/theme_manager.py` | Theme/CSS management | `get_theme_css()` |
| `tui/types.py` | Shared TUI enums/dataclasses | `MessageType`, `ConfirmResult` |

### Service Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `services/interactions.py` | LLM debug event protocol | `InteractionSink` |

### Provider Modules (`providers/`)

All LLM provider implementations live here. Previously some sat under `services/`; the `services/llm.py` module was retired in favor of per-provider modules.

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `providers/__init__.py` | Re-exports | `AIProvider`, `NormalizedStreamChunk`, `ToolCallDef`, `provider_orchestrator` |
| `providers/base.py` | Provider protocol + shared DTOs | `AIProvider`, `NormalizedStreamChunk`, `ToolCallDef`, `_ToolCall`, `_FunctionCall` |
| `providers/orchestrator.py` | Driver-keyed provider factory | `ProviderOrchestrator`, `provider_orchestrator` |
| `providers/impl/ollama.py` | Native Ollama provider (ollama SDK) | `OllamaProvider`, `ToolStreamParser`, `XMLParserAdapter` |
| `providers/impl/ollama_inspector.py` | Ollama model introspection | `OllamaInspector`, `ModelInfo`, `RuntimeState` |
| `providers/impl/openai.py` | OpenAI / OpenAI-compatible backend | `OpenAIProvider` |
| `providers/impl/claude.py` | Anthropic Claude backend | `ClaudeProvider` |
| `providers/impl/gemini.py` | Google Gemini backend | `GeminiProvider` |
| `providers/impl/deepseek.py` | DeepSeek backend | `DeepseekProvider` |
| `providers/impl/qwen.py` | Qwen backend | `QwenProvider` |
| `providers/impl/glm.py` | GLM backend | `GLMProvider` |

### Tool Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `tools/definition.py` | Tool definitions + auto-discovery | `ToolDefinition`, `TOOL_DEFINITIONS`, `TOOL_DEFINITIONS_BY_NAME`, `_discover_definitions()` |
| `tools/registry.py` | Tool registry with middleware + DI | `ToolRegistry`, `create_default_registry()` |
| `tools/execution.py` | Low-level tool execution primitives | argument normalization + invocation |
| `tools/normalization.py` | Parameter aliasing + path resolution | normalization helpers shared by registry |
| `tools/hooks.py` | Pre/post execution callback scaffolding | hook registration + invocation |
| `tools/schemas.py` | Generated OpenAI schemas | `tools_schema`, `TOOL_PERMISSIONS` |
| `tools/utils.py` | Tool utilities | `prepare_new_content()` |
| `tools/plugin_api.py` | Public plugin entry-point contract | Plugin protocol |
| `tools/plugin_manager.py` | Plugin discovery + lifecycle | `PluginManager` |
| `tools/plugin_github.py` | GitHub-sourced plugin fetcher | remote-plugin loader |
| `tools/builtins/filesystem.py` | File system tool impls | `file_explorer()`, `read_file()`, `file_editor()` |
| `tools/builtins/search.py` | Search tool impls | `search_codebase()`, `get_project_structure()` |
| `tools/builtins/shell.py` | Shell execution impl | `run_shell_command()` |
| `tools/builtins/memory.py` | Long-term memory tools | `save_memory`, `load_memory`, `save_context_memory`, `load_context_memory` |
| `tools/builtins/notes.py` | Note-taking tool | `create_note()` |
| `tools/builtins/tasks.py` | Task-management tools | `list_tasks()`, `show_task()` |
| `tools/builtins/web.py` | HTTP fetch tool | `fetch_web()` |
| `tools/builtins/utils_tools.py` | Misc utility tools | `manage_environment_vars()` |
| `tools/builtins/*_definitions.py` | Per-domain tool definitions (9 files) | `TOOL_DEFINITIONS` tuples auto-discovered at import |

### Feature Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `process_manager.py` | Background processes | `ProcessManager`, `run_background_process()` |
| `prompts.py` | System prompts | `SYSTEM_PROMPT`, `PLANNING_PROMPT_TEMPLATE`, `get_system_prompt()`, `PROJECT_STRUCTURE_MACRO_TEMPLATE` |
| `parser.py` | XML tool-call parsing | `parse_custom_tool_calls()` |

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
    └── _process_message_worker() ← Runs ChatLoop.run()
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
         ChatLoop.run()                 (loops/chat_loop.py)
                │
                ├── LLM Call ──→ providers/impl/<driver>.py
                │
                ├── Tool Parse ──→ parser.py
                │
                └── Tool Exec ──→ ExecutionPolicy.execute_with_registry()
                        │
                        ▼
                ToolRegistry.execute()  (validate → permission → execute)
                        │
                        ▼
                tools/builtins/<domain>.py (actual tool)
```

### ChatCallbacks Protocol

The `ChatCallbacks` protocol lives in `loops/chat_loop.py` and decouples `ChatLoop` from all UI concerns:

```python
@runtime_checkable
class ChatCallbacks(Protocol):
    def on_thinking_start(self) -> None: ...
    def on_thinking_stop(self) -> None: ...
    def on_assistant_content(self, text: str) -> None: ...
    def on_thinking_content(self, text: str) -> None: ...
    def on_token_usage(self, total_tokens: int) -> None: ...
    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None: ...
    def on_tool_complete(self, call_id: str, result: str) -> None: ...
    def on_tools_cleanup(self) -> None: ...
    def on_system_message(self, text: str) -> None: ...
    async def request_confirmation(self, name: str, arguments: dict) -> object | None: ...
    def is_cancelled(self) -> bool: ...
```

Implementations:
- **`AppCallbacks`** (in `tui/app.py`) updates Textual widgets.
- **`CliCallbacks`** (in `cli_callbacks.py`) prints to the Rich console for one-shot CLI mode.

Because the protocol is `@runtime_checkable`, `isinstance(cb, ChatCallbacks)` verifies any adapter at construction time.

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
from ayder_cli.core.context_manager import ContextManagerProtocol, truncate_tool_result
from ayder_cli.core.context_manager_factory import context_manager_factory

# Console + logging
from ayder_cli.console import console
from ayder_cli.logging_config import setup_logging

# Services + providers
from ayder_cli.services.interactions import InteractionSink
from ayder_cli.providers import AIProvider, provider_orchestrator

# Loop
from ayder_cli.loops.chat_loop import ChatLoop, ChatCallbacks, ChatLoopConfig

# Application layer
from ayder_cli.application.runtime_factory import create_runtime, RuntimeComponents
from ayder_cli.application.execution_policy import ExecutionPolicy, ToolRequest

# Tools
from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.tools.schemas import tools_schema, TOOL_PERMISSIONS
from ayder_cli.tools.definition import TOOL_DEFINITIONS, TOOL_DEFINITIONS_BY_NAME
from ayder_cli.tools.builtins.filesystem import read_file, file_editor

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
    from ayder_cli.core.context import ProjectContext
```

### Protocol-Based Imports

The TUI uses protocols to avoid circular imports:

```python
# loops/chat_loop.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class ChatCallbacks(Protocol):
    ...

# tui/app.py
class AppCallbacks:
    """Implements ChatCallbacks for the Textual TUI."""
    ...

# cli_callbacks.py
class CliCallbacks:
    """Implements ChatCallbacks for one-shot CLI mode."""
    ...
```

---

## Common Patterns

### Building Services

```python
# From application/runtime_factory.py
def create_runtime():
    cfg = load_config()
    project_ctx = ProjectContext(".")
    tool_registry = create_default_registry(project_ctx)
    llm_provider = create_provider(cfg)
    # Returns RuntimeContext with all assembled services
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
2. **New Application-Layer Shared Logic**: Add to `application/` and import from `loops/chat_loop.py`.
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
- **Architecture**: Uses `AppCallbacks` to implement the `ChatCallbacks` protocol, decoupling business logic from UI

The application manages:
- LLM provider setup and configuration
- Tool registry initialization with middleware
- System prompt construction with project structure
- Process manager for background operations

### Chat Loop Summary (src/ayder_cli/loops/chat_loop.py)

`ChatLoop` implements the core async agentic process in a single class (the
previously-split `AgentLoopBase` and `LoopConfig` were merged back in):
- Handles repeated LLM calls with tool execution until completion
- Supports multiple tool call formats: OpenAI native (`tool_calls`), XML custom, JSON fallback
- Private helpers `_route_tool_calls()`, `_increment_iteration()`, `_is_escalation_result()` encapsulate routing, counting, and escalation detection
- Communicates with UI exclusively through the `ChatCallbacks` protocol; no Textual imports
- Extracts and emits `<think>` blocks separately from display content
- Routes *every* LLM response through the injected `ContextManagerProtocol` (`prepare_messages()` / `update_from_response()`); tool outputs are truncated at insertion time via `truncate_tool_result()` so the KV-cache prefix remains stable

Key features:
- Auto-approved tools run in parallel (`asyncio.gather`); confirmation-required tools run sequentially
- Confirmation gate applies to **both** OpenAI-format and XML/JSON custom tool calls
- `ExecutionPolicy.execute_with_registry()` is the single execution entry (validate → permission → execute)
- Token usage tracking and iteration limiting
- Pre-iteration hook (`pre_iteration_hook`) used by the agent system to inject summaries
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
- **Required-tool validation**: Raises `ImportError` if core tools (`file_explorer`, `read_file`, `file_editor`, `run_shell_command`) are absent
- **Permissions**: `"r"` (read), `"w"` (write), `"x"` (execute), `"http"` (network)
- **Safety flags**: `safe_mode_blocked`, `is_terminal` per definition
- **Path parameters**: Names listed in `path_parameters` are automatically resolved via `ProjectContext`
- **Aliases**: `parameter_aliases` tuples for common name normalisation
- **Schema generation**: `to_openai_schema()` returns the OpenAI function-calling dict
- **Plugin loading**: `tools/plugin_manager.py` can augment `TOOL_DEFINITIONS` at runtime from local or GitHub-sourced plugins

19 built-in tools across 9 definition files:
- Filesystem (3): `file_explorer`, `read_file`, `file_editor`
- Search (2): `search_codebase`, `get_project_structure`
- Shell (1): `run_shell_command`
- Memory (4): `save_memory`, `load_memory`, `save_context_memory`, `load_context_memory`
- Notes (1): `create_note`
- Background Processes (4): `run_background_process`, `get_background_output`, `kill_background_process`, `list_background_processes`
- Tasks (2): `list_tasks`, `show_task`
- Environment (1): `manage_environment_vars`
- Web (1): `fetch_web`

> The authoritative count comes from `len(TOOL_DEFINITIONS)`; run `python -c "from ayder_cli.tools.definition import TOOL_DEFINITIONS; print(len(TOOL_DEFINITIONS))"` to verify.

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

### Phase — Shared Agent Loop Base (reverted)

`AgentLoopBase` was briefly extracted to `loops/base.py` with `LoopConfig` in `loops/config.py`, then flattened back into `loops/chat_loop.py` (the indirection was paying no rent). The helpers (`_increment_iteration`, `_reset_iterations`, `_route_tool_calls`, `_is_escalation_result`) now live as private methods on `ChatLoop`; `ChatLoopConfig` is a dataclass at the top of the same file.

### Phase — Validation Unification (Phase 4)

- `validate_tool_call()` removed from `execution.py` — double-validation eliminated. Single path: `ExecutionPolicy → ValidationAuthority → SchemaValidator → registry.execute()`.
- `validate_args()` removed from `ToolRegistry` — all validation goes through `ValidationAuthority`.
- `SchemaValidator` gained type checking (integer/string) derived from tool definition schemas.

### Architecture Bug Fixes

| Bug | Fix |
|-----|-----|
| Double `on_thinking_stop()` on LLM exception | Removed from `except` blocks in `run()`; kept only in `finally` |
| Stale loop variable in `_discover_definitions()` | Collect `(definition, source_module)` tuples; unpack in duplicate-check loop |
| XML tool calls bypass confirmation gate | `_execute_custom_tool_calls()` now calls `_tool_needs_confirmation()` before `execute_with_registry()` |
| Silent post-execute callback failure | Added `logger.warning()` in `registry.py` post-execute exception handler |
| Dead `FileDiffConfirmation` + `confirm_file_diff()` | Removed from `execution_policy.py`; real confirmation goes through `ChatCallbacks.request_confirmation()` |
| Agents mishandling raw JSON tool calls | Fixed in `chat_loop.py` — raw_json path now normalizes through the same tool-call routing as OpenAI / XML |

### Phase — Provider Orchestration

`services/llm.py` retired. All provider implementations moved to `providers/impl/*.py`, with a shared base at `providers/base.py` and a driver-keyed factory at `providers/orchestrator.py` (singleton `provider_orchestrator`). Adding a new provider is a one-file drop plus a factory registration.

### Phase — Ollama KV-Cache-Aware Context Management

`ContextManagerProtocol` extracted in `core/context_manager.py`; concrete implementations split into:
- `DefaultContextManager` (`core/default_context_manager.py`) — tiered/heuristic compaction for estimator-driven providers.
- `OllamaContextManager` (`core/ollama_context_manager.py`) — stable-prefix + real-token accounting, uses `prompt_eval_count` / `prompt_eval_duration` directly.
- `CacheMonitor` (`core/cache_monitor.py`) — timing-based KV-cache hit detection driving adaptive compaction thresholds.

Selection lives in `core/context_manager_factory.py` (driver → class path registry). `create_runtime()` owns instantiation and calls `freeze_system_prompt()` once.

### Phase — opus47 critical fixes (2026-04-16)

Landed on main after an audit of context / KV-cache wiring. See `opus47.md` for the full report. Headline fixes:

| Finding | File | Fix |
|---------|------|-----|
| #1 Tool results stored untruncated | `loops/chat_loop.py` | Truncate at the single source of truth — overwrite `rd["result"]` before both UI notification and history append |
| #2 `CacheMonitor` never instantiated | `core/ollama_context_manager.py` | Instantiated in `__init__`; `cache_hit_ratio` populated; adaptive hot-cache threshold wired |
| #3 `max_history` ignored by Ollama manager | `core/ollama_context_manager.py` | Honored after compaction, trimming from the head on unit boundaries |
| #5 XML fallback dropped usage on empty done chunk | `providers/impl/ollama.py` | Yield unconditionally when `chunk.done`, attaching usage |
| #6 `should_compact` used estimator over real tokens | `core/default_context_manager.py` | Prefer `_last_prompt_tokens` when present |

### Phase — Plugin System

`tools/plugin_api.py`, `tools/plugin_manager.py`, `tools/plugin_github.py` introduced an extension mechanism for additional tools sourced from local files or GitHub-hosted packages. Loaded plugins feed into the same `TOOL_DEFINITIONS` auto-discovery pipeline.
