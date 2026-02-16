# Project Manager Workflow — ayder-cli Refactor Program

**Program:** ayder-cli Refactor  
**Status:** Phase 03 IN PROGRESS 🚀 — **TEST-FIRST DEVELOPMENT**  
**Last Updated:** 2026-02-16

---

## Phase Status Overview

| Phase | Status | Date | Decision |
|-------|--------|------|----------|
| 01 — Baseline and Governance | ✅ CLOSED | 2026-02-16 | PASS |
| 02 — Runtime Factory and Message Contract | ✅ CLOSED | 2026-02-16 | PASS |
| 03 — Service/UI Decoupling | 🚀 **IN PROGRESS** | 2026-02-16 | **UNLOCKED** |
| 04 — Shared Async Engine | 🔒 Locked | — | — |
| 05 — Checkpoint and Execution Convergence | 🔒 Locked | — | — |
| 06 — Stabilization and Cleanup | 🔒 Locked | — | — |

---

## Phase 03: Service/UI Decoupling 🚀

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

> **TESTS ARE AVAILABLE IN:** `qa/03/service-ui-decoupling`
>
> Before writing implementation code:
> 1. Checkout or pull from `qa/03/service-ui-decoupling`
> 2. Review test files to understand expected interfaces
> 3. Implement against the test contracts
> 4. All tests must pass for gate acceptance

---

## Phase 02: CLOSED ✅

### Final Architect Report

**Report:** `.ayder/architect_to_PM_phase_02_GATE.md`  
**Decision:** **PASS**

### Actions Completed by Architect

| # | Action | Commit |
|---|--------|--------|
| 1 | Merged QA rework → gate | `dcd5ad4` |
| 2 | Merged DEV rework → gate | `c6fae63` |
| 3 | Ran gate commands | All PASS |
| 4 | Issued PASS decision | Updated decision note |
| 5 | Merged gate → `main` | Complete |

### Gate Command Results

```bash
uv run poe lint        # PASS ✅
uv run poe typecheck   # PASS ✅
uv run poe test        # PASS (798 passed, 5 skipped) ✅
```

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

### Phase 02 Decision Documents
- `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT_ARCHITECT_DECISION.md`

### Phase 03 Design Documents
- `docs/PROJECT/architect/03_PHASE/03_ARCHITECTURE_DESIGN.md` ✅
- `docs/PROJECT/architect/03_PHASE/03_RISK_REGISTER.md` ✅
- `.ayder/architect_to_teams_phase03.md` (Interface contracts) ✅

---

## Next Actions

| Step | Action | Owner | Status |
|------|--------|-------|--------|
| 03-A | Architect Kickoff | Architect | ✅ **COMPLETE** |
| 03-B | Create test definitions | Tester | ✅ **COMPLETE** |
| 03-BR | Review test coverage | Architect | ✅ **COMPLETE** — REVISIONS_REQUIRED |
| 03-BR2 | **Rework test issues** | **Tester** | 🔄 **IN REWORK** |
| 03-BR3 | Re-review after fixes | Architect | ⏳ **Waiting for tester** |
| 03-C | Implement to pass tests | Developer | 🔒 **Blocked** |
| 03-D | Architect Gate | Architect | 🔒 Locked |

---

## Phase 03 Rework Tracking

### Current Rework: Test Suite Corrections (Step BR2)

**Status:** Tester fixing issues identified in architect review  
**Blocker:** Step C (Developer implementation) on hold until resolved

#### Issues from Architect Review

| # | Issue | Severity | Fix Required |
|---|-------|----------|--------------|
| 1 | Test baseline mismatch (42f/28p/5s → 39f/35p/1s) | Critical | Update report counts |
| 2 | Private method patching `_get_tool_permission` | Critical | Use public behavior tests |
| 3 | Protocol location guidance conflict | Medium | Change to `services/interactions.py` |
| 4 | Adapter placement lacks enforcement | Medium | Add assertions outside `services/` |

#### Rework Assignment
- **Document:** `.ayder/PM_to_tester_phase03_rework.md`
- **Target:** Complete within 24 hours
- **Re-review:** Quick architect validation after fixes

---

*Phase 03 of ayder-cli refactor program — **IN REWORK** — Test-first development in progress*
