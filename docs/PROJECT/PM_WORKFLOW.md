# Project Manager Workflow — ayder-cli Refactor Program

**Program:** ayder-cli Refactor  
**Status:** Phase 03 IN PROGRESS 🚀 — **IMPLEMENTATION (Step C)**  
**Last Updated:** 2026-02-16

---

## Phase Status Overview

| Phase | Status | Date | Decision |
|-------|--------|------|----------|
| 01 — Baseline and Governance | ✅ CLOSED | 2026-02-16 | PASS |
| 02 — Runtime Factory and Message Contract | ✅ CLOSED | 2026-02-16 | PASS |
| 03 — Service/UI Decoupling | 🚀 **IN PROGRESS** | 2026-02-16 | **IMPLEMENTATION** |
| 04 — Shared Async Engine | 🔒 Locked | — | — |
| 05 — Checkpoint and Execution Convergence | 🔒 Locked | — | — |
| 06 — Stabilization and Cleanup | 🔒 Locked | — | — |

---

## Phase 03: Service/UI Decoupling 🚀

### ✅ CURRENT STATUS: ARCHITECT APPROVED — DEVELOPER IMPLEMENTATION IN PROGRESS

**Update:** Architect has approved tests for implementation. Step C authorized.

**Test Commit:** `3fd0d7b [PHASE-03][QA][REWORK-2] Fix test issues per architect review`

**Developer Assignment:** `.ayder/PM_to_developer_phase03_implementation.md`

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

> **STATUS:** Tests APPROVED — Developer implementation in progress
>
> **CRITICAL RULES:**
> 1. **NEVER modify test files** — Report issues to architect
> 2. **Implement to make tests pass** — Tests define the contract  
> 3. **Pull tests first** — From `qa/03/service-ui-decoupling`
> 4. **Keep adapters outside `services/`** — Critical requirement
>
> **Assignment:** `.ayder/PM_to_developer_phase03_implementation.md`
>
> **Escalation:** Report test doubts to architect via `.ayder/developer_to_architect_phase03.md`

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

### Phase 03 Developer Documents
- `.ayder/NOTICE_developers_phase03.md` — Test-first process overview ✅
- `.ayder/PM_to_developer_phase03_implementation.md` — **Step C assignment** 🆕

---

## Next Actions

| Step | Action | Owner | Status |
|------|--------|-------|--------|
| 03-A | Architect Kickoff | Architect | ✅ **COMPLETE** |
| 03-B | Create test definitions | Tester | ✅ **COMPLETE** |
| 03-BR | Initial review | Architect | ✅ **COMPLETE** — REVISIONS_REQUIRED |
| 03-BR2 | First rework | Tester | ❌ **FAILED** — Uncommitted |
| 03-BR2-R2 | Second rework | Tester | ✅ **COMPLETE** — Commit `3fd0d7b` pushed |
| 03-BR3-FINAL | Final review | Architect | ✅ **APPROVED** |
| **03-C** | **Implement to pass tests** | **Developer** | 🚀 **IN PROGRESS** |
| 03-D | Architect Gate | Architect | 🔒 Locked |

---

## Phase 03 Step C — Developer Implementation

### Developer Assignment
**Document:** `.ayder/PM_to_developer_phase03_implementation.md`

### Critical Rules for Developers
1. **NEVER modify test files** — Report issues to architect
2. **Implement to make tests pass** — Tests define the contract
3. **Pull tests first** — From `qa/03/service-ui-decoupling`
4. **Keep adapters outside `services/`** — Critical requirement

### Implementation Targets

| Contract | Implementation | Test File |
|----------|---------------|-----------|
| 1 | Remove UI imports from `services/` | `test_boundary.py` |
| 2 | Create `InteractionSink` Protocol | `test_interaction_sink.py` |
| 2 | Create `ConfirmationPolicy` Protocol | `test_confirmation_policy.py` |
| 3 | Inject interfaces into `ToolExecutor` | `test_executor_integration.py` |
| 4 | Route LLM verbose through `InteractionSink` | `test_llm_verbose.py` |
| 5 | Create CLI/TUI adapters OUTSIDE `services/` | `test_service_ui_decoupling.py` |

### Escalation Path
| Issue | Contact | Method |
|-------|---------|--------|
| Tests seem wrong | Architect | `.ayder/developer_to_architect_phase03.md` |
| Scope ambiguous | PM | `.ayder/` messaging |
| Technical blocker | Architect | `.ayder/developer_to_architect_phase03.md` |

### Step C Completion Criteria
- [ ] All 6 test files pass
- [ ] `InteractionSink` and `ConfirmationPolicy` protocols implemented
- [ ] `ToolExecutor` uses injected interfaces (no direct UI calls)
- [ ] LLM provider routes verbose through `InteractionSink`
- [ ] CLI adapter created outside `services/` (`src/ayder_cli/ui/cli_adapter.py`)
- [ ] TUI adapter created outside `services/` (`src/ayder_cli/tui/adapter.py`)
- [ ] Lint passes: `uv run poe lint`
- [ ] Typecheck passes: `uv run poe typecheck`
- [ ] All tests pass: `uv run poe test`
- [ ] MR opened: `dev/03/service-ui-decoupling` → `arch/03/service-ui-gate`

---

## Phase 03 Rework History

### Second Rework Complete (BR2-R2) ✅

**Commit:** `3fd0d7b [PHASE-03][QA][REWORK-2] Fix test issues per architect review`

**Issues Fixed:**
1. ✅ Test baseline counts: 39 failed, 37 passed, 3 skipped
2. ✅ Private patching removed: `grep "_get_tool_permission"` returns empty
3. ✅ Protocol location: `services/interactions.py`
4. ✅ Adapter tests: 4 new placement tests added

**Files Changed:**
- `tests/services/test_executor_integration.py` — Removed private patching
- `tests/application/test_service_ui_decoupling.py` — Added 4 adapter tests

---

*Phase 03 of ayder-cli refactor program — **IMPLEMENTATION IN PROGRESS** — Developer Step C active*
