# Developer Rework Task — Phase 02

**Status:** REWORK_REQUIRED  
**Assigned:** Developer Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Rework Item:** Item 3 of 3  
**Severity:** S2 (Major)

---

## Rework Context

Architect Gate (Step D) failed due to test failures. This rework item is for the Developer to fix `get_message_tool_calls()` behavior.

**Original Report:** `.ayder/architect_to_PM_phase_02_GATE.md`
**Full Rework Doc:** `docs/PROJECT/PM_REWORK_PHASE02.md`

---

## Rework Assignment

### Item 3: Harden `get_message_tool_calls()` to Always Return List

**File:** `src/ayder_cli/application/message_contract.py`

**Problem:**
The `get_message_tool_calls()` function doesn't always return a list for object/Mock-like messages, causing test failures in the Tester suite.

**Required Behavior:**
- ALWAYS return a `list` (never `None`, never raise)
- Handle `dict` messages: `message.get("tool_calls", [])`
- Handle object messages: `getattr(message, "tool_calls", [])`
- Handle missing/None: return `[]`

**Current Code (likely):**
```python
def get_message_tool_calls(message: dict | object) -> list:
    if isinstance(message, dict):
        return message.get("tool_calls")  # May return None!
    return message.tool_calls  # May raise AttributeError!
```

**Fixed Code (required):**
```python
def get_message_tool_calls(message: dict | object) -> list:
    """Extract tool_calls from dict or object message.
    
    Always returns a list. Returns empty list if tool_calls not present.
    """
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls")
        return tool_calls if tool_calls is not None else []
    # For objects (including Mock-like)
    return getattr(message, "tool_calls", [])
```

---

## Verification Steps

Before committing, verify the fix:

```bash
# Run developer tests (should still pass)
uv run pytest tests/test_message_contract.py -v

# Run tester tests (should now pass the ones that were failing)
uv run pytest tests/application/test_message_contract.py::TestGetMessageToolCalls -v
```

**Expected:** All tests pass.

---

## Branch and MR

### Setup

```bash
git fetch origin
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b dev/02/runtime-factory-rework
git push -u origin dev/02/runtime-factory-rework
```

### Changes

Only modify:
- `src/ayder_cli/application/message_contract.py` — Fix `get_message_tool_calls()`

### Commit

```
[PHASE-02][DEV][REWORK] Harden get_message_tool_calls to always return list

- Ensure dict messages with missing/None tool_calls return []
- Ensure object messages without tool_calls attribute return []
- Use getattr with default for object messages
- Fixes S2 rework item 3

Relates: REWORK_REQUIRED in Step D
```

### MR

Open MR:
- **Source:** `dev/02/runtime-factory-rework`
- **Target:** `arch/02/runtime-factory-gate`
- **Title:** `[PHASE-02][REWORK] Fix get_message_tool_calls() return type`
- **Reviewer:** Architect

---

## Coordination with Tester

This rework item (Item 3) is independent of Tester Items 1-2. Both can proceed in parallel.

Once both:
- Developer MR (`dev/02/runtime-factory-rework`) merged
- Tester MR (`qa/02/factory-contract-tests-rework`) merged

The Architect will re-run Step D gate.

---

## Definition of Done

- [ ] `get_message_tool_calls()` always returns a list
- [ ] Handles dict messages (with and without tool_calls)
- [ ] Handles object messages (with and without tool_calls attribute)
- [ ] Handles Mock-like objects
- [ ] Developer tests still pass
- [ ] Tester tests that were failing now pass
- [ ] MR opened targeting `arch/02/runtime-factory-gate`

---

*Developer Rework — Item 3 of 3 — Phase 02*
