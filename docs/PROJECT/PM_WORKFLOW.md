# Project Manager Workflow — Phase 02 Runtime Factory and Message Contract

**Program:** ayder-cli Refactor  
**Current Phase:** 02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT  
**Last Updated:** 2026-02-16

---

## Phase Context

| Field | Value |
|-------|-------|
| PHASE_ID | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| PROJECT_BRANCH | `main` |
| ARCH_GATE_BRANCH | `arch/02/runtime-factory-gate` |
| Prior Phase | 01_PHASE_BASELINE_AND_GOVERNANCE ✅ PASS |

---

## ⚠️ Workflow Issue Identified and Resolved

### Issue: Developer/Tester Test Ownership Ambiguity

**Discovered:** During Developer Step B execution  
**Severity:** Medium  
**Status:** Resolved with process fix

**Problem:**
- Developer task said "Deliverable: Working `runtime_factory.py` with tests"
- Developer wrote `tests/test_runtime_factory.py` and `tests/test_message_contract.py`
- Tester task specifies `tests/application/test_runtime_factory.py` and `tests/application/test_message_contract.py`
- Result: Overlapping scope, duplicate test risk

**Root Cause:** Developer task template lacked explicit test ownership boundary statement.

**Immediate Fix (Phase 02):**
- Developer to choose: Move tests to `tests/application/` OR remove and let Tester own
- Documented in: `.ayder/PM_to_developer_fix_test_issues.md`

**Process Fix (Future Phases):**
All developer tasks now include:
> **Test Ownership Boundary:** Developer writes basic unit tests only. Acceptance-criteria and integration tests are owned by Tester team. Review `docs/PROJECT/tester/NN_PHASE.md` to avoid overlap.

---

## Workflow Progress Tracker

### Phase 01 Status: CLOSED ✅

See archive: `docs/PROJECT/PM_WORKFLOW_PHASE01_ARCHIVE.md` (if needed)

**Phase 01 merged to `main` at:** `d67b11f`

---

### Phase 02 Status: IN PROGRESS

Per `docs/REFACTOR/PROJECT_MANAGER_PROMPT.md`:

#### Step A — Architect Kickoff Assignment ✅ COMPLETE

**Architect Report:** `.ayder/architect_to_PM_phase02.pm`

| Checkpoint | Status |
|------------|--------|
| `PHASE_ID` assigned | ✅ |
| `PHASE_DOC` located | ✅ |
| Prior phase PASS verified | ✅ Phase 01 decision doc exists |
| Gate branch exists | ✅ `arch/02/runtime-factory-gate` created |

**Artifacts Produced:**
| Artifact | Location | Status |
|----------|----------|--------|
| Architecture Design | `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md` | ✅ Complete |
| Risk Register | `docs/PROJECT/architect/02_PHASE/02_RISK_REGISTER.md` | ✅ Complete |
| Kickoff Task Doc | `docs/PROJECT/architect/02_PHASE.md` | ✅ Complete |

**Validation Commands:**
```bash
uv run poe lint      # PASS
uv run poe typecheck # PASS
uv run poe test      # PASS (733 passed, 5 skipped)
```

---

#### Step B — Developer Assignment 🔄 IN PROGRESS (Issue Resolution)

**Developer Report:** `.ayder/developer_to_PM_phase02.md`

**Deliverables:**
| Task | Status | Evidence |
|------|--------|----------|
| DEV-02.1 Runtime Factory | ✅ | `application/runtime_factory.py` |
| DEV-02.2 Wire CLI | ✅ | `cli_runner.py` modified |
| DEV-02.3 Wire TUI | ✅ | `tui/app.py` modified |
| DEV-02.4 Message Contract | ✅ | `application/message_contract.py` |

**Gate Commands:**
```bash
uv run poe lint      # PASS
uv run poe typecheck # PASS
uv run poe test      # PASS (818 passed, 5 skipped — +21 from baseline)
```

**Issue Resolution:**
- ⚠️ Test ownership conflict identified (see "Workflow Issue" section above)
- 🔄 Awaiting developer response: Move tests OR remove tests
- 📍 Response sent: `.ayder/PM_to_developer_fix_test_issues.md`

**Control Check B:**
- [x] Developer branch exists: `dev/02/runtime-factory`
- [x] Developer confirmed DEV-* tasks in scope
- [x] Developer posted implementation plan
- [ ] ⚠️ Test location fix pending (issue resolution)

---

#### Step C — Tester Assignment 📋 READY (Blocked on B)

**Assignment Delivered:**
- `docs/PROJECT/tester/02_PHASE.md` — Tester task assignment

**Note:** Step C was planned to run parallel to Step B, but due to the test ownership issue, it is temporarily blocked pending developer resolution.

**Tester Tasks:**
- QA-02.1: Remove Obsolete Wiring Tests
- QA-02.2: Add Runtime Factory Tests (may extend/replace developer tests)
- QA-02.3: Add Message Contract Tests (may extend/replace developer tests)

**Next Actions:**
1. ✅ Await developer test fix (Option 1: move to `tests/application/` OR Option 2: remove)
2. ✅ PM completes Control Check B
3. ✅ Assign Tester Agent to `docs/PROJECT/tester/02_PHASE.md`

**Control Check C (Required before Step D):**
- [ ] Tester branch exists: `qa/02/factory-contract-tests`
- [ ] Tester posted remove→replace test migration mapping
- [ ] Tester listed acceptance-criteria tests for phase

---

#### Step D — Architect Gate Assignment ⏳ PENDING

**Trigger:** Steps B and C both complete (Control Checks B and C pass)

**Inputs for Step D:**
- Developer MR: `dev/02/runtime-factory` → `arch/02/runtime-factory-gate`
- Tester MR: `qa/02/factory-contract-tests` → `arch/02/runtime-factory-gate`

**Acceptance Criteria:**
- One shared runtime factory used by both CLI and TUI
- Message normalization prevents dict/object shape regressions
- Required tests for factory and message contract exist and pass
- Architect PASS with no open S1/S2 issues

---

## Branch/MR Matrix

| Role | Branch | Target | MR Status |
|------|--------|--------|-----------|
| Architect | `arch/02/runtime-factory-gate` | `main` | Created ✅ |
| Developer | `dev/02/runtime-factory` | `arch/02/runtime-factory-gate` | In Progress 🔄 |
| Tester | `qa/02/factory-contract-tests` | `arch/02/runtime-factory-gate` | Ready 📋 (Blocked) |
| Architect (final) | `arch/02/runtime-factory-gate` | `main` | Pending |

---

## Deliverables Summary

### Architect Deliverables (Complete)
| Artifact | Location | Status |
|----------|----------|--------|
| Architecture Design | `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md` | ✅ |
| Risk Register | `docs/PROJECT/architect/02_PHASE/02_RISK_REGISTER.md` | ✅ |
| Kickoff Task | `docs/PROJECT/architect/02_PHASE.md` | ✅ |

### Developer Deliverables (Complete, Test Fix Pending)
| Artifact | Location | Status |
|----------|----------|--------|
| Runtime Factory | `src/ayder_cli/application/runtime_factory.py` | ✅ |
| Message Contract | `src/ayder_cli/application/message_contract.py` | ✅ |
| CLI Wiring | `src/ayder_cli/cli_runner.py` | ✅ |
| TUI Wiring | `src/ayder_cli/tui/app.py` | ✅ |
| Memory Integration | `src/ayder_cli/memory.py` | ✅ |
| Chat Loop Integration | `src/ayder_cli/tui/chat_loop.py` | ✅ |
| Commands Integration | `src/ayder_cli/tui/commands.py` | ✅ |
| Developer Tests | `tests/test_*.py` | 🔄 Fix pending |

### Tester Deliverables (Pending)
| Artifact | Location | Status |
|----------|----------|--------|
| Test Migration Map | `docs/PROJECT/tester/02_PHASE/02_TEST_MIGRATION_MAPPING.md` | 📋 |
| Factory Tests | `tests/application/test_runtime_factory.py` | 📋 (may use dev tests) |
| Message Contract Tests | `tests/application/test_message_contract.py` | 📋 (may use dev tests) |

---

## Key Design Decisions (from Architect)

### Runtime Factory
- Module: `src/ayder_cli/application/runtime_factory.py`
- Container: `RuntimeComponents` dataclass with 9 fields
- Function: `create_runtime(*, config, project_root, model_name)`

### Message Contract
- Module: `src/ayder_cli/application/message_contract.py`
- Helpers: `get_message_role`, `get_message_content`, `get_message_tool_calls`, `to_message_dict`
- Rule: Handle both dict and object messages safely

### Migration Targets
- CLI: Replace `_build_services()` in `cli_runner.py`
- TUI: Replace inline init in `tui/app.py`
- Integration: `memory.py`, `tui/chat_loop.py`, `tui/commands.py`

---

## Next Actions for PM

1. ✅ **AWAITING:** Developer response on test fix (Option 1 or 2)
2. ✅ Complete Control Check B after fix confirmed
3. ✅ Assign Tester Agent → `docs/PROJECT/tester/02_PHASE.md`
4. 🔄 Steps B and C proceed in parallel (after unblock)
5. ⏳ Prepare Step D when B and C complete

---

## Process Improvement Log

| Phase | Issue | Resolution |
|-------|-------|------------|
| 02 | Developer/Tester test boundary ambiguity | Added explicit "Test Ownership Boundary" statement to all future developer tasks |

---

*Phase 02 of ayder-cli refactor program — Step A complete; Step B resolving issue; Step C ready*
