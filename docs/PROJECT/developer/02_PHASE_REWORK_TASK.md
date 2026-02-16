# Developer Task — Phase 02 Rework

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Developer Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Task Type:** REWORK (S2 Severity)  
**Rework Item:** 3 of 3

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` |
| `REWORK_DOC` | `docs/PROJECT/PM_REWORK_PHASE02.md` |
| `ARCH_GATE_BRANCH` | `arch/02/runtime-factory-gate` |
| `REWORK_BRANCH` | `dev/02/runtime-factory-rework` |
| `DEV_TASK_SCOPE` | `message-contract-fix` |

---

## 2. Rework Context

### Why Rework is Required

Architect Gate (Step D) failed with test failures:

```bash
uv run poe test      # FAIL
```

- Developer unit tests: **PASS** (21 tests in `tests/test_*.py`)
- Tester acceptance tests: **FAIL** (5 failed, 39 passed in `tests/application/test_*.py`)

### Root Cause

The `get_message_tool_calls()` function in `message_contract.py` does not always return a list, causing test failures when:
- Dict messages have `tool_calls: None` → returns `None` instead of `[]`
- Object messages lack `tool_calls` attribute → raises `AttributeError`

### Your Rework Responsibility

You are responsible for **Item 3** of 3 rework items:
- Items 1-2: Tester (test paths and assertions)
- **Item 3: Developer (this task) — fix `get_message_tool_calls()`**

---

## 3. Mission

Fix `get_message_tool_calls()` in `message_contract.py` to **ALWAYS return a list**, handling all edge cases properly.

**Key Constraint:**
- Function signature must remain: `def get_message_tool_calls(message: dict | object) -> list`
- Return type must ALWAYS be `list` (never `None`, never raise)
- All existing tests must still pass
- New edge cases must be handled

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [ ] `PHASE_ID` and `DEV_TASK_SCOPE` assigned
- [ ] `ARCH_GATE_BRANCH` exists: `arch/02/runtime-factory-gate`
- [ ] Prior rework items not blocking (Items 1-2 are Tester's responsibility)
- [ ] You have read `docs/PROJECT/PM_REWORK_PHASE02.md` Item 3

If any check fails: STOP and request clarification from PM.

---

## 5. Branch Setup (Execute First)

Create rework branch from the gate branch:

```bash
git fetch origin
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b dev/02/runtime-factory-rework
git push -u origin dev/02/runtime-factory-rework
```

---

## 6. Rework Task

### Task: Fix `get_message_tool_calls()` to Always Return List

**File:** `src/ayder_cli/application/message_contract.py`

#### Current Problematic Code (likely)

```python
def get_message_tool_calls(message: dict | object) -> list:
    if isinstance(message, dict):
        return message.get("tool_calls")  # Returns None if missing!
    return message.tool_calls  # Raises AttributeError if missing!
```

#### Required Fixed Code

```python
def get_message_tool_calls(message: dict | object) -> list:
    """Extract tool_calls from dict or object message.
    
    Always returns a list. Returns empty list if tool_calls not present.
    Handles both dict messages and provider object messages.
    
    Args:
        message: A dict or object with tool_calls attribute
        
    Returns:
        List of tool calls, or empty list if not present
    """
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls")
        return tool_calls if tool_calls is not None else []
    # For objects (including Mock-like objects in tests)
    return getattr(message, "tool_calls", [])
```

#### Edge Cases to Handle

| Input | Expected Output | Why |
|-------|-----------------|-----|
| `{"tool_calls": [...]}` | `[...]` | Normal dict case |
| `{"tool_calls": None}` | `[]` | None should become empty list |
| `{}` (no tool_calls key) | `[]` | Missing key should become empty list |
| `object_with_tool_calls` | `[...]` | Normal object case |
| `object_without_tool_calls` | `[]` | Missing attribute should become empty list |
| `Mock()` (test mock) | `[]` | getattr handles mocks safely |

#### Verification Checklist

- [ ] Function always returns a list type
- [ ] Dict with `tool_calls: [...]` returns the list
- [ ] Dict with `tool_calls: None` returns `[]`
- [ ] Dict without `tool_calls` key returns `[]`
- [ ] Object with `.tool_calls` attribute returns the value
- [ ] Object without `.tool_calls` attribute returns `[]`
- [ ] Mock objects work correctly (use `getattr` with default)

---

## 7. Local Validation

### Step 1: Run Your Original Tests

```bash
uv run pytest tests/test_message_contract.py -v
```
**Expected:** All 21 developer tests still pass.

### Step 2: Run the Failing Tester Tests

```bash
uv run pytest tests/application/test_message_contract.py::TestGetMessageToolCalls -v
```
**Expected:** These now pass (were failing due to your bug).

### Step 3: Run Full Test Suite

```bash
uv run poe test
```
**Expected:** All tests pass (862 total).

**Note:** Full pass also requires Tester Items 1-2. If those aren't merged yet, you may see 5 failures until Tester completes their rework.

### Step 4: Run Gate Commands

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```
**Expected:** All pass.

---

## 8. Commit and Push

### Commit Message

```
[PHASE-02][DEV][REWORK] Harden get_message_tool_calls to always return list

Fix S2 rework item 3:
- Ensure dict messages with missing/None tool_calls return [] not None
- Ensure object messages without tool_calls attribute return [] not raise
- Use getattr with default for safe object attribute access
- Handles Mock-like objects in tests

Fixes: REWORK_REQUIRED in Step D gate
Related: Items 1-2 (Tester responsibility)
```

### Push

```bash
git push -u origin dev/02/runtime-factory-rework
```

---

## 9. Merge Request

Open MR:
- **Source:** `dev/02/runtime-factory-rework`
- **Target:** `arch/02/runtime-factory-gate`
- **Title:** `[PHASE-02][REWORK] Fix get_message_tool_calls() return type`
- **Reviewer:** Architect

### MR Description Template

```markdown
## Phase 02 Rework — Item 3 (Developer)

### Problem
`get_message_tool_calls()` didn't always return a list:
- Returned `None` for dict with `tool_calls: None`
- Raised `AttributeError` for objects without `tool_calls` attribute

### Fix
- Dict: return `tool_calls if tool_calls is not None else []`
- Object: return `getattr(message, "tool_calls", [])`

### Verification
- [ ] `uv run poe lint` passes
- [ ] `uv run poe typecheck` passes
- [ ] Developer tests pass: `tests/test_message_contract.py`
- [ ] Tester tests pass: `tests/application/test_message_contract.py::TestGetMessageToolCalls`

### Files Changed
- `src/ayder_cli/application/message_contract.py` (1 function modified)

### Related
- Rework items 1-2 are Tester's responsibility
- Full pass requires all 3 items merged
```

---

## 10. Coordination with Tester

### Your Item (3) is Independent

Your fix is in the implementation (`message_contract.py`).
Tester's fixes (Items 1-2) are in their test files (`tests/application/test_*.py`).

### Sequence

```
You fix implementation ──┐
                         ├──→ Both MRs merged → Architect re-runs gate
Tester fixes tests ──────┘
```

### Communication

- Do NOT modify `tests/application/test_*.py` — that's Tester's scope
- If you discover Tester issues while running tests, document in MR comments
- Architect will coordinate the merge order

---

## 11. Definition of Done

- [ ] Rework branch `dev/02/runtime-factory-rework` exists
- [ ] `get_message_tool_calls()` always returns a list (never None, never raises)
- [ ] All 6 edge cases handled (see Section 6 table)
- [ ] Developer unit tests still pass (21 tests)
- [ ] Tester acceptance tests now pass (specifically `TestGetMessageToolCalls`)
- [ ] Gate commands pass: `lint`, `typecheck`, `test`
- [ ] MR opened targeting `arch/02/runtime-factory-gate`
- [ ] MR description includes verification checklist

---

## 12. Questions?

If unclear on:
- **Function behavior:** See Section 6 (Required Fixed Code)
- **Edge cases:** See Section 6 (Edge Cases table)
- **Tester coordination:** See Section 10
- **Gate requirements:** See `docs/PROJECT/PM_REWORK_PHASE02.md`

Escalate to PM or Architect via MR comments.

---

*Developer Rework Task — Item 3 of 3 — Phase 02*
