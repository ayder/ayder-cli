# Tester Task — Phase 02: Runtime Factory and Message Contract

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** QA/Test Engineer Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Phase Doc:** `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md`

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` |
| `PROJECT_BRANCH` | `main` |
| `ARCH_GATE_BRANCH` | `arch/02/runtime-factory-gate` |
| `QA_TEST_SCOPE` | `factory-contract-tests` |

---

## 2. Core References (Read Before Proceeding)

All documentation available in `arch/02/runtime-factory-gate`:

1. `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` — Phase QA-* tasks
2. `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md` — Factory and contract specs
3. `docs/PROJECT/tester/01_PHASE/01_OBSOLETE_TEST_CANDIDATES.md` — Obsolete test candidates
4. `docs/REFACTOR/TESTER_PROMPT.md` — Tester operating guide
5. `AGENTS.md` — Test commands and conventions

---

## 3. Mission

Execute Tester tasks for Phase 02 in parallel with Developer. Remove obsolete wiring tests, add runtime factory tests, and add message contract tests.

**Key Constraints:**
- Work parallel to Developer (do not block on Developer branch)
- Remove obsolete tests that assert old private composition internals
- Maintain or improve coverage in changed areas
- Map remove→replace for every removed test

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning work, confirm:

- [ ] `PHASE_ID` and `QA_TEST_SCOPE` assigned
- [ ] `ARCH_GATE_BRANCH` exists: `arch/02/runtime-factory-gate`
- [ ] Architect kickoff complete (design docs exist)
- [ ] Prior phase (01) is PASS

If any check fails: STOP and request correction from PM.

---

## 5. Branch Setup (Execute First)

Create QA branch from the gate branch:

```bash
git fetch origin
git checkout arch/02/runtime-factory-gate
git pull --ff-only origin arch/02/runtime-factory-gate
git checkout -b qa/02/factory-contract-tests
git push -u origin qa/02/factory-contract-tests
```

---

## 6. Tester Tasks for Phase 02

### QA-02.1 Remove Obsolete Wiring Tests

**Objective:** Remove tests that assert old private composition internals

**Candidates from Phase 01 Inventory:**

| Test File | Candidate Tests | Reason |
|-----------|-----------------|--------|
| `tests/services/tools/test_executor.py` | Tests mocking internal `_build_services` wiring | Factory replaces inline composition |
| `tests/test_cli.py` | Tests asserting specific initialization order | Factory abstracts composition |

**Requirements:**
- Identify tests that will break due to factory introduction
- Document remove→replace mapping
- Do NOT remove tests yet without Architect approval during gate
- Prepare removal list for gate review

**Deliverable:** Updated `docs/PROJECT/tester/02_PHASE/02_TEST_MIGRATION_MAPPING.md`

### QA-02.2 Add Runtime Factory Tests

**Objective:** Add tests proving CLI and TUI receive factory-built dependencies

**Required Tests:**

1. **Factory Assembly Test**
   - Test: `test_runtime_factory_assembles_all_components`
   - Verify: `create_runtime()` returns all 9 components
   - Location: `tests/application/test_runtime_factory.py`

2. **Factory CLI Integration Test**
   - Test: `test_cli_uses_factory_components`
   - Verify: CLI runner uses factory-built dependencies
   - Location: `tests/test_cli_runner.py`

3. **Factory TUI Integration Test**
   - Test: `test_tui_uses_factory_components`
   - Verify: TUI app uses factory-built dependencies
   - Location: `tests/ui/test_app.py`

4. **Factory Composition Parity Test**
   - Test: `test_cli_tui_factory_parity`
   - Verify: CLI and TUI get equivalent core dependencies
   - Location: `tests/application/test_runtime_factory.py`

**Deliverable:** New test file `tests/application/test_runtime_factory.py` + updates

### QA-02.3 Add Message Contract Tests

**Objective:** Cover mixed message representations

**Required Tests:**

1. **Dict Message Test**
   - Test: `test_get_message_role_from_dict`
   - Input: `{"role": "user", "content": "hello"}`
   - Verify: Returns `"user"`

2. **Object Message Test**
   - Test: `test_get_message_role_from_object`
   - Input: Object with `.role` attribute
   - Verify: Returns role attribute value

3. **Content Extraction Test (Mixed)**
   - Test: `test_get_message_content_dict_and_object`
   - Inputs: Dict and object messages
   - Verify: Both return correct content string

4. **Tool Calls Extraction Test**
   - Test: `test_get_message_tool_calls`
   - Input: Message with tool_calls
   - Verify: Tool calls extracted correctly from both formats

5. **Conversion Test**
   - Test: `test_to_message_dict`
   - Input: Object message
   - Verify: Returns proper dict representation

6. **Checkpoint Summary Integration Test**
   - Test: `test_checkpoint_summary_with_mixed_messages`
   - Verify: Summary generation works with dict/object messages

**Edge Cases to Cover:**
- Missing role field → fallback behavior
- Missing content field → `""` fallback
- Non-string content → coercion
- Provider-specific object formats

**Deliverable:** New test file `tests/application/test_message_contract.py`

---

## 7. Test Migration Mapping

For every test removed, document:

```markdown
| Removed Test | Reason | Replacement Test |
|--------------|--------|------------------|
| test_old_wiring | Factory replaces inline composition | test_factory_assembles_components |
```

---

## 8. Local Validation Before Push

Run mandatory checks:

```bash
uv run poe lint
uv run poe test
```

When test architecture changed significantly:
```bash
uv run poe typecheck
uv run poe test-all
```

All checks must pass.

---

## 9. Commit and Push

Commit message format:
```
[PHASE-02][QA] factory and message contract tests
```

Push:
```bash
git push -u origin qa/02/factory-contract-tests
```

---

## 10. Merge Request

Open MR:
- **Source:** `qa/02/factory-contract-tests`
- **Target:** `arch/02/runtime-factory-gate`
- **Reviewer:** Architect team

### MR Description Template

```markdown
## Phase 02 Tester Deliverables

### Changes
- [ ] Obsolete wiring tests identified (removal deferred to gate)
- [ ] Runtime factory tests added
- [ ] Message contract tests added
- [ ] Test migration mapping documented

### Test Migration Mapping
| Removed Test | Reason | Replacement Test |
|--------------|--------|------------------|
| (pending gate approval) | ... | ... |

### Verification
- [ ] `uv run poe lint` passes
- [ ] `uv run poe test` passes
- [ ] Coverage maintained or improved

### Files Changed
- docs/PROJECT/tester/02_PHASE/02_TEST_MIGRATION_MAPPING.md (new)
- tests/application/test_runtime_factory.py (new)
- tests/application/test_message_contract.py (new)
- tests/... (modifications if needed)

### Notes for Architect Review
- Factory tests validate CLI/TUI composition parity
- Message contract tests cover dict/object formats
- No tests removed yet - awaiting approval
```

---

## 11. Control Check C (PM Validation Required)

Before Architect gate assignment (Step D), PM will verify:

- [ ] Tester branch exists: `qa/02/factory-contract-tests`
- [ ] Tester posted remove→replace test migration mapping
- [ ] Tester listed acceptance-criteria tests for phase

If migration mapping is incomplete: PM will block gate request.

---

## 12. Done Definition

Done when:
- [ ] Tester branch `qa/02/factory-contract-tests` exists
- [ ] Obsolete wiring tests identified and mapped
- [ ] Runtime factory tests added and passing
- [ ] Message contract tests added and passing
- [ ] Test migration mapping documented
- [ ] All gate commands pass (lint, test)
- [ ] MR opened targeting `arch/02/runtime-factory-gate`
- [ ] Control Check C items confirmed

---

*Generated from analysis of .ayder/architect_to_PM_phase02.pm*
