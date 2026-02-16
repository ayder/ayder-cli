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

#### Step B — Developer Assignment 📋 READY

**Prerequisites Met:**
- Gate branch exists ✅
- Architect kickoff complete ✅
- Phase doc available ✅

**Assignment Delivered:**
- `docs/PROJECT/developer/02_PHASE.md` — Developer task assignment

**Next Actions:**
1. Assign Developer Agent with:
   - `PHASE_ID`: `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`
   - `PHASE_DOC`: `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md`
   - `ARCH_GATE_BRANCH`: `arch/02/runtime-factory-gate`
   - `DEV_TASK_SCOPE`: `runtime-factory`

**Developer Tasks:**
- DEV-02.1: Shared Runtime Factory (`application/runtime_factory.py`)
- DEV-02.2: Wire CLI to Factory (`cli_runner.py`)
- DEV-02.3: Wire TUI to Factory (`tui/app.py`)
- DEV-02.4: Message Normalization Contract (`application/message_contract.py`)

**Control Check B (Required before Step C):**
- [ ] Developer branch exists: `dev/02/runtime-factory`
- [ ] Developer confirmed DEV-* tasks in scope
- [ ] Developer posted implementation plan and expected changed files

---

#### Step C — Tester Assignment 📋 READY

**Prerequisites Met:**
- Gate branch exists ✅
- Architect kickoff complete ✅
- Phase doc available ✅

**Assignment Delivered:**
- `docs/PROJECT/tester/02_PHASE.md` — Tester task assignment

**Next Actions:**
1. Assign Tester Agent (parallel to Developer) with:
   - `PHASE_ID`: `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`
   - `PHASE_DOC`: `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md`
   - `ARCH_GATE_BRANCH`: `arch/02/runtime-factory-gate`
   - `QA_TEST_SCOPE`: `factory-contract-tests`

**Tester Tasks:**
- QA-02.1: Remove Obsolete Wiring Tests
- QA-02.2: Add Runtime Factory Tests
- QA-02.3: Add Message Contract Tests

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
| Developer | `dev/02/runtime-factory` | `arch/02/runtime-factory-gate` | Pending |
| Tester | `qa/02/factory-contract-tests` | `arch/02/runtime-factory-gate` | Pending |
| Architect (final) | `arch/02/runtime-factory-gate` | `main` | Pending |

---

## Deliverables Summary

### Architect Deliverables (Complete)
| Artifact | Location | Status |
|----------|----------|--------|
| Architecture Design | `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md` | ✅ |
| Risk Register | `docs/PROJECT/architect/02_PHASE/02_RISK_REGISTER.md` | ✅ |
| Kickoff Task | `docs/PROJECT/architect/02_PHASE.md` | ✅ |

### Developer Deliverables (Pending)
| Artifact | Location | Status |
|----------|----------|--------|
| Runtime Factory | `src/ayder_cli/application/runtime_factory.py` | 📋 |
| Message Contract | `src/ayder_cli/application/message_contract.py` | 📋 |
| CLI Wiring | `src/ayder_cli/cli_runner.py` | 📋 |
| TUI Wiring | `src/ayder_cli/tui/app.py` | 📋 |

### Tester Deliverables (Pending)
| Artifact | Location | Status |
|----------|----------|--------|
| Test Migration Map | `docs/PROJECT/tester/02_PHASE/02_TEST_MIGRATION_MAPPING.md` | 📋 |
| Factory Tests | `tests/application/test_runtime_factory.py` | 📋 |
| Message Contract Tests | `tests/application/test_message_contract.py` | 📋 |

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

1. **Assign Developer Agent** → `docs/PROJECT/developer/02_PHASE.md`
2. **Assign Tester Agent** (parallel) → `docs/PROJECT/tester/02_PHASE.md`
3. **Monitor Control Checks** B and C
4. **Prepare Step D** when B and C complete

---

*Phase 02 of ayder-cli refactor program — Step A complete; Steps B and C ready*
