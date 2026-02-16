# Architect Task — Phase 02: Runtime Factory and Message Contract

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Architect Agent  
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
| `QA_TEST_SCOPE` | `factory-contract-tests` |

---

## 2. Core References (Read Before Proceeding)

All REFACTOR documentation is available locally in `main` (Phase 01 merged):

1. `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` — Phase-specific scope
2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md` — Program constraints + acceptance rubric
3. `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE_ARCHITECT_DECISION.md` — Prior phase decision
4. `docs/REFACTOR/ARCHITECT_PROMPT.md` — Architect operating guide
5. `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md` — Prior phase baseline
6. `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md` — Risk context (R02-MSG)
7. `AGENTS.md` + `.ayder/PROJECT_STRUCTURE.md` — Coding conventions

---

## 3. Mission

Kick off Phase 02 by establishing the architecture for shared runtime composition and message normalization. This phase introduces actual behavior changes: the runtime factory and message contract.

**Key Constraints:**
- Single shared factory for CLI and TUI dependency assembly
- Message normalization must handle dict/object safely
- No output/UX regression in normal flows
- Preserve async architecture constraint for Phase 04

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [ ] `PHASE_ID` assigned
- [ ] `PHASE_DOC` located and readable
- [ ] Prior phase (01) is PASS — see `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE_ARCHITECT_DECISION.md`
- [ ] Architect gate branch exists or will be created: `arch/02/runtime-factory-gate`

If any check fails: STOP and request correction from PM.

---

## 5. Architect Tasks for Phase 02 Kickoff

### ARC-02.0 Phase 02 Architecture Design

**Objective:** Design the runtime factory and message contract architecture.

**Required Design Decisions:**

| Component | Design Question | Deliverable |
|-----------|-----------------|-------------|
| Runtime Factory | Module location and interface | Design doc section |
| Factory Contents | Config, LLM, process manager, tool registry, executor, checkpoint/memory | Interface spec |
| CLI Wiring | How `cli_runner.py` adopts factory | Migration plan |
| TUI Wiring | How `tui/app.py` adopts factory | Migration plan |
| Message Contract | Dict/object safe access pattern | Contract spec |
| Checkpoint Integration | Message normalization for summary prep | Integration plan |

**Deliverable:** `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md`

**Template:**
```markdown
# Phase 02 Architecture Design

## Runtime Factory Design

### Module Location
- `src/ayder_cli/application/runtime_factory.py`

### Factory Interface
```python
def create_runtime(config: Config) -> RuntimeComponents: ...
```

### Assembled Components
- Config
- LLM Provider
- Process Manager
- Tool Registry
- Tool Executor
- Checkpoint Manager
- Memory Manager

## Message Contract Design

### Normalized Message Access
```python
def get_message_content(msg: dict | Any) -> str: ...
def get_message_role(msg: dict | Any) -> str: ...
```

### Integration Points
- Session append
- Checkpoint summary preparation

## Migration Plan

### CLI (`cli_runner.py`)
- Current: `_build_services()` inline
- Target: Use `runtime_factory.create_runtime()`

### TUI (`tui/app.py`)
- Current: Inline initialization in `__init__`
- Target: Use `runtime_factory.create_runtime()`

## Risk Mitigations
- ...
```

### ARC-02.1 Factory Interface Definition

**Objective:** Define the factory interface and `RuntimeComponents` container.

**Required:**
- Factory function signature
- Return type (dataclass or protocol)
- Component list matching Phase 02 spec

**Deliverable:** Interface definition in design doc or stub code

### ARC-02.2 Message Contract Specification

**Objective:** Define message normalization contract.

**Requirements:**
- Handle `dict` messages (OpenAI format)
- Handle object messages with attributes (provider-specific)
- Safe access for `content` and `role`
- Used in session handling and checkpoint summary

**Deliverable:** Contract spec in design doc

### ARC-02.3 Phase 02 Risk Update

**Objective:** Update risk assessment for Phase 02-specific risks.

**Risks to Address:**

| Risk ID | Risk | Mitigation |
|---------|------|------------|
| R02-FACTORY | Factory adoption may break CLI/TUI initialization | Staged rollout with fallback verification |
| R02-MSG | Message normalization may miss edge cases | Comprehensive test coverage for mixed formats |
| R02-PARITY | CLI and TUI may diverge in factory usage | Factory tests validate both paths |

**Deliverable:** `docs/PROJECT/architect/02_PHASE/02_RISK_REGISTER.md`

---

## 6. Branch Setup (Execute First)

Create the Architect gate branch from current `main`:

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout -B arch/02/runtime-factory-gate
git push -u origin arch/02/runtime-factory-gate
```

Confirm branch exists and is current with `main`.

---

## 7. Gate Criteria (Future Gate Step D)

This section is for reference when Phase 02 reaches Architect Gate (Step D):

### ARC-02.1 Architecture Review
- [ ] Verify duplicated composition roots are removed/reduced to thin wrappers
- [ ] Confirm factory is single source of dependency assembly

### ARC-02.2 Command Gate
Run and record results:
```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

### ARC-02.3 Acceptance Review
- [ ] Validate remove→replace test mapping
- [ ] Ensure no phase-inappropriate architectural churn

---

## 8. Acceptance Criteria for Phase 02

- One shared runtime factory used by both CLI and TUI
- Message normalization prevents dict/object shape regressions
- Required tests for factory and message contract exist and pass
- Architect PASS with no open S1/S2 issues

---

## 9. Exit Artifacts to Produce

| Artifact | Location | Owner |
|----------|----------|-------|
| Architecture design | `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md` | Architect |
| Risk register update | `docs/PROJECT/architect/02_PHASE/02_RISK_REGISTER.md` | Architect |
| Factory interface stub | `src/ayder_cli/application/runtime_factory.py` (optional) | Architect |
| Architect decision | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT_ARCHITECT_DECISION.md` | Architect (gate) |

---

## 10. Sequence Reminder

Per `PROJECT_MANAGER_PROMPT.md`:

1. **Step A (NOW):** Architect Kickoff Assignment ← YOU ARE HERE
2. Step B: Developer Assignment (parallel to C)
3. Step C: Tester Assignment (parallel to B)
4. Step D: Architect Gate Assignment (re-assign with MRs)

Developer and Tester branches will target `arch/02/runtime-factory-gate`.

---

## 11. Dependencies from Phase 01

Phase 02 builds on Phase 01 outputs:

| Phase 01 Output | Phase 02 Usage |
|-----------------|----------------|
| `01_BASELINE_INVENTORY.md` | Understand current CLI/TUI composition |
| `01_SCAFFOLDING_PLAN.md` | `application/` package ready for factory |
| `01_RISK_REGISTER.md` | R02-MSG risk addressed in message contract |
| `01_TEST_INVENTORY.md` | Know which tests to update/remove |

---

## 12. Done Definition for Kickoff

Done when:
- [ ] Gate branch `arch/02/runtime-factory-gate` exists and is current with `main`
- [ ] Architecture design document drafted
- [ ] Factory interface defined
- [ ] Message contract specified
- [ ] Risk register updated for Phase 02
- [ ] Kickoff summary posted for PM review

---

*Phase 02 Step A — Architect Kickoff Assignment*
