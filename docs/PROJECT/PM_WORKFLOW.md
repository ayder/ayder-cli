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

## ⚠️ Workflow Issue Status: RESOLVED

### Issue: Developer/Tester Test Ownership Ambiguity

**Status:** ✅ **RESOLVED** — Both teams coordinated successfully

**Resolution:**
- Developer wrote tests at `tests/test_*.py`
- Tester wrote tests at `tests/application/test_*.py` (per their spec)
- **No conflict:** Tester's tests are comprehensive (44 tests vs developer's 21)
- **Architect decision:** Will review both test suites at gate and decide on consolidation

---

## Workflow Progress Tracker

### Phase 01 Status: CLOSED ✅

**Phase 01 merged to `main` at:** `d67b11f`

---

### Phase 02 Status: IN PROGRESS — Steps B and C COMPLETE

Per `docs/REFACTOR/PROJECT_MANAGER_PROMPT.md`:

#### Step A — Architect Kickoff Assignment ✅ COMPLETE

| Checkpoint | Status |
|------------|--------|
| Architecture Design | ✅ `02_ARCHITECTURE_DESIGN.md` |
| Risk Register | ✅ `02_RISK_REGISTER.md` |
| Validation | ✅ lint, typecheck, test PASS |

---

#### Step B — Developer Assignment ✅ COMPLETE

**Developer Report:** `.ayder/developer_to_PM_phase02.md`

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| DEV-02.1 Runtime Factory | ✅ | `application/runtime_factory.py` (9 components) |
| DEV-02.2 Wire CLI | ✅ | `cli_runner.py` uses factory |
| DEV-02.3 Wire TUI | ✅ | `tui/app.py` uses factory |
| DEV-02.4 Message Contract | ✅ | `application/message_contract.py` + integrations |
| Developer Tests | ✅ | 21 tests added |

**Gate Commands:**
```bash
uv run poe lint      # PASS
uv run poe typecheck # PASS
uv run poe test      # PASS (818 passed, 5 skipped)
```

**Control Check B:** ✅ ALL PASS
- [x] Developer branch exists: `dev/02/runtime-factory`
- [x] Developer confirmed DEV-* tasks in scope
- [x] Developer posted implementation plan
- [x] No scope drift

---

#### Step C — Tester Assignment ✅ COMPLETE

**Tester Report:** `.ayder/tester_to_PM_phase02.md` (in `qa/02/factory-contract-tests`)

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| QA-02.1 Obsolete Tests | ✅ | Identified 4 tests, mapped replacements |
| QA-02.2 Factory Tests | ✅ | 13 tests in `tests/application/test_runtime_factory.py` |
| QA-02.3 Message Contract Tests | ✅ | 31 tests in `tests/application/test_message_contract.py` |
| Test Migration Map | ✅ | `02_TEST_MIGRATION_MAPPING.md` |

**Gate Commands:**
```bash
uv run poe lint      # PASS
uv run poe test      # PASS (733 passed, 49 skipped)
```

*Note: 49 skipped includes 44 new tests that will activate when DEV modules present*

**Control Check C:** ✅ ALL PASS
- [x] Tester branch exists: `qa/02/factory-contract-tests`
- [x] Tester posted remove→replace test migration mapping
- [x] Tester listed acceptance-criteria tests for phase

---

#### Step D — Architect Gate Assignment 📋 READY

**Trigger:** Steps B and C both complete ✅

**Inputs for Architect Gate:**

| Input | Value |
|-------|-------|
| `PHASE_ID` | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` |
| `ARCH_GATE_BRANCH` | `arch/02/runtime-factory-gate` |
| Developer MR | `dev/02/runtime-factory` → `arch/02/runtime-factory-gate` |
| Tester MR | `qa/02/factory-contract-tests` → `arch/02/runtime-factory-gate` |

**Acceptance Criteria:**
- [ ] One shared runtime factory used by both CLI and TUI
- [ ] Message normalization prevents dict/object shape regressions
- [ ] Required tests for factory and message contract exist and pass
- [ ] Architect PASS with no open S1/S2 issues

**Architect Tasks (Step D):**
1. **ARC-02.1** — Architecture Review
   - Verify duplicated composition roots removed/reduced
   - Confirm factory is single source of dependency assembly
2. **ARC-02.2** — Command Gate
   - Run `lint`, `typecheck`, `test`
3. **ARC-02.3** — Acceptance Review
   - Validate test migration mapping
   - Review both test suites (developer + tester)
   - Decide on test consolidation if needed

**Control Check D (Phase Closure Gate):**
- [ ] Architect reviewed all MRs
- [ ] Architect ran required commands
- [ ] Architect published PASS or REWORK_REQUIRED decision

---

## Branch/MR Matrix

| Role | Branch | Target | MR Status |
|------|--------|--------|-----------|
| Architect | `arch/02/runtime-factory-gate` | `main` | Created ✅ |
| Developer | `dev/02/runtime-factory` | `arch/02/runtime-factory-gate` | Ready ✅ |
| Tester | `qa/02/factory-contract-tests` | `arch/02/runtime-factory-gate` | Ready ✅ |
| Architect (final) | `arch/02/runtime-factory-gate` | `main` | Pending |

---

## Deliverables Summary

### Developer Deliverables
| Artifact | Location | Tests |
|----------|----------|-------|
| Runtime Factory | `src/ayder_cli/application/runtime_factory.py` | `tests/test_runtime_factory.py` (21) |
| Message Contract | `src/ayder_cli/application/message_contract.py` | `tests/test_message_contract.py` |
| CLI Wiring | `src/ayder_cli/cli_runner.py` | Updated |
| TUI Wiring | `src/ayder_cli/tui/app.py` | Updated |
| Memory Integration | `src/ayder_cli/memory.py` | Uses contract |
| Chat Loop Integration | `src/ayder_cli/tui/chat_loop.py` | Uses contract |
| Commands Integration | `src/ayder_cli/tui/commands.py` | Uses contract |

### Tester Deliverables
| Artifact | Location | Count |
|----------|----------|-------|
| Test Migration Map | `docs/PROJECT/tester/02_PHASE/02_TEST_MIGRATION_MAPPING.md` | — |
| Factory Tests | `tests/application/test_runtime_factory.py` | 13 tests |
| Message Contract Tests | `tests/application/test_message_contract.py` | 31 tests |

**Total New Tests:** 65 (21 dev + 44 tester)

---

## Test Migration Summary

| Action | Count | Details |
|--------|-------|---------|
| Tests to Update | 4 | `TestBuildServices::*` (obsolete) |
| Tests Added (Dev) | 21 | Basic unit tests |
| Tests Added (QA) | 44 | Comprehensive acceptance tests |
| **Net Change** | **+61** | Significant coverage increase |

---

## Next Actions for PM

1. ✅ **ASSIGN ARCHITECT GATE AGENT** for Step D
2. Provide: `docs/PROJECT/architect/02_PHASE_GATE.md` (create if needed)
3. Inputs: Developer MR + Tester MR → `arch/02/runtime-factory-gate`
4. Monitor Control Check D for PASS/REWORK_REQUIRED

---

## Key Design Decisions (Validated)

### Runtime Factory
- ✅ Module: `src/ayder_cli/application/runtime_factory.py`
- ✅ Container: `RuntimeComponents` (9 fields)
- ✅ Function: `create_runtime(*, config, project_root, model_name)`
- ✅ CLI: `_build_services()` delegates to factory
- ✅ TUI: `AyderApp.__init__()` uses factory

### Message Contract
- ✅ Module: `src/ayder_cli/application/message_contract.py`
- ✅ Helpers: `get_message_role`, `get_message_content`, `get_message_tool_calls`, `to_message_dict`
- ✅ Integration: `memory.py`, `tui/chat_loop.py`, `tui/commands.py`
- ✅ Rule: Handle both dict and object messages safely

---

## Process Improvement Log

| Phase | Issue | Resolution |
|-------|-------|------------|
| 02 | Developer/Tester test boundary ambiguity | Both teams delivered; Architect will consolidate at gate |

---

*Phase 02 of ayder-cli refactor program — Steps A, B, C complete; Ready for Step D (Architect Gate)*
