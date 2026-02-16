# Phase 02 Rework Tasks — REWORK_REQUIRED

**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Gate Decision:** REWORK_REQUIRED  
**Date:** 2026-02-16  
**Severity:** S2 (Major)  

---

## Rework Trigger

Architect Gate (Step D) failed on test execution:

```bash
uv run poe test      # FAIL
```

Failure at:
- `tests/application/test_message_contract.py::TestToMessageDict::test_to_message_dict_from_dict`

Supplementary verification:
```bash
# Developer tests PASS
uv run pytest tests/test_runtime_factory.py tests/test_message_contract.py -q
# PASS (21 passed)

# Tester tests FAIL  
uv run pytest tests/application/test_runtime_factory.py tests/application/test_message_contract.py -q
# FAIL (5 failed, 39 passed)
```

---

## Rework Items

### Item 1: Tester — Fix Test Path and Patch Assumptions (S2)

**Owner:** Tester Agent  
**Branch:** `qa/02/factory-contract-tests-rework` (from `arch/02/runtime-factory-gate`)

**Problem:**
Tester acceptance tests have path/patch assumptions that don't align with actual factory wiring.

**Required Fixes:**
- [ ] Review `tests/application/test_runtime_factory.py` — align import paths with actual `application.runtime_factory` module
- [ ] Review `tests/application/test_message_contract.py` — align patch targets with actual contract helper locations
- [ ] Ensure mocks/patches target the correct module paths after Developer implementation

**Verification:**
```bash
uv run pytest tests/application/test_runtime_factory.py -v
# Should pass after fix
```

---

### Item 2: Tester — Relax `to_message_dict` Dict Passthrough Test (S2)

**Owner:** Tester Agent  
**Branch:** `qa/02/factory-contract-tests-rework` (same as Item 1)

**Problem:**
`test_to_message_dict_from_dict` uses strict identity assertion that conflicts with contract-aligned behavior.

**Required Fix:**
- [ ] Locate test: `tests/application/test_message_contract.py::TestToMessageDict::test_to_message_dict_from_dict`
- [ ] Change assertion from identity check (`is`) to equality check (`==`)
- [ ] OR adjust expectation to match actual contract behavior (may create copy for safety)

**Contract Behavior:**
```python
def to_message_dict(message: dict | object) -> dict:
    # If already dict, may return as-is OR create copy
    # If object, convert to dict
```

**Verification:**
```bash
uv run pytest tests/application/test_message_contract.py::TestToMessageDict -v
# Should pass after fix
```

---

### Item 3: Developer — Harden `get_message_tool_calls()` (S2)

**Owner:** Developer Agent  
**Branch:** `dev/02/runtime-factory-rework` (from `arch/02/runtime-factory-gate`)

**Problem:**
`get_message_tool_calls()` doesn't always return a list for object/Mock-like messages.

**Required Fix:**
- [ ] Update `src/ayder_cli/application/message_contract.py`
- [ ] Ensure `get_message_tool_calls()` ALWAYS returns a list (`[]` fallback)
- [ ] Handle cases:
  - `dict` with `tool_calls` key
  - `dict` without `tool_calls` key → return `[]`
  - Object with `.tool_calls` attribute
  - Object without `.tool_calls` attribute → return `[]`
  - Mock-like objects (may need `getattr` with default)

**Implementation Pattern:**
```python
def get_message_tool_calls(message: dict | object) -> list:
    if isinstance(message, dict):
        return message.get("tool_calls", [])
    # For objects
    return getattr(message, "tool_calls", [])
```

**Verification:**
```bash
uv run pytest tests/test_message_contract.py -v
# Should still pass

uv run pytest tests/application/test_message_contract.py -v  
# Should now pass (was failing due to this)
```

---

## Workflow

### Step 1: Developer Rework (Item 3)

```bash
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b dev/02/runtime-factory-rework
# Implement Item 3
git push -u origin dev/02/runtime-factory-rework
# Open MR: dev/02/runtime-factory-rework → arch/02/runtime-factory-gate
```

### Step 2: Tester Rework (Items 1-2)

```bash
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b qa/02/factory-contract-tests-rework
# Implement Items 1-2
git push -u origin qa/02/factory-contract-tests-rework
# Open MR: qa/02/factory-contract-tests-rework → arch/02/runtime-factory-gate
```

### Step 3: Architect Re-Review (Step D Re-run)

After both MRs merged to `arch/02/runtime-factory-gate`:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test      # MUST PASS
```

Then Architect issues new decision (PASS or REWORK_REQUIRED).

---

## Success Criteria

- [ ] All 3 rework items completed
- [ ] Both rework MRs merged to `arch/02/runtime-factory-gate`
- [ ] `uv run poe test` passes completely
- [ ] Architect re-review completed
- [ ] Phase 02 can proceed to closure

---

## Severity Classification

| Item | Severity | Rationale |
|------|----------|-----------|
| 1 | S2 | Test path misalignment blocks acceptance testing |
| 2 | S2 | Test assertion blocks valid contract behavior |
| 3 | S2 | Contract helper returns wrong type (not list) causing test failures |

All are S2 (Major) — not critical correctness issues, but block gate acceptance.

---

*Rework tasks issued by Architect — Phase 02 Gate (Step D)*
