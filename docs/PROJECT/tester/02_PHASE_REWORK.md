# Tester Rework Task — Phase 02

**Status:** REWORK_REQUIRED  
**Assigned:** Tester Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Rework Items:** Items 1-2 of 3  
**Severity:** S2 (Major)

---

## Rework Context

Architect Gate (Step D) failed due to test failures in the Tester acceptance suite. Developer unit tests pass; Tester acceptance tests fail.

**Original Report:** `.ayder/architect_to_PM_phase_02_GATE.md`
**Full Rework Doc:** `docs/PROJECT/PM_REWORK_PHASE02.md`

---

## Rework Assignments

### Item 1: Fix Test Path and Patch Assumptions

**Files:**
- `tests/application/test_runtime_factory.py`
- `tests/application/test_message_contract.py`

**Problem:**
Test path/patch assumptions don't align with actual factory wiring implemented by Developer.

**Required Fixes:**

1. **Review import paths:**
   - Ensure imports reference `ayder_cli.application.runtime_factory`
   - Ensure imports reference `ayder_cli.application.message_contract`

2. **Review patch targets:**
   - If patching `create_runtime`, target correct module path
   - If patching contract helpers, target where they're used (not where defined)
   - Example: patch `ayder_cli.memory.get_message_role` not `ayder_cli.application.message_contract.get_message_role`

3. **Common issues to check:**
   - `@patch('wrong.module.path')` → fix to correct path
   - `from application.runtime_factory import ...` → `from ayder_cli.application.runtime_factory import ...`

---

### Item 2: Relax `to_message_dict` Dict Passthrough Test

**File:** `tests/application/test_message_contract.py`

**Test:** `TestToMessageDict::test_to_message_dict_from_dict`

**Problem:**
Test uses strict identity assertion (`is`) that conflicts with contract-aligned behavior. The contract may return a copy of the dict for safety, which is valid behavior.

**Current Test (likely):**
```python
def test_to_message_dict_from_dict(self):
    message = {"role": "user", "content": "hello"}
    result = to_message_dict(message)
    assert result is message  # Strict identity - fails if copy made!
```

**Fixed Test (required):**
```python
def test_to_message_dict_from_dict(self):
    message = {"role": "user", "content": "hello"}
    result = to_message_dict(message)
    # Accept either same object OR equal copy
    assert result == message
    assert isinstance(result, dict)
    assert result["role"] == "user"
    assert result["content"] == "hello"
```

**Alternative Fix (if contract guarantees passthrough):**
Document that `to_message_dict` returns the same dict object when given a dict, and fix the implementation to guarantee this.

**Decision:** Use equality check (`==`) not identity (`is`) — more flexible.

---

## Verification Steps

Before committing, verify fixes:

```bash
# Run only the acceptance tests
uv run pytest tests/application/test_runtime_factory.py -v
# Should pass after Item 1 fix

uv run pytest tests/application/test_message_contract.py -v
# Should pass after Items 1-2 fixes

# Run full test suite
uv run poe test
# Should now pass completely (after Developer also fixes Item 3)
```

**Note:** Full pass requires Developer Item 3 to also be complete. Your fixes alone may not achieve full pass yet.

---

## Branch and MR

### Setup

```bash
git fetch origin
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b qa/02/factory-contract-tests-rework
git push -u origin qa/02/factory-contract-tests-rework
```

### Changes

Modify:
- `tests/application/test_runtime_factory.py` — Fix paths/patches (Item 1)
- `tests/application/test_message_contract.py` — Fix paths/patches (Item 1), fix assertion (Item 2)

### Commit

```
[PHASE-02][QA][REWORK] Fix test paths and relax dict passthrough assertion

- Fix import paths and patch targets for factory/contract tests
- Align patch assumptions with actual Developer implementation
- Relax to_message_dict_from_dict assertion from 'is' to '=='
- Fixes S2 rework items 1-2

Relates: REWORK_REQUIRED in Step D
```

### MR

Open MR:
- **Source:** `qa/02/factory-contract-tests-rework`
- **Target:** `arch/02/runtime-factory-gate`
- **Title:** `[PHASE-02][REWORK] Fix acceptance test paths and assertions`
- **Reviewer:** Architect

---

## Coordination with Developer

Your rework items (1-2) are independent of Developer Item 3. Both can proceed in parallel.

Once both:
- Tester MR (`qa/02/factory-contract-tests-rework`) merged
- Developer MR (`dev/02/runtime-factory-rework`) merged

The Architect will re-run Step D gate.

---

## Definition of Done

- [ ] Import paths corrected in both test files
- [ ] Patch targets aligned with actual implementation
- [ ] `test_to_message_dict_from_dict` uses equality not identity
- [ ] Tester acceptance tests pass (may need Developer fix for full suite pass)
- [ ] MR opened targeting `arch/02/runtime-factory-gate`

---

*Tester Rework — Items 1-2 of 3 — Phase 02*
