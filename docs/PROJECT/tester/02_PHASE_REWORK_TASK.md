# Tester Task — Phase 02 Rework

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Tester Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Task Type:** REWORK (S2 Severity)  
**Rework Items:** 1-2 of 3

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` |
| `REWORK_DOC` | `docs/PROJECT/PM_REWORK_PHASE02.md` |
| `ARCH_GATE_BRANCH` | `arch/02/runtime-factory-gate` |
| `REWORK_BRANCH` | `qa/02/factory-contract-tests-rework` |
| `QA_TEST_SCOPE` | `acceptance-test-fixes` |

---

## 2. Rework Context

### Why Rework is Required

Architect Gate (Step D) failed with test failures:

```bash
uv run poe test      # FAIL
```

- Developer unit tests: **PASS** (21 tests in `tests/test_*.py`)
- Tester acceptance tests: **FAIL** (5 failed, 39 passed in `tests/application/test_*.py`)

### Root Causes

1. **Item 1 — Test Path Issues:** Your acceptance tests have import paths and patch targets that don't align with the actual Developer implementation.

2. **Item 2 — Assertion Too Strict:** Your `test_to_message_dict_from_dict` test uses `assert result is message` (identity check), but the contract implementation may return a copy, causing the test to fail.

### Your Rework Responsibility

You are responsible for **Items 1-2** of 3 rework items:
- **Item 1: Tester (this task) — fix test paths and patches**
- **Item 2: Tester (this task) — relax dict passthrough assertion**
- Item 3: Developer — fix `get_message_tool_calls()` (not your responsibility)

---

## 3. Mission

Fix your acceptance tests to align with actual Developer implementation and use appropriate assertions.

**Key Constraints:**
- Fix import paths to match actual module locations
- Fix patch targets to match where functions are used (not defined)
- Change identity assertion (`is`) to equality assertion (`==`)
- All 44 of your acceptance tests must pass after fixes
- Do NOT modify Developer implementation files

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [ ] `PHASE_ID` and `QA_TEST_SCOPE` assigned
- [ ] `ARCH_GATE_BRANCH` exists: `arch/02/runtime-factory-gate`
- [ ] Prior rework item not blocking (Item 3 is Developer's responsibility)
- [ ] You have read `docs/PROJECT/PM_REWORK_PHASE02.md` Items 1-2
- [ ] You can see the actual Developer implementation in `arch/02/runtime-factory-gate`

If any check fails: STOP and request clarification from PM.

---

## 5. Branch Setup (Execute First)

Create rework branch from the gate branch:

```bash
git fetch origin
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b qa/02/factory-contract-tests-rework
git push -u origin qa/02/factory-contract-tests-rework
```

---

## 6. Rework Tasks

### Item 1: Fix Test Path and Patch Assumptions

**Files:**
- `tests/application/test_runtime_factory.py`
- `tests/application/test_message_contract.py`

#### Problem

Your tests were written against the architecture spec, but the Developer implementation may have slightly different module paths or usage patterns.

#### Common Issues to Fix

**A. Import Path Issues**

```python
# WRONG (may have)
from application.runtime_factory import create_runtime

# CORRECT (should be)
from ayder_cli.application.runtime_factory import create_runtime
```

**B. Patch Target Issues**

```python
# WRONG (patching where defined)
@patch('ayder_cli.application.message_contract.get_message_role')
def test_something(self, mock_role):
    ...

# CORRECT (patch where used)
@patch('ayder_cli.memory.get_message_role')  # If used in memory.py
def test_something(self, mock_role):
    ...
```

**C. Factory Component Access**

Verify your tests access `RuntimeComponents` correctly:

```python
# Check actual dataclass field names match your tests
from ayder_cli.application.runtime_factory import RuntimeComponents

# Verify all 9 fields exist:
# - config
# - llm_provider
# - process_manager
# - project_ctx
# - tool_registry
# - tool_executor
# - checkpoint_manager
# - memory_manager
# - system_prompt
```

#### Verification Steps for Item 1

1. **Check actual module structure:**
   ```bash
   ls -la src/ayder_cli/application/
   # Verify runtime_factory.py and message_contract.py exist
   ```

2. **Check actual imports work:**
   ```python
   python -c "from ayder_cli.application.runtime_factory import create_runtime, RuntimeComponents; print('OK')"
   python -c "from ayder_cli.application.message_contract import get_message_role, get_message_content, get_message_tool_calls, to_message_dict; print('OK')"
   ```

3. **Check actual usage in integrated files:**
   ```bash
   grep -n "from ayder_cli.application" src/ayder_cli/memory.py
   grep -n "from ayder_cli.application" src/ayder_cli/tui/chat_loop.py
   grep -n "from ayder_cli.application" src/ayder_cli/tui/commands.py
   ```

#### Fix Checklist for Item 1

- [ ] All imports use full path: `ayder_cli.application.X` not just `application.X`
- [ ] Patch targets match where functions are actually used
- [ ] `RuntimeComponents` field names match actual dataclass
- [ ] Mock setups align with actual factory return values

---

### Item 2: Relax `to_message_dict` Dict Passthrough Assertion

**File:** `tests/application/test_message_contract.py`

**Test:** `TestToMessageDict::test_to_message_dict_from_dict`

#### Problem

Your test likely uses identity assertion which fails if the implementation returns a copy:

```python
# YOUR CURRENT TEST (problematic)
def test_to_message_dict_from_dict(self):
    message = {"role": "user", "content": "hello"}
    result = to_message_dict(message)
    
    assert result is message  # <-- FAILS if implementation returns copy!
```

#### Required Fix

Change from identity check (`is`) to equality check (`==`):

```python
# YOUR FIXED TEST
def test_to_message_dict_from_dict(self):
    message = {"role": "user", "content": "hello"}
    result = to_message_dict(message)
    
    # Check equality, not identity - implementation may return copy
    assert result == message
    assert isinstance(result, dict)
    assert result["role"] == "user"
    assert result["content"] == "hello"
    
    # Optionally verify it's a dict with expected structure
    assert "role" in result
    assert "content" in result
```

#### Why This Fix is Correct

The contract specification says `to_message_dict` converts messages to dicts. It does NOT guarantee:
- The same dict object is returned (identity)
- Only that an equivalent dict is returned (equality)

The Developer implementation may create a copy for safety (to prevent mutation of original), which is valid behavior.

#### Alternative Interpretation

If you believe the contract SHOULD guarantee passthrough (same object), then:
1. Document this requirement explicitly
2. Ask Developer to change implementation to guarantee passthrough
3. Keep your `is` assertion

**Recommended:** Use equality check — more flexible and doesn't over-constrain implementation.

#### Fix Checklist for Item 2

- [ ] Located `test_to_message_dict_from_dict` in your test file
- [ ] Changed `assert result is message` to `assert result == message`
- [ ] Added additional assertions to verify dict structure
- [ ] Test passes with actual Developer implementation

---

## 7. Local Validation

### Step 1: Run Your Acceptance Tests (Before Fix)

```bash
uv run pytest tests/application/test_runtime_factory.py -v
# Note which tests fail and why

uv run pytest tests/application/test_message_contract.py -v
# Note which tests fail and why
```

**Expected before fix:** Some tests fail (5 failures total across both files).

### Step 2: Apply Fixes

- Fix import/patch issues (Item 1)
- Fix assertion (Item 2)

### Step 3: Run Your Acceptance Tests (After Fix)

```bash
uv run pytest tests/application/test_runtime_factory.py -v
# Expected: All 13 pass

uv run pytest tests/application/test_message_contract.py -v
# Expected: All 31 pass
```

### Step 4: Run Full Test Suite (With Developer's Fix)

**Note:** For full pass, you also need Developer's Item 3 fix merged.

If Developer's fix is not yet merged:
```bash
# Your tests should pass
uv run pytest tests/application/ -v

# But full suite may still fail on get_message_tool_calls tests
uv run poe test
```

After both your fix AND Developer's fix are merged:
```bash
uv run poe test
# Expected: All 862 tests pass
```

### Step 5: Run Gate Commands

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

---

## 8. Commit and Push

### Commit Message

```
[PHASE-02][QA][REWORK] Fix acceptance test paths and assertions

Fix S2 rework items 1-2:
- Fix import paths: use full 'ayder_cli.application.X' paths
- Fix patch targets: patch where functions are used, not defined
- Relax to_message_dict_from_dict: 'is' → '==' for flexibility
- Align tests with actual Developer implementation

Fixes: REWORK_REQUIRED in Step D gate
Related: Item 3 (Developer responsibility)
```

### Push

```bash
git push -u origin qa/02/factory-contract-tests-rework
```

---

## 9. Merge Request

Open MR:
- **Source:** `qa/02/factory-contract-tests-rework`
- **Target:** `arch/02/runtime-factory-gate`
- **Title:** `[PHASE-02][REWORK] Fix acceptance test paths and assertions`
- **Reviewer:** Architect

### MR Description Template

```markdown
## Phase 02 Rework — Items 1-2 (Tester)

### Problems Fixed

**Item 1 — Test Path Issues:**
- Import paths now use full `ayder_cli.application.X`
- Patch targets aligned with actual usage locations
- Mock configurations match actual factory implementation

**Item 2 — Assertion Too Strict:**
- Changed `test_to_message_dict_from_dict` from `is` to `==`
- Allows implementation to return copy if needed
- Added structure validation assertions

### Verification

- [ ] `uv run poe lint` passes
- [ ] `uv run poe typecheck` passes
- [ ] Acceptance tests pass: `tests/application/test_runtime_factory.py` (13 tests)
- [ ] Acceptance tests pass: `tests/application/test_message_contract.py` (31 tests)

### Files Changed
- `tests/application/test_runtime_factory.py` (path fixes)
- `tests/application/test_message_contract.py` (path and assertion fixes)

### Related
- Item 3 is Developer's responsibility
- Full pass requires all 3 items merged
```

---

## 10. Coordination with Developer

### Your Items (1-2) are Independent

Your fixes are in your test files (`tests/application/test_*.py`).
Developer's fix (Item 3) is in the implementation (`message_contract.py`).

### Sequence

```
You fix tests ───────────┐
                         ├──→ Both MRs merged → Architect re-runs gate
Developer fixes impl ────┘
```

### Test Interdependency

Some of your tests exercise `get_message_tool_calls()` (Item 3's function).
- Before Developer's fix: Those specific tests may still fail
- After Developer's fix: All tests should pass

**Your responsibility:** Fix Items 1-2. Don't worry about Item 3 failures.

### Communication

- Do NOT modify `src/ayder_cli/application/*.py` — that's Developer's scope
- If you discover the implementation has bugs, report in MR comments
- If you're unsure about contract behavior, ask Architect

---

## 11. Definition of Done

- [ ] Rework branch `qa/02/factory-contract-tests-rework` exists
- [ ] Import paths use full `ayder_cli.application` prefix
- [ ] Patch targets align with actual usage locations
- [ ] `test_to_message_dict_from_dict` uses `==` not `is`
- [ ] Your 13 factory tests pass
- [ ] Your 31 message contract tests pass (except any blocked by Item 3)
- [ ] Gate commands pass: `lint`, `typecheck`
- [ ] MR opened targeting `arch/02/runtime-factory-gate`
- [ ] MR description includes verification checklist

---

## 12. Questions?

If unclear on:
- **Import paths:** Check actual files in `src/ayder_cli/application/`
- **Patch targets:** Check where functions are imported/used, not defined
- **Assertion change:** See Section 6.2 (Item 2)
- **Developer coordination:** See Section 10
- **Gate requirements:** See `docs/PROJECT/PM_REWORK_PHASE02.md`

Escalate to PM or Architect via MR comments.

---

*Tester Rework Task — Items 1-2 of 3 — Phase 02*
