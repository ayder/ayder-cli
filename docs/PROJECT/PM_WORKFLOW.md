# Project Manager Workflow — Phase 02 Runtime Factory and Message Contract

**Program:** ayder-cli Refactor  
**Current Phase:** 02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT  
**Status:** REWORK_COMPLETE — Ready for Architect Re-Gate  
**Last Updated:** 2026-02-16

---

## Phase Context

| Field | Value |
|-------|-------|
| PHASE_ID | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| PROJECT_BRANCH | `main` |
| ARCH_GATE_BRANCH | `arch/02/runtime-factory-gate` |
| Gate Decision | **REWORK_REQUIRED** → **REWORK_COMPLETE** |

---

## Rework Status: ALL ITEMS COMPLETE ✅

### Rework Completion Summary

| Item | Owner | Status | Result |
|------|-------|--------|--------|
| 1 — Fix test paths | Tester | ✅ COMPLETE | MR ready |
| 2 — Relax assertion | Tester | ✅ COMPLETE | MR ready |
| 3 — Fix `get_message_tool_calls()` | Developer | ✅ COMPLETE | MR ready |

### Rework Reports

- **Tester:** `.ayder/tester_to_PM_phase02_rework.md` — Items 1-2 complete, 44/44 tests pass
- **Developer:** `.ayder/developer_to_PM_phase02_rework.md` — Item 3 complete, edge cases covered

---

## Rework Details

### Tester Items 1-2 (Complete)

**Fixes Applied:**
| Item | File | Change |
|------|------|--------|
| Item 1 | `test_runtime_factory.py` | Path comparison, factory patch target |
| Item 2 | `test_message_contract.py` | `is` → `==` assertion |

**Verification:**
```bash
tests/application/test_runtime_factory.py      # 13 PASS ✅
tests/application/test_message_contract.py     # 31 PASS ✅
```

### Developer Item 3 (Complete)

**Fix Applied:**
```python
# Before
return message.get("tool_calls") or []
return getattr(message, "tool_calls", None) or []

# After  
tool_calls = message.get("tool_calls")
return tool_calls if isinstance(tool_calls, list) else []
tool_calls = getattr(message, "tool_calls", None)
return tool_calls if isinstance(tool_calls, list) else []
```

**Edge Cases:** 7/7 covered (dict, object, Mock, None, missing)

---

## Ready for Architect Re-Gate

### Merge Status

| MR | Source | Target | Status |
|----|--------|--------|--------|
| Tester rework | `qa/02/factory-contract-tests-rework` | `arch/02/runtime-factory-gate` | Ready to merge ✅ |
| Developer rework | `dev/02/runtime-factory-rework` | `arch/02/runtime-factory-gate` | Ready to merge ✅ |

### Sequence

```
✅ QA Items 1-2 ───────┐
                       ├──→ Merge both MRs → Re-run Step D → PASS → Merge to main
✅ DEV Item 3 ─────────┘
```

---

## Next Steps

### Immediate (PM Actions)

1. ✅ **CONFIRM:** Both rework reports reviewed and accepted
2. 🔄 **MERGE:** Both MRs to `arch/02/runtime-factory-gate`
3. 📋 **ASSIGN:** Architect for Step D re-gate

### Architect Step D Re-Gate

**Assignment:** `docs/PROJECT/architect/02_PHASE_GATE_RERUN.md`

**Tasks:**
- [ ] Merge `qa/02/factory-contract-tests-rework` to gate
- [ ] Merge `dev/02/runtime-factory-rework` to gate
- [ ] Run gate commands: `lint`, `typecheck`, `test`
- [ ] Expected: 862 tests pass
- [ ] Issue PASS decision
- [ ] Merge gate to `main`

---

## Success Criteria for Phase 02 Closure

- [x] QA Items 1-2 complete
- [x] DEV Item 3 complete
- [ ] Both MRs merged to gate
- [ ] Architect re-gate complete
- [ ] `uv run poe test` passes (862 tests)
- [ ] Decision: PASS
- [ ] Merged to `main`

---

## Deliverables Tracking

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 01 | Baseline | ✅ CLOSED |
| 02 | Runtime Factory | 🔄 REWORK_COMPLETE → Awaiting re-gate |
| 03 | Service/UI Decoupling | 🔒 Locked (pending Phase 02) |

---

*Phase 02 of ayder-cli refactor program — Rework 3/3 complete — Ready for Architect re-gate*
