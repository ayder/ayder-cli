# Project Manager Workflow — Phase 02 Runtime Factory and Message Contract

**Program:** ayder-cli Refactor  
**Current Phase:** 02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT  
**Status:** REWORK_REQUIRED  
**Last Updated:** 2026-02-16

---

## Phase Context

| Field | Value |
|-------|-------|
| PHASE_ID | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| PROJECT_BRANCH | `main` |
| ARCH_GATE_BRANCH | `arch/02/runtime-factory-gate` |
| Gate Decision | **REWORK_REQUIRED** |

---

## Workflow Status: REWORK_REQUIRED

Per Architect Gate Report (`.ayder/architect_to_PM_phase_02_GATE.md`):

### Gate Outcome
- **Decision:** **REWORK_REQUIRED** (S2 severity)
- **Blocker:** Test suite failures
- **Merge to main:** BLOCKED

### Gate Command Results
```bash
uv run poe lint      # PASS
uv run poe typecheck # PASS
uv run poe test      # FAIL
```

Failure breakdown:
- Developer unit tests: PASS (21 tests)
- Tester acceptance tests: FAIL (5 failed, 39 passed)

### Rework Items (3 S2 Issues)

| Item | Owner | Description | Status |
|------|-------|-------------|--------|
| 1 | Tester | Fix test path and patch assumptions | 📋 Ready |
| 2 | Tester | Relax `to_message_dict` dict passthrough assertion | 📋 Ready |
| 3 | Developer | Harden `get_message_tool_calls()` to always return list | 📋 Ready |

---

## Rework Workflow

### Current State

| Step | Previous Status | Current Action |
|------|-----------------|----------------|
| A | ✅ Complete | — |
| B | ✅ Complete | **REWORK** in progress |
| C | ✅ Complete | **REWORK** in progress |
| D | ❌ REWORK_REQUIRED | Await rework completion |

### Rework Branches

| Role | Rework Branch | Target |
|------|---------------|--------|
| Developer | `dev/02/runtime-factory-rework` | `arch/02/runtime-factory-gate` |
| Tester | `qa/02/factory-contract-tests-rework` | `arch/02/runtime-factory-gate` |

### Sequence

1. **Developer** implements Item 3 in `dev/02/runtime-factory-rework`
2. **Tester** implements Items 1-2 in `qa/02/factory-contract-tests-rework`
3. **Both** open MRs to `arch/02/runtime-factory-gate`
4. **Architect** reviews and merges both MRs
5. **Architect** re-runs gate commands
6. **Architect** issues new decision (PASS or REWORK_REQUIRED)

---

## Rework Tasks

### Developer Rework (Item 3)

**Task Doc:** `docs/PROJECT/developer/02_PHASE_REWORK.md`

**Summary:**
Fix `get_message_tool_calls()` in `message_contract.py` to ALWAYS return a list.

```python
def get_message_tool_calls(message: dict | object) -> list:
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls")
        return tool_calls if tool_calls is not None else []
    return getattr(message, "tool_calls", [])
```

### Tester Rework (Items 1-2)

**Task Doc:** `docs/PROJECT/tester/02_PHASE_REWORK.md`

**Summary:**
1. Fix import paths and patch targets in acceptance tests
2. Change `test_to_message_dict_from_dict` from `is` to `==` assertion

---

## Deliverables Tracking

### Original Deliverables (from Steps B and C)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Runtime Factory | ✅ Implemented | Needs no changes |
| Message Contract | ✅ Implemented | Needs Item 3 fix |
| CLI/TUI Wiring | ✅ Implemented | Needs no changes |
| Dev Unit Tests | ✅ Passing | Needs no changes |
| Tester Acceptance Tests | ❌ Failing | Needs Items 1-2 fixes |

### Rework Deliverables

| Deliverable | Owner | Branch |
|-------------|-------|--------|
| `get_message_tool_calls()` fix | Developer | `dev/02/runtime-factory-rework` |
| Test path fixes | Tester | `qa/02/factory-contract-tests-rework` |
| Assertion relaxation | Tester | `qa/02/factory-contract-tests-rework` |

---

## Success Criteria for Rework

- [ ] Developer MR merged: `dev/02/runtime-factory-rework` → `arch/02/runtime-factory-gate`
- [ ] Tester MR merged: `qa/02/factory-contract-tests-rework` → `arch/02/runtime-factory-gate`
- [ ] `uv run poe test` passes completely (862 tests)
- [ ] Architect re-review completed
- [ ] New decision: PASS

---

## Next Actions for PM

1. ✅ **ISSUED:** Rework tasks to Developer and Tester
2. 🔄 **MONITOR:** Progress on both rework branches
3. ⏳ **AWAIT:** Both MRs ready for Architect review
4. ⏳ **SCHEDULE:** Step D re-run (Architect Gate)

---

## Process Note

This is the first rework cycle in the program. The issue was identified at gate:
- Developer unit tests passed in isolation
- Tester acceptance tests had path/assertion mismatches with actual implementation
- Contract helper had edge case (non-list return) not caught by dev tests

**Lessons for future phases:**
- Consider integration test run before gate submission
- Ensure Tester tests are run against actual Developer implementation
- Define contract behavior for edge cases (None, missing attrs) more explicitly

---

*Phase 02 of ayder-cli refactor program — REWORK_REQUIRED — Awaiting Items 1-3 completion*
