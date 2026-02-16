# Phase 02 Architecture Design

## Scope and Objective

Phase 02 introduces two architecture changes that are intentionally behavior-affecting:

1. One shared runtime composition path for both CLI and TUI.
2. One normalized message-access contract that is safe for both dict and object message shapes.

This document defines the target interfaces and migration plan for Developer/Tester execution in Phase 02.

---

## Runtime Factory Design

### Module Location

- `src/ayder_cli/application/runtime_factory.py`

### Factory Interface

```python
@dataclass
class RuntimeComponents:
    config: Config
    llm_provider: LLMProvider
    process_manager: ProcessManager
    project_ctx: ProjectContext
    tool_registry: ToolRegistry
    tool_executor: ToolExecutor
    checkpoint_manager: CheckpointManager
    memory_manager: MemoryManager
    system_prompt: str

def create_runtime(
    *,
    config: Config | None = None,
    project_root: str = ".",
    model_name: str | None = None,
) -> RuntimeComponents: ...
```

### Assembled Components (Single Source of Composition)

`create_runtime()` must assemble and return:

- config (`load_config()` unless injected)
- llm provider (`create_llm_provider(config)`)
- process manager (`ProcessManager(max_processes=config.max_background_processes)`)
- project context (`ProjectContext(project_root)`)
- tool registry (`create_default_registry(project_ctx, process_manager=...)`)
- tool executor (`ToolExecutor(tool_registry)`)
- checkpoint manager (`CheckpointManager(project_ctx)`)
- memory manager (`MemoryManager(project_ctx, llm_provider=..., tool_executor=..., checkpoint_manager=...)`)
- enhanced system prompt (`SYSTEM_PROMPT + PROJECT_STRUCTURE_MACRO_TEMPLATE`)

### Factory Notes by Surface

- CLI currently composes dependencies in `_build_services()` (`src/ayder_cli/cli_runner.py`).
- TUI currently composes dependencies in `AyderApp.__init__()` (`src/ayder_cli/tui/app.py`).
- TUI must keep UI-specific setup local (`_setup_registry_callbacks`, `_setup_registry_middleware`) while consuming factory-built core dependencies.

---

## Message Contract Design

### Problem

Current code has mixed assumptions:

- some paths append raw message objects (`session.append_raw(msg)`)
- summary/preparation code in multiple modules assumes dict-only access with `msg.get(...)`

This creates regressions when message objects are present during checkpoint/compaction/memory flows.

### Contract Module

- `src/ayder_cli/application/message_contract.py`

### Required Helpers

```python
def get_message_role(message: dict | object) -> str: ...
def get_message_content(message: dict | object) -> str: ...
def get_message_tool_calls(message: dict | object) -> list: ...
def to_message_dict(message: dict | object) -> dict[str, object]: ...
```

### Contract Rules

1. Accept both dict messages and provider/object messages.
2. Never assume `.get(...)` exists on message objects.
3. Return stable string content (`""` fallback; coerce non-string with `str(...)`).
4. Keep role fallback explicit (`"unknown"` only when truly absent).
5. Preserve `tool_calls`, `tool_call_id`, and `name` fields where present.

### Integration Points (Phase 02)

Use message contract helpers in:

- `src/ayder_cli/memory.py` (`_build_conversation_summary`)
- `src/ayder_cli/tui/chat_loop.py` (`_handle_checkpoint` summary build)
- `src/ayder_cli/tui/commands.py` (`/compact` and `/save-memory` conversation extraction)
- any session append/raw handling where message shape can vary

---

## Migration Plan

### CLI (`src/ayder_cli/cli_runner.py`)

Current:
- `_build_services()` performs full inline composition.

Target:
- replace `_build_services()` internals with `create_runtime(...)` call.
- preserve existing `CommandRunner` behavior and output.

### TUI (`src/ayder_cli/tui/app.py`)

Current:
- `AyderApp.__init__()` performs full inline composition.

Target:
- use `create_runtime(...)` for shared runtime dependencies.
- keep TUI-only behavior local: callbacks, middleware, widget lifecycle.
- no UX regression in input handling, tool panel updates, confirmation modals.

### Sequencing

1. Introduce factory and contract modules with tests.
2. Wire CLI to factory.
3. Wire TUI to factory.
4. Apply message contract in summary/compaction paths.
5. Run full phase command gate and targeted parity tests.

---

## Verification and Acceptance Mapping

Phase 02 acceptance criteria are satisfied only when all are true:

- one shared factory is used by both CLI and TUI
- message normalization prevents dict/object shape regressions
- required factory and message-contract tests pass
- no open S1/S2 issues at architect gate

Validation commands at gate:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

---

## Implementation Boundaries

- No phase-inappropriate architectural churn outside runtime composition and message contract scope.
- No early Phase 04 async-loop convergence in this phase.
- Keep tool discovery/plugin model unchanged unless required by Phase 02 acceptance.
