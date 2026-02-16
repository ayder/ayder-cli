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

### Step B — Developer Assignment 📋 READY

**Prerequisites Met:**
- Gate branch exists ✅
- Architect kickoff complete ✅
- Phase doc available ✅

**Assignment Delivered:**
- `docs/PROJECT/developer/01_PHASE.md` — Developer task assignment

**Next Actions:**
1. Assign Developer Agent with:
   - `PHASE_ID`: `01_PHASE_BASELINE_AND_GOVERNANCE`
   - `PHASE_DOC`: `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md`
   - `PROJECT_BRANCH`: `main`
   - `ARCH_GATE_BRANCH`: `arch/01/baseline-gate`
   - `DEV_TASK_SCOPE`: `baseline-inventory`

**Control Check B (Required before Step C):**
- [ ] Developer branch exists: `dev/01/baseline-inventory`
- [ ] Developer confirmed DEV-* tasks in scope
- [ ] Developer posted implementation plan and expected changed files

---

### Step C — Tester Assignment 📋 READY

**Prerequisites Met:**
- Gate branch exists ✅
- Architect kickoff complete ✅
- Phase doc available ✅

**Assignment Delivered:**
- `docs/PROJECT/tester/01_PHASE.md` — Tester task assignment

**Next Actions:**
1. Assign Tester Agent (parallel to Developer) with:
   - `PHASE_ID`: `01_PHASE_BASELINE_AND_GOVERNANCE`
   - `PHASE_DOC`: `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md`
   - `PROJECT_BRANCH`: `main`
   - `ARCH_GATE_BRANCH`: `arch/01/baseline-gate`
   - `QA_TEST_SCOPE`: `test-inventory`

**Control Check C (Required before Step D):**
- [ ] Tester branch exists: `qa/01/test-inventory`
- [ ] Tester posted remove→replace test migration mapping
- [ ] Tester listed acceptance-criteria tests for phase

---

### Step D — Architect Gate Assignment ⏳ PENDING

**Trigger:** Steps B and C both complete (Control Checks B and C pass)

**Inputs for Step D:**
- Developer MR list: TBD
- Tester MR list: TBD
- Phase acceptance checklist: See `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md`

**Control Check D (Phase Closure Gate):**
- [ ] Architect reviewed all MRs
- [ ] Architect ran required commands (`lint`, `typecheck`, `test`)
- [ ] Architect published PASS or REWORK_REQUIRED decision note

---

## Branch/MR Matrix

| Role | Branch | Target | MR Status |
|------|--------|--------|-----------|
| Architect | `arch/01/baseline-gate` | `main` | Created ✅ |
| Developer | `dev/01/baseline-inventory` | `arch/01/baseline-gate` | Pending |
| Tester | `qa/01/test-inventory` | `arch/01/baseline-gate` | Pending |
| Architect (final) | `arch/01/baseline-gate` | `main` | Pending gate decision |

---

## Required Artifacts Summary

| Artifact | Owner | Location | Status |
|----------|-------|----------|--------|
| Baseline inventory | Architect | `docs/PROJECT/architect/01_PHASE/01_BASELINE_INVENTORY.md` | ✅ Complete |
| Scaffolding plan | Architect | `docs/PROJECT/architect/01_PHASE/01_SCAFFOLDING_PLAN.md` | ✅ Complete |
| Risk register | Architect | `docs/PROJECT/architect/01_PHASE/01_RISK_REGISTER.md` | ✅ Complete |
| Dev baseline notes | Developer | `docs/PROJECT/developer/01_PHASE/01_DEV_BASELINE_NOTES.md` | 📋 Pending |
| Dev risk assessment | Developer | `docs/PROJECT/developer/01_PHASE/01_DEV_RISK_ASSESSMENT.md` | 📋 Pending |
| Test inventory | Tester | `docs/PROJECT/tester/01_PHASE/01_TEST_INVENTORY.md` | 📋 Pending |
| Obsolete test candidates | Tester | `docs/PROJECT/tester/01_PHASE/01_OBSOLETE_TEST_CANDIDATES.md` | 📋 Pending |
| Characterization tests | Tester | `docs/PROJECT/tester/01_PHASE/01_CHARACTERIZATION_TESTS.md` | 📋 Pending |
| Architect decision | Architect | `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE_ARCHITECT_DECISION.md` | ⏳ Future (Step D) |

---

## Escalation Rules

- If acceptance criteria interpretation is disputed → Escalate to Architect
- If team scope conflict persists → Issue PM clarification note, pause execution
- If any S1 issue is unresolved → Phase cannot close

---

## Next Actions for PM

1. **Assign Developer Agent** with task document `docs/PROJECT/developer/01_PHASE.md`
2. **Assign Tester Agent** with task document `docs/PROJECT/tester/01_PHASE.md`
3. **Monitor Control Checks B and C** for completion
4. **Prepare Step D assignment** when B and C complete

---

## Done Definition (Program Level)

Phase 01 complete only when:
- [x] Assignment sequence was followed exactly (Steps A-D)
- [ ] Developer and Tester deliverables reviewed through Architect gate
- [ ] Architect issued PASS decision
- [ ] Gate branch merged to project branch (`main`)
- [ ] PM archived evidence and unlocked next phase

---

*Workflow tracker for Phase 01 of ayder-cli refactor program*
