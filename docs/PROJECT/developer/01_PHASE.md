# Developer Task — Phase 01: Baseline and Governance Setup

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Developer Agent  
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

---

## 2. Core References (Read Before Proceeding)

All REFACTOR documentation is available locally in this branch (`arch/01/baseline-gate`):

1. `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md` — Phase-specific DEV-* tasks
2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md` — Program constraints + acceptance rubric
3. `docs/REFACTOR/DEVELOPER_PROMPT.md` — Developer team operating guide
4. `docs/REFACTOR/PROJECT_MANAGERS_WORKFLOW.md` — Workflow and control sequence
5. `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md` — Architect's flow analysis
6. `docs/PROJECT/architect/01_PHASE/01_SCAFFOLDING_PLAN.md` — Target structure definition
7. `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md` — Known risks and mitigations
8. `AGENTS.md` + `.ayder/PROJECT_STRUCTURE.md` — Coding conventions

> **Note:** REFACTOR docs were sourced from `logging` branch and are now available locally.

---

## 3. Mission

Execute Developer tasks for Phase 01. This phase must NOT introduce intentional runtime behavior changes. Focus on documentation, inventory, and scaffolding only.

**Key Constraints:**
- No intentional runtime behavior changes
- Keep existing import paths untouched
- Do not wire new architecture yet—only placeholders/scaffolding
- All work targets `arch/01/baseline-gate` branch

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [ ] `PHASE_ID` and `DEV_TASK_SCOPE` assigned
- [ ] `ARCH_GATE_BRANCH` exists: `arch/01/baseline-gate`
- [ ] Architect kickoff is complete (baseline inventory exists)
- [ ] Prior phase dependency is PASS (N/A for Phase 01 — first phase)

If any check fails: STOP and request correction from PM.

---

## 5. Branch Setup (Execute First)

Create developer branch from the gate branch:

```bash
git fetch origin
git checkout arch/01/baseline-gate
git pull --ff-only origin arch/01/baseline-gate
git checkout -b dev/01/baseline-inventory
git push -u origin dev/01/baseline-inventory
```

---

## 6. Developer Tasks for Phase 01

### DEV-01.1 Baseline Inventory

**Objective:** Document current key flows and file ownership based on Architect's analysis.

**Required Deliverable:** Update/extend `docs/PROJECT/developer/01_PHASE/01_DEV_BASELINE_NOTES.md`

**Analysis Requirements:**

| Flow Area | Verification Task | Key Files |
|-----------|-------------------|-----------|
| CLI orchestration path | Confirm entry flow from `cli.py` through `ChatLoop` | `cli.py`, `cli_runner.py`, `client.py`, `chat_loop.py` |
| TUI orchestration path | Confirm entry flow from `AyderApp` through `TuiChatLoop` | `tui/app.py`, `tui/chat_loop.py` |
| Checkpoint flow | Identify sync points and data persistence | `checkpoint_manager.py`, `memory.py` |
| Tool execution path | Map confirmation and execution flow | `services/tools/executor.py`, `tools/registry.py` |

**Output Template:**
```markdown
# Developer Baseline Notes — Phase 01

## CLI Flow Verification
- Entry point confirmed: ...
- Service building pattern: ...
- Observations: ...

## TUI Flow Verification  
- Entry point confirmed: ...
- Callback pattern for UI updates: ...
- Observations: ...

## Checkpoint Behavior Notes
- CLI checkpoint trigger: ...
- TUI checkpoint trigger: ...
- Divergence observations: ...

## Tool Execution Notes
- CLI confirmation flow: ...
- TUI confirmation flow: ...
- Result formatting differences: ...

## Implementation Concerns for Future Phases
- Risk areas identified: ...
- Recommended refactoring order: ...
```

### DEV-01.2 Refactor Workspace Scaffolding

**Objective:** Create/confirm target module placeholders (no behavior wiring yet).

**Required Actions:**

1. Verify `src/ayder_cli/application/` package exists:
   - `__init__.py` present
   - `README.md` present

2. If missing, create:
   ```bash
   mkdir -p src/ayder_cli/application
   touch src/ayder_cli/application/__init__.py
   ```

3. Populate `__init__.py`:
   ```python
   """Application composition layer placeholders for refactor phases."""
   ```

4. Populate `README.md`:
   ```markdown
   # application package

   This package will host runtime composition and orchestration boundaries introduced
   incrementally in refactor phases 02-06. Phase 01 keeps this package as scaffold
   only; no runtime wiring is allowed in this phase.
   ```

**Guardrails:**
- Keep imports untouched in runtime paths during this phase
- Do not import from `application` package in existing code yet
- No behavior wiring allowed

### DEV-01.3 Risk Register

**Objective:** Provide a concise risk list with mitigation proposals.

**Required Deliverable:** `docs/PROJECT/developer/01_PHASE/01_DEV_RISK_ASSESSMENT.md`

**Risk Categories to Address:**

| Risk ID | Risk | Mitigation Proposal |
|---------|------|---------------------|
| R01-ASYNC | Async migration from sync CLI loop | Identify all blocking I/O calls; plan async wrappers |
| R02-MSG | Message shape differences between CLI/TUI | Document current message formats; design normalization layer |
| R03-TEST | Test breakage during refactor | Map tests to behaviors; prepare characterization tests |

**Output Template:**
```markdown
# Developer Risk Assessment — Phase 01

## R01-ASYNC: Async Migration Risk
**Description:** CLI currently uses synchronous flow; TUI uses async. Convergence required.
**Impact:** High
**Mitigation:** 
- Inventory all sync I/O in CLI path
- Plan gradual async conversion with compatibility layers
- Test thoroughly at each step

## R02-MSG: Message Shape Risk  
**Description:** CLI and TUI produce different message structures for similar operations.
**Impact:** Medium
**Mitigation:**
- Document current message schemas
- Design normalized message contract
- Implement adapter pattern for transition

## R03-TEST: Test Breakage Risk
**Description:** Internal refactoring may break existing tests.
**Impact:** Medium
**Mitigation:**
- Map existing tests to behavior contracts
- Prioritize characterization tests
- Maintain coverage during changes
```

---

## 7. Local Validation Before Push

Run mandatory checks and record results:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

All checks must pass. If failures occur, fix before opening MR.

---

## 8. Commit and Push

Commit message format:
```
[PHASE-01][DEV] baseline inventory and scaffolding
```

Push:
```bash
git push -u origin dev/01/baseline-inventory
```

---

## 9. Merge Request

Open MR:
- **Source:** `dev/01/baseline-inventory`
- **Target:** `arch/01/baseline-gate`
- **Reviewer:** Architect team

### MR Description Template

```markdown
## Phase 01 Developer Deliverables

### Changes
- [ ] Baseline inventory notes added
- [ ] Application package scaffold confirmed/created
- [ ] Risk assessment documented

### Verification
- [ ] `uv run poe lint` passes
- [ ] `uv run poe typecheck` passes
- [ ] `uv run poe test` passes

### Files Changed
- docs/PROJECT/developer/01_PHASE/01_DEV_BASELINE_NOTES.md (new)
- docs/PROJECT/developer/01_PHASE/01_DEV_RISK_ASSESSMENT.md (new)
- src/ayder_cli/application/__init__.py (scaffold)
- src/ayder_cli/application/README.md (scaffold)

### Notes for Architect Review
- No runtime behavior changes introduced
- Scaffolding only—no wiring changes
```

---

## 10. Control Check B (PM Validation Required)

Before Tester assignment (Step C), PM will verify:

- [ ] Developer branch exists: `dev/01/baseline-inventory`
- [ ] Developer confirmed DEV-* tasks in scope
- [ ] Developer posted implementation plan and expected changed files

If scope drift appears: PM will stop and send back for correction.

---

## 11. Done Definition

Done when:
- [ ] Developer branch `dev/01/baseline-inventory` exists
- [ ] Baseline inventory notes documented
- [ ] Application package scaffold confirmed
- [ ] Risk assessment documented
- [ ] All gate commands pass (lint, typecheck, test)
- [ ] MR opened targeting `arch/01/baseline-gate`
- [ ] Control Check B items confirmed

---

*Generated from analysis of docs/REFACTOR/PROJECT_MANAGER_PROMPT.md and .ayder/architect_to_PM_phase01.md*
