# Project Manager Workflow — Phase 02 Runtime Factory and Message Contract

**Program:** ayder-cli Refactor  
**Current Phase:** 02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT  
**Status:** REWORK_IN_PROGRESS — Awaiting Developer Item 3  
**Last Updated:** 2026-02-16

---

## Phase Context

| Field | Value |
|-------|-------|
| PHASE_ID | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| PROJECT_BRANCH | `main` |
| ARCH_GATE_BRANCH | `arch/02/runtime-factory-gate` |
| Gate Decision | **REWORK_REQUIRED** → In Progress |

---

## Rework Status Overview

| Item | Owner | Status | MR | Tests |
|------|-------|--------|-----|-------|
| 1 — Fix test paths | Tester | ✅ **COMPLETE** | `qa/02/factory-contract-tests-rework` → gate | 13 factory tests PASS |
| 2 — Relax assertion | Tester | ✅ **COMPLETE** | Same MR | 31 contract tests PASS |
| 3 — Fix `get_message_tool_calls()` | Developer | ⏳ **PENDING** | Awaiting report | Awaiting fix |

---

## Tester Rework Complete (Items 1-2)

**Tester Report:** `.ayder/tester_to_PM_phase02_rework.md`

### Fixes Applied

| Item | File | Change |
|------|------|--------|
| Item 1 | `test_runtime_factory.py` | Fixed Path comparison, factory patch target |
| Item 2 | `test_message_contract.py` | `is` → `==` assertion |

### Verification Results

```bash
# Acceptance Tests (44 total)
tests/application/test_runtime_factory.py      # 13 PASS ✅
tests/application/test_message_contract.py     # 31 PASS ✅

# Gate Commands
uv run poe lint        # PASS ✅
uv run poe typecheck   # PASS ✅
uv run poe test        # 798 PASS, 5 SKIP (Item 3 pending) ⚠️
```

### Notes
- Tester rework does NOT modify Developer implementation files
- Full test suite pass (862 total) requires Developer's Item 3 fix

---

## Developer Rework Pending (Item 3)

**Status:** ⏳ Awaiting Developer report

**Required:**
- Fix `get_message_tool_calls()` in `message_contract.py` to ALWAYS return list
- Handle dict with `tool_calls: None` → return `[]`
- Handle object without `tool_calls` attr → return `[]`
- Branch: `dev/02/runtime-factory-rework` → `arch/02/runtime-factory-gate`

**Expected Report:** `.ayder/developer_to_PM_phase02_rework.md`

---

## Workflow Status

### Rework Sequence

```
✅ QA Items 1-2 ────────────────────────────┐
                                           ├──→ Both MRs merged → Re-run Step D
⏳ DEV Item 3 (awaiting report) ────────────┘
```

### Current State

| Step | Status |
|------|--------|
| A | ✅ Complete |
| B | ✅ Complete → 🔄 Rework: QA DONE, DEV PENDING |
| C | ✅ Complete → 🔄 Rework: QA DONE, DEV PENDING |
| D | ⏸️ Paused — Awaiting Item 3 completion |

---

## Next Actions

### Immediate

1. ⏳ **AWAIT:** Developer report (`.ayder/developer_to_PM_phase02_rework.md`)
2. 🔄 **REVIEW:** Developer Item 3 fix when ready
3. ✅ **MERGE:** Both MRs to `arch/02/runtime-factory-gate`
4. 🏁 **RE-RUN:** Architect Step D gate

### After Developer Report

- Verify Developer branch: `dev/02/runtime-factory-rework`
- Verify `get_message_tool_calls()` always returns list
- Merge Developer MR to gate
- Request Architect re-review

---

## Success Criteria for Full Rework

- [x] QA MR merged: `qa/02/factory-contract-tests-rework` → gate
- [ ] DEV MR merged: `dev/02/runtime-factory-rework` → gate
- [ ] `uv run poe test` passes completely (862 tests)
- [ ] Architect re-review completed
- [ ] New decision: PASS

---

## Process Notes

### Tester Efficiency
Tester completed Items 1-2 quickly with:
- Clear path fixes (PosixPath vs str comparison)
- Clear assertion fix (`is` → `==`)
- Good coordination notes about Item 3 boundary

### Awaiting Developer
Tester is blocked on Developer's Item 3 fix. Once Developer submits:
- Both MRs can be merged
- Full test suite should pass
- Gate can be re-run

---

*Phase 02 of ayder-cli refactor program — Rework 2/3 complete — Awaiting Developer Item 3*
