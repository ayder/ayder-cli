# Architect Gate Re-Run — Phase 02: Runtime Factory and Message Contract

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Architect Reviewer Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Step:** D Re-Run (After Rework Completion)

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` |
| `PROJECT_BRANCH` | `main` |
| `ARCH_GATE_BRANCH` | `arch/02/runtime-factory-gate` |
| `REWORK_STATUS` | ALL ITEMS COMPLETE (1-2: Tester, 3: Developer) |

---

## 2. Rework Context

### Original Gate Failure

First Step D gate failed with:
```bash
uv run poe test      # FAIL
```

- Developer unit tests: PASS (21 tests)
- Tester acceptance tests: FAIL (5 failed, 39 passed)

### Rework Completed

| Item | Owner | Issue | Fix |
|------|-------|-------|-----|
| 1 | Tester | Test path/patch misalignment | Fixed imports and patch targets |
| 2 | Tester | Strict `is` assertion | Changed to `==` |
| 3 | Developer | `get_message_tool_calls` non-list return | Added `isinstance(list)` guard |

### Rework Reports

- Tester: `.ayder/tester_to_PM_phase02_rework.md`
- Developer: `.ayder/developer_to_PM_phase02_rework.md`

---

## 3. Mission

Re-run Step D gate after rework completion. Merge both rework MRs, execute gate commands, and issue final PASS or REWORK_REQUIRED decision.

**Key Differences from First Gate:**
- Both rework MRs need to be merged first
- Expected outcome: Full test suite passes
- This should be the final gate for Phase 02

---

## 4. Pre-Flight Checklist

Before beginning re-gate, confirm:

- [ ] Rework Items 1-2 complete (Tester report exists)
- [ ] Rework Item 3 complete (Developer report exists)
- [ ] Tester MR ready: `qa/02/factory-contract-tests-rework`
- [ ] Developer MR ready: `dev/02/runtime-factory-rework`
- [ ] Both MRs target `arch/02/runtime-factory-gate`

If any check fails: STOP and request correction from PM.

---

## 5. Merge Rework MRs

### Step 1: Merge Tester Rework

```bash
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git merge qa/02/factory-contract-tests-rework
# Resolve conflicts if any (should be none)
git push origin arch/02/runtime-factory-gate
```

### Step 2: Merge Developer Rework

```bash
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git merge dev/02/runtime-factory-rework
# Resolve conflicts if any (should be none)
git push origin arch/02/runtime-factory-gate
```

### Merge Verification

Verify both merges:
```bash
git log --oneline -5
# Should show both merge commits
```

---

## 6. Gate Commands (Mandatory)

Run on `arch/02/runtime-factory-gate` after both merges:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

### Expected Results

| Command | Expected Result |
|---------|-----------------|
| `lint` | All checks passed |
| `typecheck` | Success, no issues |
| `test` | 862 passed, 5 skipped |

**Test Count Breakdown:**
- 797 baseline (Phase 01)
- +21 developer unit tests
- +44 tester acceptance tests
- = 862 total

### If Tests Fail

Document failures:
```bash
uv run poe test 2>&1 | tee test_failures.log
```

If any failures, decision is **REWORK_REQUIRED** with new rework items.

---

## 7. Acceptance Criteria Verification

Per `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md`:

| Criterion | Verification | Status |
|-----------|--------------|--------|
| One shared runtime factory used by both CLI and TUI | Review `cli_runner.py`, `tui/app.py` | [ ] |
| Message normalization prevents dict/object regressions | Review `message_contract.py` + tests | [ ] |
| Required factory tests exist and pass | `tests/application/test_runtime_factory.py` | [ ] |
| Required contract tests exist and pass | `tests/application/test_message_contract.py` | [ ] |
| `get_message_tool_calls` always returns list | Review implementation | [ ] |
| No open S1/S2 issues | Review classification | [ ] |

---

## 8. Rework Verification

### Verify Item 1 (Tester)

Check test paths are correct:
```bash
grep -n "from ayder_cli.application" tests/application/test_runtime_factory.py
# Should show correct imports
```

### Verify Item 2 (Tester)

Check assertion is relaxed:
```bash
grep -A2 "test_to_message_dict_from_dict" tests/application/test_message_contract.py
# Should show `==` not `is`
```

### Verify Item 3 (Developer)

Check `isinstance(list)` guard:
```bash
grep -A5 "def get_message_tool_calls" src/ayder_cli/application/message_contract.py
# Should show isinstance(tool_calls, list) guard
```

---

## 9. Decision Protocol

### If Any Test Fails: **REWORK_REQUIRED**

- Document failing tests
- Classify new rework items (S1/S2/S3)
- Do not merge to `main`
- PM will issue new rework tasks

### If All Tests Pass: **PASS**

1. ✅ Both rework MRs merged to gate
2. ✅ Gate commands pass
3. ✅ Acceptance criteria verified
4. Open final MR: `arch/02/runtime-factory-gate` → `main`
5. Merge to `main`
6. Publish decision note: `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT_ARCHITECT_DECISION.md`
7. Mark Phase 02 CLOSED

---

## 10. Required Phase Decision Note

Update: `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT_ARCHITECT_DECISION.md`

### If PASS

```markdown
# Architect Decision — Phase 02 (FINAL)

**Phase ID:** 02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT  
**Date:** YYYY-MM-DD  
**Decision:** PASS

## Rework Summary

| Item | Owner | Issue | Resolution |
|------|-------|-------|------------|
| 1 | Tester | Test path/patch alignment | Fixed |
| 2 | Tester | Strict identity assertion | Relaxed to equality |
| 3 | Developer | Non-list return from get_message_tool_calls | isinstance(list) guard |

## Final Verification

```
uv run poe lint        → All checks passed
uv run poe typecheck   → Success
uv run poe test        → 862 passed, 5 skipped
```

## Merge Record

- Tester rework MR: `qa/02/factory-contract-tests-rework` → gate
- Developer rework MR: `dev/02/runtime-factory-rework` → gate
- Final MR: `arch/02/runtime-factory-gate` → `main`

## Phase 02 Status

CLOSED. Proceeding to Phase 03.
```

### If REWORK_REQUIRED

Document new rework items with severity and owner assignments.

---

## 11. Control Check D (PM Validation Required)

Before phase closure, PM will verify:

- [ ] Architect merged both rework MRs to gate
- [ ] Architect ran required commands (`lint`, `typecheck`, `test`)
- [ ] All tests pass (862 total)
- [ ] Architect published PASS decision
- [ ] Gate branch merged to `main`

If all checks pass:
- [ ] PM marks Phase 02 CLOSED
- [ ] PM unlocks Phase 03

---

## 12. Done Definition

Done only when:
- [ ] Both rework MRs merged to gate
- [ ] Gate commands pass with 862 tests
- [ ] Decision (PASS) published
- [ ] Gate branch merged to `main`
- [ ] Phase 02 marked CLOSED
- [ ] Phase 03 unlocked

---

*Phase 02 Step D Re-Run — Rework Complete — Ready for Final Gate*
