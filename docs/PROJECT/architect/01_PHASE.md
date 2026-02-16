# Architect Task — Phase 01: Baseline and Governance Setup

**Status:** IN_PROGRESS  
**Assigned:** Architect Agent  
**Phase ID:** `01_PHASE_BASELINE_AND_GOVERNANCE`  
**Phase Doc:** `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md`

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `01_PHASE_BASELINE_AND_GOVERNANCE` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md` |
| `PROJECT_BRANCH` | `main` |
| `ARCH_GATE_BRANCH` | `arch/01/baseline-gate` |
| `DEV_TASK_SCOPE` | `baseline-inventory` |
| `QA_TEST_SCOPE` | `test-inventory` |

---

## 2. Core References (Read Before Proceeding)

All REFACTOR documentation is available locally in this branch (`arch/01/baseline-gate`):

1. `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md` — Phase-specific scope and criteria
2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md` — Program constraints + acceptance rubric
3. `docs/REFACTOR/ARCHITECT_PROMPT.md` — Architect operating guide
4. `docs/REFACTOR/PROJECT_MANAGERS_WORKFLOW.md` — Control sequence and merge policy
5. `docs/REFACTOR/PROJECT_MANAGER_PROMPT.md` — PM workflow reference
6. `AGENTS.md` + `.ayder/PROJECT_STRUCTURE.md` — Repo standards + architecture context

> **Note:** REFACTOR docs were sourced from `logging` branch and are now available locally.

---

## 3. Mission

Establish a controlled baseline before architectural change. This phase must NOT introduce intentional runtime behavior changes. Prepare governance, inventory, and baseline checks only.

**Key Constraints:**
- No intentional runtime behavior changes
- Do not wire new architecture yet—only placeholders/scaffolding
- Async architecture constraint must be preserved for future phases

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [x] `PHASE_ID` assigned
- [x] `PHASE_DOC` located and readable
- [ ] Prior phase dependency is PASS (N/A for Phase 01 — first phase)
- [ ] Architect gate branch exists or will be created: `arch/01/baseline-gate`

If any check fails: STOP and request correction from PM.

---

## 5. Architect Tasks for Phase 01 Kickoff

### ARC-01.1 Baseline Inventory Review (Kickoff)

**Objective:** Document current key flows and file ownership for baseline understanding.

**Required Analysis:**

| Flow Area | Files to Analyze | Key Questions |
|-----------|------------------|---------------|
| CLI orchestration path | `src/ayder_cli/cli.py`, `src/ayder_cli/cli_runner.py` | Entry point, command dispatch, argument parsing |
| TUI orchestration path | `src/ayder_cli/tui/app.py`, `src/ayder_cli/tui/chat_loop.py` | App lifecycle, widget tree, event handling |
| Checkpoint flow (CLI) | `src/ayder_cli/checkpoint_manager.py`, `src/ayder_cli/memory.py` | How checkpoints are saved/loaded in CLI mode |
| Checkpoint flow (TUI) | `src/ayder_cli/tui/chat_loop.py` + checkpoint imports | How checkpoints are saved/loaded in TUI mode |
| Tool execution (CLI) | `src/ayder_cli/services/tools/executor.py`, `src/ayder_cli/chat_loop.py` | Tool call flow, confirmation handling |
| Tool execution (TUI) | `src/ayder_cli/tui/chat_loop.py`, tool panel integration | Tool call flow, UI feedback |

**Deliverable:** Produce `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md`

Template structure:
```markdown
# Phase 01 Baseline Inventory

## 1. CLI Orchestration Path
- Entry: `cli.py::main()`
- Flow: ...
- Key files: ...

## 2. TUI Orchestration Path
- Entry: `tui/app.py::AyderApp`
- Flow: ...
- Key files: ...

## 3. Checkpoint Flow (Both Paths)
- CLI path: ...
- TUI path: ...
- Divergence notes: ...

## 4. Tool Execution Flow (Both Paths)
- CLI path: ...
- TUI path: ...
- Divergence notes: ...

## 5. Risk Observations (Initial)
- ...
```

### ARC-01.2 Refactor Workspace Scaffolding Plan

**Objective:** Define target module structure for future phases (no behavior wiring yet).

**Required Scaffolding:**

```
src/ayder_cli/
├── application/          # NEW: Application composition layer
│   ├── __init__.py
│   └── README.md         # Explain future purpose
```

**Deliverable:** Document planned structure in `docs/PROJECT/architect/01_PHASE/01_SCAFFOLDING_PLAN.md`

Include:
- Directory creation commands
- Placeholder `__init__.py` content
- Phase-by-phase population plan

### ARC-01.3 Risk Register

**Objective:** Identify and document key risks with mitigation proposals.

**Required Risk Analysis:**

| Risk ID | Risk | Severity | Mitigation Proposal |
|---------|------|----------|---------------------|
| R01-ASYNC | Async migration from sync CLI loop | High | Document current sync points; identify await boundaries |
| R02-MSG | Message shape changes between CLI/TUI | Medium | Inventory current message formats; design normalized contract |
| R03-TEST | Test breakage during refactor | Medium | Map test-to-behavior relationships; prepare characterization tests |

**Deliverable:** `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md`

---

## 6. Branch Setup (Execute First)

Create the Architect gate branch before any other work:

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout -B arch/01/baseline-gate
git push -u origin arch/01/baseline-gate
```

Confirm branch exists and is current with `main`.

---

## 7. Gate Criteria (Future Gate Step D)

This section is for reference when Phase 01 reaches Architect Gate (Step D):

### ARC-01.1 Baseline Review (Gate)
- [ ] Validate inventory completeness and correctness
- [ ] Confirm no unapproved behavioral changes in Developer MRs

### ARC-01.2 Command Gate (Mandatory)
Run and record results:
```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

### ARC-01.3 Sign-off Decision
- **PASS** if baseline + governance artifacts complete and checks pass
- **REWORK_REQUIRED** with explicit DEV/QA ticket list otherwise

---

## 8. Acceptance Criteria for Phase 01

- [ ] Baseline inventory exists and is architect-approved
- [ ] Impacted test map exists with obsolete candidate list (from QA)
- [ ] Required gate commands pass
- [ ] No intentional runtime behavior change introduced

---

## 9. Exit Artifacts to Produce

| Artifact | Location | Owner |
|----------|----------|-------|
| Baseline inventory | `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md` | Architect |
| Test migration map (initial) | `docs/PROJECT/architect/01_PHASE/01_TEST_MIGRATION_MAP.md` | QA (Architect reviews) |
| Scaffolding plan | `docs/PROJECT/architect/01_PHASE/01_SCAFFOLDING_PLAN.md` | Architect |
| Risk register | `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md` | Architect |
| Architect gate note | `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE_ARCHITECT_DECISION.md` | Architect (gate step) |

---

## 10. Sequence Reminder

Per `PROJECT_MANAGER_PROMPT.md`:

1. **Step A (NOW):** Architect Kickoff Assignment ← YOU ARE HERE
2. Step B: Developer Assignment (parallel to C)
3. Step C: Tester Assignment (parallel to B)
4. Step D: Architect Gate Assignment (re-assign with MRs)

Developer and Tester branches will target `arch/01/baseline-gate`.

---

## 11. Done Definition for Kickoff

Done when:
- [ ] Gate branch `arch/01/baseline-gate` exists and is current with `main`
- [ ] Baseline inventory artifact drafted
- [ ] Scaffolding plan documented
- [ ] Risk register documented
- [ ] Kickoff summary posted for PM review

---

*Generated from analysis of docs/REFACTOR/PROJECT_MANAGER_PROMPT.md*
