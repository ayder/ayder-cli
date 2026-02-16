# Developer Task — Phase 02: Runtime Factory and Message Contract

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Developer Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Phase Doc:** `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md`

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` |
| `PROJECT_BRANCH` | `main` |
| `ARCH_GATE_BRANCH` | `arch/02/runtime-factory-gate` |
| `DEV_TASK_SCOPE` | `runtime-factory` |

---

## 2. Core References (Read Before Proceeding)

All documentation available in `arch/02/runtime-factory-gate`:

1. `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` — Phase DEV-* tasks
2. `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md` — **CRITICAL: Factory and contract specs**
3. `docs/PROJECT/architect/02_PHASE/02_RISK_REGISTER.md` — Phase 02 risks
4. `docs/REFACTOR/DEVELOPER_PROMPT.md` — Developer operating guide
5. `AGENTS.md` + `.ayder/PROJECT_STRUCTURE.md` — Coding conventions

---

## 3. Mission

Implement Phase 02 behavior changes: shared runtime factory and message normalization contract. This phase introduces actual code changes (not just documentation).

**Key Constraints:**
- CLI and TUI must use same `create_runtime()` factory
- Message contract must handle dict/object safely
- No output/UX regression in normal flows
- No Phase 04 async changes yet

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [ ] `PHASE_ID` and `DEV_TASK_SCOPE` assigned
- [ ] `ARCH_GATE_BRANCH` exists: `arch/02/runtime-factory-gate`
- [ ] Architect kickoff complete (design docs exist)
- [ ] Prior phase (01) is PASS

If any check fails: STOP and request correction from PM.

---

## 5. Branch Setup (Execute First)

Create developer branch from the gate branch:

```bash
git fetch origin
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b dev/02/runtime-factory
git push -u origin dev/02/runtime-factory
```

---

## 6. Developer Tasks for Phase 02

### DEV-02.1 Shared Runtime Factory

**Objective:** Implement `src/ayder_cli/application/runtime_factory.py`

**Requirements (from Architecture Design):**

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

**Assembly Requirements:**
- config: `load_config()` unless injected
- llm provider: `create_llm_provider(config)`
- process manager: `ProcessManager(max_processes=config.max_background_processes)`
- project context: `ProjectContext(project_root)`
- tool registry: `create_default_registry(project_ctx, process_manager=...)`
- tool executor: `ToolExecutor(tool_registry)`
- checkpoint manager: `CheckpointManager(project_ctx)`
- memory manager: `MemoryManager(project_ctx, llm_provider=..., tool_executor=..., checkpoint_manager=...)`
- system prompt: `SYSTEM_PROMPT + PROJECT_STRUCTURE_MACRO_TEMPLATE`

**Deliverable:** Working `runtime_factory.py` with tests

### DEV-02.2 Wire CLI to Factory

**Objective:** Update `src/ayder_cli/cli_runner.py` to use factory

**Current:** `_build_services()` performs inline composition

**Target:** Replace `_build_services()` with `create_runtime(...)` call

**Requirements:**
- Preserve existing `CommandRunner` behavior
- No output/behavior regression
- Import from `application.runtime_factory`

**Files to Modify:**
- `src/ayder_cli/cli_runner.py`

### DEV-02.3 Wire TUI to Factory

**Objective:** Update `src/ayder_cli/tui/app.py` to use factory

**Current:** `AyderApp.__init__()` performs inline composition

**Target:** Use `create_runtime(...)` for shared dependencies

**Requirements:**
- Keep TUI-only behavior local: callbacks, middleware, widget lifecycle
- No UX regression in input handling, tool panel, confirmation modals
- Import from `application.runtime_factory`

**Files to Modify:**
- `src/ayder_cli/tui/app.py`

### DEV-02.4 Message Normalization Contract

**Objective:** Implement `src/ayder_cli/application/message_contract.py`

**Requirements (from Architecture Design):**

```python
def get_message_role(message: dict | object) -> str: ...
def get_message_content(message: dict | object) -> str: ...
def get_message_tool_calls(message: dict | object) -> list: ...
def to_message_dict(message: dict | object) -> dict[str, object]: ...
```

**Contract Rules:**
1. Accept both dict messages and provider/object messages
2. Never assume `.get(...)` exists on message objects
3. Return stable string content (`""` fallback; coerce with `str(...)`)
4. Keep role fallback explicit (`"unknown"` only when truly absent)
5. Preserve `tool_calls`, `tool_call_id`, and `name` fields

**Integration Points (apply helpers in):**
- `src/ayder_cli/memory.py` (`_build_conversation_summary`)
- `src/ayder_cli/tui/chat_loop.py` (`_handle_checkpoint` summary)
- `src/ayder_cli/tui/commands.py` (`/compact`, `/save-memory` extraction)

**Files to Modify:**
- `src/ayder_cli/application/message_contract.py` (new)
- `src/ayder_cli/memory.py`
- `src/ayder_cli/tui/chat_loop.py`
- `src/ayder_cli/tui/commands.py`

---

## 7. Implementation Sequence

1. **Introduce factory and contract modules with tests**
2. **Wire CLI to factory**
3. **Wire TUI to factory**
4. **Apply message contract in summary/compaction paths**
5. **Run full command gate**

---

## 8. Local Validation Before Push

Run mandatory checks:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

All checks must pass. If failures occur, fix before opening MR.

---

## 9. Commit and Push

Commit message format:
```
[PHASE-02][DEV] runtime factory and message contract implementation
```

Push:
```bash
git push -u origin dev/02/runtime-factory
```

---

## 10. Merge Request

Open MR:
- **Source:** `dev/02/runtime-factory`
- **Target:** `arch/02/runtime-factory-gate`
- **Reviewer:** Architect team

### MR Description Template

```markdown
## Phase 02 Developer Deliverables

### Changes
- [ ] Runtime factory implemented (`application/runtime_factory.py`)
- [ ] CLI wired to factory (`cli_runner.py`)
- [ ] TUI wired to factory (`tui/app.py`)
- [ ] Message contract implemented (`application/message_contract.py`)
- [ ] Message contract integrated in memory, chat_loop, commands

### Verification
- [ ] `uv run poe lint` passes
- [ ] `uv run poe typecheck` passes
- [ ] `uv run poe test` passes

### Files Changed
- src/ayder_cli/application/runtime_factory.py (new)
- src/ayder_cli/application/message_contract.py (new)
- src/ayder_cli/cli_runner.py (modified)
- src/ayder_cli/tui/app.py (modified)
- src/ayder_cli/memory.py (modified)
- src/ayder_cli/tui/chat_loop.py (modified)
- src/ayder_cli/tui/commands.py (modified)
- tests/... (new tests)

### Notes for Architect Review
- Factory assembles all 9 components per spec
- Message contract handles dict/object safely
- No UX regressions observed in manual testing
```

---

## 11. Control Check B (PM Validation Required)

Before Tester assignment (Step C), PM will verify:

- [ ] Developer branch exists: `dev/02/runtime-factory`
- [ ] Developer confirmed DEV-* tasks in scope
- [ ] Developer posted implementation plan and expected changed files

If scope drift appears: PM will stop and send back for correction.

---

## 12. Done Definition

Done when:
- [ ] Developer branch `dev/02/runtime-factory` exists
- [ ] Runtime factory implemented and tested
- [ ] CLI wired to factory
- [ ] TUI wired to factory
- [ ] Message contract implemented and integrated
- [ ] All gate commands pass (lint, typecheck, test)
- [ ] MR opened targeting `arch/02/runtime-factory-gate`
- [ ] Control Check B items confirmed

---

*Generated from analysis of .ayder/architect_to_PM_phase02.pm*
