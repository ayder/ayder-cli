# Architect Gate Assignment — Phase 02: Runtime Factory and Message Contract

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Architect Reviewer Agent  
**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Step:** D (Gate Review + Merge Authority)

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` |
| `PROJECT_BRANCH` | `main` |
| `ARCH_GATE_BRANCH` | `arch/02/runtime-factory-gate` |
| Developer MR | `dev/02/runtime-factory` → `arch/02/runtime-factory-gate` |
| Tester MR | `qa/02/factory-contract-tests` → `arch/02/runtime-factory-gate` |

---

## 2. Core References (Read Before Proceeding)

All documentation available in `arch/02/runtime-factory-gate`:

1. `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md` — Phase acceptance criteria
2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md` — Global constraints
3. `docs/PROJECT/architect/02_PHASE/02_ARCHITECTURE_DESIGN.md` — Your design specification
4. `docs/PROJECT/developer/02_PHASE.md` — Developer task (completed)
5. `docs/PROJECT/tester/02_PHASE.md` — Tester task (completed)
6. `docs/REFACTOR/ARCHITECT_PROMPT.md` — Architect operating guide
7. `AGENTS.md` — Coding conventions

---

## 3. Mission

Own phase gating and merge control for Phase 02. Review Developer and Tester MRs, enforce acceptance criteria, resolve the dual test suite situation, run mandatory commands, and issue PASS or REWORK_REQUIRED decision.

**Key Issue to Resolve:**
- Developer delivered 21 tests in `tests/test_*.py`
- Tester delivered 44 tests in `tests/application/test_*.py`
- Both test the same factory and contract interfaces
- **Decision required:** Consolidate, keep both, or select one

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning gate review, confirm:

- [ ] `PHASE_ID` and `ARCH_GATE_BRANCH` assigned
- [ ] Developer MR ready: `dev/02/runtime-factory`
- [ ] Tester MR ready: `qa/02/factory-contract-tests`
- [ ] Control Checks B and C passed (verified by PM)

If any check fails: STOP and request correction from PM.

---

## 5. Developer MR Review

**Source:** `dev/02/runtime-factory`  
**Target:** `arch/02/runtime-factory-gate`

**Implementation to Review:**

| File | Purpose | Review Criteria |
|------|---------|-----------------|
| `application/runtime_factory.py` | Shared factory | Assembles 9 components per design? |
| `application/message_contract.py` | Message normalization | Handles dict/object per contract rules? |
| `cli_runner.py` | CLI wiring | `_build_services()` delegates to factory? |
| `tui/app.py` | TUI wiring | `__init__()` uses factory? |
| `memory.py` | Contract integration | `_build_conversation_summary` uses helpers? |
| `tui/chat_loop.py` | Contract integration | `_handle_checkpoint` uses helpers? |
| `tui/commands.py` | Contract integration | `/compact`, `/save-memory` use helpers? |
| `tests/test_runtime_factory.py` | Dev tests | Basic coverage (21 tests) |
| `tests/test_message_contract.py` | Dev tests | Basic coverage |
| `tests/test_cli.py` | Updated tests | Patch paths updated? |

**Verification Checklist:**
- [ ] Factory assembles all 9 components
- [ ] CLI uses factory (no inline composition)
- [ ] TUI uses factory (UI behavior preserved)
- [ ] Message contract handles dict/object safely
- [ ] Contract integrated in all 3 locations (memory, chat_loop, commands)
- [ ] No UX regressions
- [ ] No Phase 04 async changes

---

## 6. Tester MR Review

**Source:** `qa/02/factory-contract-tests`  
**Target:** `arch/02/runtime-factory-gate`

**Deliverables to Review:**

| File | Purpose | Review Criteria |
|------|---------|-----------------|
| `tester/02_PHASE/02_TEST_MIGRATION_MAPPING.md` | Migration map | Obsolete tests mapped to replacements? |
| `tests/application/test_runtime_factory.py` | Factory tests | Comprehensive coverage (13 tests)? |
| `tests/application/test_message_contract.py` | Contract tests | Comprehensive coverage (31 tests)? |

**Test Migration Mapping:**

| Obsolete Test | Replacement |
|---------------|-------------|
| `test_build_services_with_exception_in_structure_macro` | `test_factory_handles_structure_macro_failure` |
| `test_build_services_success_with_structure_macro` | `test_factory_consistent_system_prompt` |
| `test_build_services_with_custom_config` | `test_factory_accepts_config_override` |
| `test_build_services_with_custom_project_root` | `test_factory_accepts_project_root` |

**Verification Checklist:**
- [ ] All obsolete tests identified and mapped
- [ ] Factory tests cover: assembly, CLI integration, TUI integration, parity
- [ ] Contract tests cover: dict/object, edge cases, integration points
- [ ] Tests use `pytest.importorskip()` for graceful handling
- [ ] No tests removed without approval

---

## 7. Test Suite Consolidation Decision

**Issue:** Two test suites for same functionality

| Suite | Location | Count | Coverage |
|-------|----------|-------|----------|
| Developer | `tests/test_*.py` | 21 | Basic unit tests |
| Tester | `tests/application/test_*.py` | 44 | Comprehensive acceptance |

**Options:**

### Option A — Keep Both (Recommended)
- Developer tests as quick unit tests
- Tester tests as comprehensive acceptance tests
- Both can coexist; no consolidation needed

### Option B — Consolidate to Tester Suite
- Remove developer tests
- Keep tester tests as authoritative
- May need to verify no coverage loss

### Option C — Merge into Unified Suite
- Consolidate into `tests/application/`
- Select best tests from each
- Most work, marginal benefit

**Decision Required:** Choose A, B, or C and document in decision note.

---

## 8. Gate Commands (Mandatory)

Run on `arch/02/runtime-factory-gate` after merging both MRs:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

**Expected Results:**
- lint: All checks passed
- typecheck: Success, no issues
- test: 818+ passed (developer) or 777+ passed + 44 skipped (tester, until modules present)

Record actual results in decision note.

---

## 9. Acceptance Criteria Verification

Per `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT.md`:

| Criterion | Verification Method | Status |
|-----------|---------------------|--------|
| One shared runtime factory used by both CLI and TUI | Review `cli_runner.py`, `tui/app.py` | [ ] |
| Message normalization prevents dict/object regressions | Review `message_contract.py` + tests | [ ] |
| Required factory tests exist and pass | Run `tests/application/test_runtime_factory.py` | [ ] |
| Required contract tests exist and pass | Run `tests/application/test_message_contract.py` | [ ] |
| No open S1/S2 issues | Review classification | [ ] |

---

## 10. Decision Protocol

### If Any S1/S2 Issues Found: **REWORK_REQUIRED**

- Return explicit rework list to Developer/Tester teams
- Do not merge to `main`
- Classification:
  - **S1 (Critical):** Factory doesn't assemble correctly, contract causes regressions
  - **S2 (Major):** Missing test coverage, architectural boundary violations
  - **S3 (Minor):** Non-blocking cleanup

### If All Criteria Satisfied: **PASS**

1. Merge Developer MR into `arch/02/runtime-factory-gate`
2. Merge Tester MR into `arch/02/runtime-factory-gate`
3. **Decide on test consolidation** (A, B, or C from Section 7)
4. Apply consolidation if needed
5. Re-run gate commands
6. Open final MR: `arch/02/runtime-factory-gate` → `main`
7. Merge to `main`
8. Publish decision note

---

## 11. Required Phase Decision Note

Publish to: `docs/REFACTOR/PHASES/02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT_ARCHITECT_DECISION.md`

**Template:**
```markdown
# Architect Decision — Phase 02

**Phase ID:** 02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT  
**Date:** YYYY-MM-DD  
**Decision:** PASS / REWORK_REQUIRED

## Acceptance Criteria Checklist

- [ ] One shared runtime factory used by both CLI and TUI
- [ ] Message normalization prevents dict/object shape regressions
- [ ] Required tests exist and pass
- [ ] No open S1/S2 issues

## Command Results

```
uv run poe lint        → [result]
uv run poe typecheck   → [result]
uv run poe test        → [result]
```

## Test Suite Consolidation Decision

**Chosen Option:** A / B / C

**Rationale:** [explanation]

**Actions Taken:** [if any consolidation applied]

## Rework Items (if REWORK_REQUIRED)

| Severity | Item | Owner |
|----------|------|-------|
| S1/S2/S3 | [description] | Developer/Tester |

## Merge Record

- Developer MR: [commit/merge ref]
- Tester MR: [commit/merge ref]
- Test consolidation: [commit ref if applicable]
- Final MR: `arch/02/runtime-factory-gate` → `main` [MR ref]
```

---

## 12. Control Check D (PM Validation Required)

Before phase closure, PM will verify:

- [ ] Architect reviewed all MRs
- [ ] Architect ran required commands (`lint`, `typecheck`, `test`)
- [ ] Architect published PASS or REWORK_REQUIRED decision note
- [ ] **Test consolidation decision documented**

If PASS:
- [ ] Architect merged `arch/02/runtime-factory-gate` → `main`
- [ ] PM marks phase complete and unlocks Phase 03

If REWORK_REQUIRED:
- [ ] PM opens rework tickets (DEV/QA) with severity labels
- [ ] PM loops back to Step B and/or Step C

---

## 13. Done Definition

Done only when:
- [ ] Developer and Tester MRs reviewed
- [ ] Test consolidation decision made and documented
- [ ] Gate commands run and results recorded
- [ ] Decision (PASS or REWORK_REQUIRED) published
- [ ] If PASS: gate branch merged to `main`
- [ ] If REWORK_REQUIRED: actionable tickets issued

---

*Phase 02 Step D — Architect Gate Assignment — READY FOR EXECUTION*
