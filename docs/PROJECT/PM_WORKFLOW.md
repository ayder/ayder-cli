# Project Manager Workflow — Phase 01 Baseline and Governance

**Program:** ayder-cli Refactor  
**Current Phase:** 01_PHASE_BASELINE_AND_GOVERNANCE  
**Last Updated:** 2026-02-16

---

## Phase Context

| Field | Value |
|-------|-------|
| PHASE_ID | `01_PHASE_BASELINE_AND_GOVERNANCE` |
| PROJECT_BRANCH | `main` |
| ARCH_GATE_BRANCH | `arch/01/baseline-gate` |

## Documentation Source

All REFACTOR documentation is **available locally** in `arch/01/baseline-gate`:
- `docs/REFACTOR/` — Team prompts and workflow docs
- `docs/REFACTOR/PHASES/` — Phase specifications (00-06)

> These docs were sourced from the `logging` branch and copied to this branch for developer/tester access.

---

## Workflow Progress Tracker

Per `docs/REFACTOR/PROJECT_MANAGER_PROMPT.md`:

### Step A — Architect Kickoff Assignment ✅ COMPLETE

| Checkpoint | Status |
|------------|--------|
| Architect gate branch exists and is refreshed from project branch | ✅ `arch/01/baseline-gate` created from `main` @ `3c659d2` |
| Architect kickoff note exists (scope, acceptance checklist, risks) | ✅ `.ayder/architect_to_PM_phase01.md` |
| Architect confirms prior phase dependency is PASS | ✅ N/A (Phase 01 is first phase) |
| All REFACTOR docs committed to gate branch | ✅ Commit `8f81b37` |

**Artifacts Produced:**
- `docs/PROJECT/architect/01_PHASE.md` — Architect task assignment
- `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md` — Flow analysis
- `docs/PROJECT/architect/01_PHASE/01_SCAFFOLDING_PLAN.md` — Target structure
- `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md` — Risk analysis
- `src/ayder_cli/application/__init__.py` — Scaffold placeholder
- `src/ayder_cli/application/README.md` — Scaffold documentation

**Gate Commands Status:**
- `uv run poe lint` ✅ PASS
- `uv run poe typecheck` ✅ PASS  
- `uv run poe test` ✅ PASS (733 passed, 5 skipped)

---

### Step B — Developer Assignment ✅ COMPLETE

**Developer Report:** `.ayder/developer_to_PM_phase01.md`

**Deliverables:**
| Task | Status | Evidence |
|------|--------|----------|
| DEV-01.1 Baseline Inventory | ✅ | `docs/PROJECT/developer/01_PHASE/01_DEV_BASELINE_NOTES.md` |
| DEV-01.2 Refactor Scaffolding | ✅ | `src/ayder_cli/application/` verified |
| DEV-01.3 Risk Register | ✅ | `docs/PROJECT/developer/01_PHASE/01_DEV_RISK_ASSESSMENT.md` |

**Gate Commands:**
- `uv run poe lint` ✅ PASS
- `uv run poe typecheck` ✅ PASS
- `uv run poe test` ✅ PASS (797 passed, 5 skipped)

**Control Check B:** ✅ ALL PASS
- [x] Developer branch exists: `dev/01/baseline-inventory`
- [x] Developer confirmed DEV-* tasks in scope
- [x] Developer posted implementation plan and expected changed files
- [x] No scope drift — documentation and scaffolding only

**Branch:** `dev/01/baseline-inventory` → `arch/01/baseline-gate`

---

### Step C — Tester Assignment ✅ COMPLETE

**Tester Report:** `.ayder/tester_to_PM_phase01.md`

**Deliverables:**
| Task | Status | Evidence |
|------|--------|----------|
| QA-01.1 Test Inventory | ✅ | `docs/PROJECT/tester/01_PHASE/01_TEST_INVENTORY.md` |
| QA-01.2 Obsolete Test Candidates | ✅ | `docs/PROJECT/tester/01_PHASE/01_OBSOLETE_TEST_CANDIDATES.md` |
| QA-01.3 Characterization Tests | ✅ | `docs/PROJECT/tester/01_PHASE/01_CHARACTERIZATION_TESTS.md` |

**Gate Commands:**
- `uv run poe lint` ✅ PASS
- `uv run poe test` ✅ PASS (733 passed, 5 skipped)

**Control Check C:** ✅ ALL PASS
- [x] Tester branch exists: `qa/01/test-inventory`
- [x] Tester posted remove→replace test migration mapping
- [x] Tester listed acceptance-criteria tests for phase

**Branch:** `qa/01/test-inventory` → `arch/01/baseline-gate`

**Key Findings:**
- 211 tests inventoried in impacted areas
- 20+ obsolete test candidates identified (pending Architect approval)
- All baseline characterization tests passing

---

### Step D — Architect Gate Assignment 📋 READY

**Prerequisites Met:**
- Steps B and C complete ✅
- Control Checks B and C pass ✅

**Inputs for Architect Gate:**

| Input | Value |
|-------|-------|
| `PHASE_ID` | `01_PHASE_BASELINE_AND_GOVERNANCE` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md` |
| `PROJECT_BRANCH` | `main` |
| `ARCH_GATE_BRANCH` | `arch/01/baseline-gate` |
| Developer MR | `dev/01/baseline-inventory` → `arch/01/baseline-gate` |
| Tester MR | `qa/01/test-inventory` → `arch/01/baseline-gate` |

**Phase Acceptance Criteria:**
- [ ] Baseline inventory exists and is architect-approved
- [ ] Impacted test map exists with obsolete candidate list
- [ ] Required gate commands pass
- [ ] No intentional runtime behavior change introduced

**Architect Tasks (Step D):**

| Task | Description |
|------|-------------|
| ARC-01.1 | Baseline Review — Validate inventory completeness |
| ARC-01.2 | Command Gate — Run `lint`, `typecheck`, `test` |
| ARC-01.3 | Sign-off Decision — PASS or REWORK_REQUIRED |

**Control Check D (Phase Closure Gate):**
- [ ] Architect reviewed all MRs
- [ ] Architect ran required commands (`lint`, `typecheck`, `test`)
- [ ] Architect published PASS or REWORK_REQUIRED decision note

---

## Branch/MR Matrix

| Role | Branch | Target | MR Status |
|------|--------|--------|-----------|
| Architect | `arch/01/baseline-gate` | `main` | Created ✅ |
| Developer | `dev/01/baseline-inventory` | `arch/01/baseline-gate` | Ready for Review ✅ |
| Tester | `qa/01/test-inventory` | `arch/01/baseline-gate` | Ready for Review ✅ |
| Architect (final) | `arch/01/baseline-gate` | `main` | Pending gate decision |

---

## Required Artifacts Summary

| Artifact | Owner | Location | Status |
|----------|-------|----------|--------|
| Baseline inventory | Architect | `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md` | ✅ Complete |
| Scaffolding plan | Architect | `docs/PROJECT/architect/01_PHASE/01_SCAFFOLDING_PLAN.md` | ✅ Complete |
| Risk register | Architect | `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md` | ✅ Complete |
| Dev baseline notes | Developer | `docs/PROJECT/developer/01_PHASE/01_DEV_BASELINE_NOTES.md` | ✅ Complete |
| Dev risk assessment | Developer | `docs/PROJECT/developer/01_PHASE/01_DEV_RISK_ASSESSMENT.md` | ✅ Complete |
| Test inventory | Tester | `docs/PROJECT/tester/01_PHASE/01_TEST_INVENTORY.md` | ✅ Complete |
| Obsolete test candidates | Tester | `docs/PROJECT/tester/01_PHASE/01_OBSOLETE_TEST_CANDIDATES.md` | ✅ Complete |
| Characterization tests | Tester | `docs/PROJECT/tester/01_PHASE/01_CHARACTERIZATION_TESTS.md` | ✅ Complete |
| Architect decision | Architect | `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE_ARCHITECT_DECISION.md` | ⏳ Pending (Step D) |

---

## Escalation Rules

- If acceptance criteria interpretation is disputed → Escalate to Architect
- If team scope conflict persists → Issue PM clarification note, pause execution
- If any S1 issue is unresolved → Phase cannot close

---

## Next Actions for PM

1. **Assign Architect Gate Agent** with Step D inputs (above)
2. **Provide Architect Prompt** from `docs/REFACTOR/ARCHITECT_PROMPT.md`
3. **Monitor Control Check D** for PASS/REWORK_REQUIRED decision

---

## Done Definition (Program Level)

Phase 01 complete only when:
- [x] Assignment sequence was followed exactly (Steps A-D)
- [ ] Developer and Tester deliverables reviewed through Architect gate
- [ ] Architect issued PASS decision
- [ ] Gate branch merged to project branch (`main`)
- [ ] PM archived evidence and unlocked next phase

---

## Risk Summary

| Risk | Status | Owner |
|------|--------|-------|
| Async migration (CLI sync → async) | Identified | Phase 04 |
| Message shape divergence | Identified | Phase 02 |
| Test breakage during refactor | Mitigated | Tester inventory complete |
| Tool execution path divergence | Identified | Phase 04-05 |
| Checkpoint flow divergence | Identified | Phase 05 |

---

*Workflow tracker for Phase 01 of ayder-cli refactor program — Steps A, B, C complete; ready for Step D*
