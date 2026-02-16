# Project Manager Workflow — ayder-cli Refactor Program

**Program:** ayder-cli Refactor  
**Status:** Phase 03 IN PROGRESS 🚨 — **TEST-FIRST DEVELOPMENT (SECOND REWORK)**  
**Last Updated:** 2026-02-16

---

## Phase Status Overview

| Phase | Status | Date | Decision |
|-------|--------|------|----------|
| 01 — Baseline and Governance | ✅ CLOSED | 2026-02-16 | PASS |
| 02 — Runtime Factory and Message Contract | ✅ CLOSED | 2026-02-16 | PASS |
| 03 — Service/UI Decoupling | 🚨 **IN REWORK** | 2026-02-16 | **SECOND REWORK REQUIRED** |
| 04 — Shared Async Engine | 🔒 Locked | — | — |
| 05 — Checkpoint and Execution Convergence | 🔒 Locked | — | — |
| 06 — Stabilization and Cleanup | 🔒 Locked | — | — |

---

## Phase 03: Service/UI Decoupling 🚨

### ⚠️ CURRENT STATUS: SECOND REWORK REQUIRED

**Issue:** Architect re-review found that claimed fixes were NOT actually committed to the branch.

**Action Required:** Tester must ACTUALLY commit and push all 4 fixes to `qa/03/service-ui-decoupling`.

### Process Change: Test-First Development

**This phase uses a TEST-FIRST approach:**

1. **Testers create tests FIRST** in branch `qa/03/service-ui-decoupling`
2. Tests define the expected interface contracts
3. **Developers pull tests** from test branch before implementing
4. Developers implement to make tests pass

### Branch Strategy

| Branch | Purpose | Owner |
|--------|---------|-------|
| `arch/03/service-ui-gate` | Architect gate branch | Architect |
| `qa/03/service-ui-decoupling` | **Test definitions** | Tester |
| `dev/03/service-ui-decoupling` | Implementation | Developer |

### 📢 Notice to Developers

> **STATUS:** Tests NOT READY — Second rework in progress
>
> Developer handoff is **BLOCKED** pending actual commits from tester.

---

## Phase 02: CLOSED ✅

### Final Architect Report

**Report:** `.ayder/architect_to_PM_phase_02_GATE.md`  
**Decision:** **PASS**

---

## Phase 03 Deliverables (Planned)

| Component | Description | Test Location |
|-----------|-------------|---------------|
| Service Layer Interface | Abstract service contracts | `tests/services/test_interfaces.py` |
| UI Adapter Pattern | UI-side adapters for services | `tests/ui/test_adapters.py` |
| Dependency Injection | Service injection mechanism | `tests/application/test_di.py` |
| Event Bus | Decoupled communication | `tests/application/test_event_bus.py` |

---

## Artifacts Summary

### Phase 03 Design Documents
- `docs/PROJECT/architect/03_PHASE/03_ARCHITECTURE_DESIGN.md` ✅
- `docs/PROJECT/architect/03_PHASE/03_RISK_REGISTER.md` ✅
- `.ayder/architect_to_teams_phase03.md` (Interface contracts) ✅

### Phase 03 Review Documents
- `.ayder/architect_to_PM_phase03_review.md` — Initial review (REVISIONS_REQUIRED)
- `.ayder/architect_to_PM_phase03_rereview.md` — Re-review (ADDITIONAL_REVISIONS)
- `.ayder/tester_to_PM_phase03_rework.md` — First rework report (unverified)

---

## Next Actions

| Step | Action | Owner | Status |
|------|--------|-------|--------|
| 03-A | Architect Kickoff | Architect | ✅ **COMPLETE** |
| 03-B | Create test definitions | Tester | ✅ **COMPLETE** |
| 03-BR | Review test coverage | Architect | ✅ **COMPLETE** — REVISIONS_REQUIRED |
| 03-BR2 | First rework attempt | Tester | ❌ **FAILED** — Uncommitted changes |
| **03-BR2-R2** | **Second rework — ACTUAL commits** | **Tester** | 🚨 **URGENT** |
| 03-BR3 | Re-review after ACTUAL fixes | Architect | ⏳ **Waiting** |
| 03-C | Implement to pass tests | Developer | 🔒 **Blocked** |
| 03-D | Architect Gate | Architect | 🔒 Locked |

---

## Phase 03 Rework Tracking

### 🚨 SECOND REWORK: Uncommitted Changes (Step BR2-R2)

**Status:** CRITICAL — Previous rework report claimed fixes complete, but files were not committed

**Architect Finding (from `.ayder/architect_to_PM_phase03_rereview.md`):**

| # | Issue | Claimed Status | ACTUAL Status |
|---|-------|----------------|---------------|
| 1 | Test baseline counts | ✅ "Fixed to 39f/37p/3s" | ❌ Still shows 42/28/5 in doc |
| 2 | Private patching | ✅ "Removed" | ❌ Still at line ~242 in executor tests |
| 3 | Protocol location | ✅ "Fixed to interactions.py" | ❌ Still shows __init__.py in doc |
| 4 | Adapter placement tests | ✅ "Added 4 tests" | ❌ NOT FOUND in test file |

**Evidence:**
```bash
$ grep "_get_tool_permission" tests/services/test_executor_integration.py
# Still finds matches — NOT REMOVED

$ grep "test_cli_adapter_outside_services" tests/application/test_service_ui_decoupling.py
# No matches — NOT ADDED
```

### Root Cause
Tester wrote a rework report claiming fixes were done, but:
- Changes may be local/unstaged
- Changes may be staged but not committed
- Changes may be committed but not pushed
- Changes may be in wrong branch

### Required Actions (ACTUALLY DO THEM)

1. **Edit files** — Make the 4 required changes
2. **Stage changes** — `git add -A`
3. **Commit changes** — `git commit -m "[PHASE-03][QA][REWORK-2] ..."`
4. **Push changes** — `git push origin qa/03/service-ui-decoupling`
5. **Verify changes** — Use `grep` and `git log` to confirm
6. **Report completion** — Create `.ayder/tester_to_PM_phase03_rework2.md` WITH evidence

### Assignment
- **Document:** `.ayder/PM_to_tester_phase03_rework2.md`
- **Urgency:** CRITICAL (Phase blocked)
- **Target:** Complete within 12 hours
- **Verification:** Architect will grep and check actual files this time

---

*Phase 03 of ayder-cli refactor program — **SECOND REWORK REQUIRED** — ACTUAL commits needed*
