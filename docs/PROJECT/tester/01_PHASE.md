# Tester Task — Phase 01: Baseline and Governance Setup

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** QA/Test Engineer Agent  
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
| `QA_TEST_SCOPE` | `test-inventory` |

---

## 2. Core References (Read Before Proceeding)

All REFACTOR documentation is available locally in this branch (`arch/01/baseline-gate`):

1. `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md` — Phase-specific QA-* tasks
2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md` — Test migration policy and gate rubric
3. `docs/REFACTOR/TESTER_PROMPT.md` — Tester team operating guide
4. `docs/REFACTOR/PROJECT_MANAGERS_WORKFLOW.md` — Workflow and control sequence
5. `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md` — Architect's flow analysis
6. `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md` — Known risks
7. `AGENTS.md` — Test commands and conventions
8. Existing tests under `tests/` for patterns

> **Note:** REFACTOR docs were sourced from `logging` branch and are now available locally.

---

## 3. Mission

Execute Tester tasks for Phase 01 in parallel with Developer work. Build test inventory and mapping, identify obsolete test candidates, and add/confirm baseline characterization tests.

**Key Constraints:**
- Do not remove tests yet unless Architect approves early cleanup
- Work parallel to Developer (do not block on Developer branch)
- Target `arch/01/baseline-gate` branch
- Maintain or improve coverage in changed areas

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [ ] `PHASE_ID` and `QA_TEST_SCOPE` assigned
- [ ] `ARCH_GATE_BRANCH` exists: `arch/01/baseline-gate`
- [ ] Architect kickoff is complete
- [ ] Prior phase dependency is PASS (N/A for Phase 01 — first phase)

If any check fails: STOP and request correction from PM.

---

## 5. Branch Setup (Execute First)

Create QA branch from the gate branch:

```bash
git fetch origin
git checkout arch/01/baseline-gate
git pull --ff-only origin arch/01/baseline-gate
git checkout -b qa/01/test-inventory
git push -u origin qa/01/test-inventory
```

---

## 6. Tester Tasks for Phase 01

### QA-01.1 Test Inventory and Mapping

**Objective:** Build test map for impacted areas.

**Files to Inventory:**

| Test File | Area | Current Coverage | Refactor Impact |
|-----------|------|------------------|-----------------|
| `tests/services/tools/test_executor.py` | Tool execution | Tool executor logic | High - execution path changing |
| `tests/services/test_llm*.py` | LLM services | Provider interactions | Medium - message contract changes |
| `tests/ui/test_tui_chat_loop.py` | TUI loop | Chat loop behavior | High - async convergence |
| `tests/test_memory.py` | Memory/Checkpoint | Persistence layer | Medium - checkpoint flow changes |
| `tests/test_checkpoint_manager.py` | Checkpoint | Checkpoint I/O | High - checkpoint convergence |
| `tests/test_cli.py` | CLI entry | Command parsing | Low - entry point stable |

**Required Deliverable:** `docs/PROJECT/tester/01_PHASE/01_TEST_INVENTORY.md`

**Output Template:**
```markdown
# Test Inventory — Phase 01

## Impacted Test Areas

### tests/services/tools/test_executor.py
- **Purpose:** Tool execution flow testing
- **Key Tests:** ...
- **Refactor Impact:** Execution path will change with async convergence
- **Action Required:** Map to new execution contract in Phase 04-05

### tests/services/test_llm*.py
- **Purpose:** LLM provider testing
- **Key Tests:** ...
- **Refactor Impact:** Message contract normalization
- **Action Required:** Validate message shape compatibility

### tests/ui/test_tui_chat_loop.py
- **Purpose:** TUI chat loop behavior
- **Key Tests:** ...
- **Refactor Impact:** High - loop will converge with CLI
- **Action Required:** Characterization tests for current behavior

### tests/test_memory.py
- **Purpose:** Memory persistence
- **Key Tests:** ...
- **Refactor Impact:** Checkpoint behavior convergence
- **Action Required:** Verify checkpoint read/write behavior preserved

### tests/test_checkpoint_manager.py
- **Purpose:** Checkpoint I/O operations
- **Key Tests:** ...
- **Refactor Impact:** Checkpoint creation path divergence
- **Action Required:** Validate both CLI and TUI checkpoint paths

### tests/test_cli.py
- **Purpose:** CLI entry point
- **Key Tests:** ...
- **Refactor Impact:** Low - entry point stable
- **Action Required:** Baseline characterization
```

### QA-01.2 Obsolete-Test Candidate List

**Objective:** Identify tests likely tied to internals expected to change.

**Criteria for Obsolescence:**
- Tests directly assert on internal implementation details
- Tests mock components that will be replaced
- Tests validate behavior that will be intentionally changed

**Process:**
1. Review each test file for implementation-coupled assertions
2. Identify tests mocking:
   - Internal loop structures
   - Direct service-to-UI coupling
   - Sync/async boundary internals
3. Document removal rationale

**Required Deliverable:** `docs/PROJECT/tester/01_PHASE/01_OBSOLETE_TEST_CANDIDATES.md`

**Output Template:**
```markdown
# Obsolete Test Candidates — Phase 01

## Candidate List (Pending Architect Approval)

| Test File | Test Name | Reason Obsolete | Replacement Plan |
|-----------|-----------|-----------------|------------------|
| tests/.../test_xxx.py | test_yyy | Directly asserts on internal loop state | Replace with behavior characterization test |
| ... | ... | ... | ... |

## Early Cleanup Approved (if Architect approves)

| Test File | Test Name | Approval Status |
|-----------|-----------|-----------------|
| ... | ... | Pending |

## Notes
- Do not remove without Architect approval
- Each removal must map to replacement coverage
```

### QA-01.3 Baseline Characterization Tests

**Objective:** Add/confirm characterization tests for current behavior.

**Required Tests:**

1. **CLI command run path basic success**
   - Test: `tests/test_cli.py::TestCLI::test_basic_command_execution`
   - Verify: CLI can parse args and invoke runner
   - Status: Confirm existing or add new

2. **TUI chat loop basic success**
   - Test: `tests/ui/test_tui_chat_loop.py::TestTuiChatLoop::test_basic_message_flow`
   - Verify: TUI can process user input and generate response
   - Status: Confirm existing or add new

3. **Checkpoint read/write smoke**
   - Test: `tests/test_checkpoint_manager.py::TestCheckpointManager::test_save_and_read_checkpoint`
   - Verify: Checkpoint can be saved and restored
   - Status: Confirm existing or add new

**Required Deliverable:** `docs/PROJECT/tester/01_PHASE/01_CHARACTERIZATION_TESTS.md`

**Output Template:**
```markdown
# Baseline Characterization Tests — Phase 01

## CLI Command Path
- **Test:** tests/test_cli.py::TestCLI::test_basic_command_execution
- **Coverage:** Entry point through command execution
- **Status:** [ ] Existing | [ ] Added
- **Notes:** ...

## TUI Chat Loop
- **Test:** tests/ui/test_tui_chat_loop.py::TestTuiChatLoop::test_basic_message_flow
- **Coverage:** Input processing through response generation
- **Status:** [ ] Existing | [ ] Added
- **Notes:** ...

## Checkpoint Operations
- **Test:** tests/test_checkpoint_manager.py::TestCheckpointManager::test_save_and_read_checkpoint
- **Coverage:** Checkpoint persistence round-trip
- **Status:** [ ] Existing | [ ] Added
- **Notes:** ...

## New Characterization Tests Added
| Test File | Test Name | Purpose |
|-----------|-----------|---------|
| ... | ... | ... |
```

---

## 7. Local Validation Before Push

Run mandatory checks:

```bash
uv run poe lint
uv run poe test
```

When test architecture changed significantly:
```bash
uv run poe typecheck
uv run poe test-all
```

All checks must pass.

---

## 8. Commit and Push

Commit message format:
```
[PHASE-01][QA] test inventory and characterization tests
```

Push:
```bash
git push -u origin qa/01/test-inventory
```

---

## 9. Merge Request

Open MR:
- **Source:** `qa/01/test-inventory`
- **Target:** `arch/01/baseline-gate`
- **Reviewer:** Architect team

### MR Description Template

```markdown
## Phase 01 Tester Deliverables

### Changes
- [ ] Test inventory completed for impacted areas
- [ ] Obsolete test candidate list documented
- [ ] Baseline characterization tests confirmed/added

### Test Migration Mapping
| Removed Test | Reason | Replacement Test |
|--------------|--------|------------------|
| (none yet - pending Architect approval) | ... | ... |

### Verification
- [ ] `uv run poe lint` passes
- [ ] `uv run poe test` passes
- [ ] Coverage maintained or improved

### Files Changed
- docs/PROJECT/tester/01_PHASE/01_TEST_INVENTORY.md (new)
- docs/PROJECT/tester/01_PHASE/01_OBSOLETE_TEST_CANDIDATES.md (new)
- docs/PROJECT/tester/01_PHASE/01_CHARACTERIZATION_TESTS.md (new)
- tests/... (if characterization tests added)

### Notes for Architect Review
- No tests removed without approval
- Test inventory ready for Phase 02-06 planning
```

---

## 10. Control Check C (PM Validation Required)

Before Architect gate assignment (Step D), PM will verify:

- [ ] Tester branch exists: `qa/01/test-inventory`
- [ ] Tester posted remove→replace test migration mapping
- [ ] Tester listed acceptance-criteria tests for phase

If migration mapping is incomplete: PM will block gate request.

---

## 11. Done Definition

Done when:
- [ ] Tester branch `qa/01/test-inventory` exists
- [ ] Test inventory documented for all impacted areas
- [ ] Obsolete test candidate list created
- [ ] Baseline characterization tests confirmed/added
- [ ] All gate commands pass (lint, test)
- [ ] MR opened targeting `arch/01/baseline-gate`
- [ ] Control Check C items confirmed

---

*Generated from analysis of docs/REFACTOR/PROJECT_MANAGER_PROMPT.md and .ayder/architect_to_PM_phase01.md*
