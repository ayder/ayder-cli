# Architect Gate Assignment — Phase 01: Baseline and Governance

**Status:** READY_FOR_ASSIGNMENT  
**Assigned:** Architect Reviewer Agent  
**Phase ID:** `01_PHASE_BASELINE_AND_GOVERNANCE`  
**Step:** D (Gate Review + Merge Authority)

---

## 1. Assignment Inputs

| Input | Value |
|-------|-------|
| `PHASE_ID` | `01_PHASE_BASELINE_AND_GOVERNANCE` |
| `PHASE_DOC` | `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md` |
| `PROJECT_BRANCH` | `main` |
| `ARCH_GATE_BRANCH` | `arch/01/baseline-gate` |
| Developer MR | `dev/01/baseline-inventory` → `arch/01/baseline-gate` |
| Tester MR | `qa/01/test-inventory` → `arch/01/baseline-gate` |

---

## 2. Core References (Read Before Proceeding)

1. `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md` — Phase acceptance criteria
2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md` — Global constraints and gate rubric
3. `docs/REFACTOR/ARCHITECT_PROMPT.md` — Architect operating guide
4. `docs/REFACTOR/PROJECT_MANAGERS_WORKFLOW.md` — Control sequence and merge policy
5. `AGENTS.md` + `.ayder/PROJECT_STRUCTURE.md` — Repo standards

---

## 3. Mission

Own phase gating and merge control for Phase 01. Review Developer and Tester MRs, enforce acceptance criteria, run mandatory commands, and issue PASS or REWORK_REQUIRED decision.

**Key Constraints:**
- Only Architect can authorize PASS/REWORK_REQUIRED
- Only Architect can merge gate branch to project branch
- No merge while any S1/S2 issue remains unresolved

---

## 4. Pre-Flight Checklist (Blockers)

Before beginning gate review, confirm:

- [ ] `PHASE_ID` and `ARCH_GATE_BRANCH` assigned
- [ ] Developer MR ready for review (`dev/01/baseline-inventory`)
- [ ] Tester MR ready for review (`qa/01/test-inventory`)
- [ ] Control Checks B and C passed (verified by PM)

If any check fails: STOP and request correction from PM.

---

## 5. Developer MR Review

**Source:** `dev/01/baseline-inventory`  
**Target:** `arch/01/baseline-gate`

**Deliverables to Review:**

| File | Purpose | Review Criteria |
|------|---------|-----------------|
| `docs/PROJECT/developer/01_PHASE/01_DEV_BASELINE_NOTES.md` | CLI/TUI flow verification | Accurate against source? Divergence documented? |
| `docs/PROJECT/developer/01_PHASE/01_DEV_RISK_ASSESSMENT.md` | Risk analysis | Aligned with architect risks? Mitigations actionable? |
| `src/ayder_cli/application/__init__.py` | Scaffold placeholder | No runtime wiring? Docstring appropriate? |
| `src/ayder_cli/application/README.md` | Scaffold documentation | Clear scope boundaries? |

**Verification Checklist:**
- [ ] No runtime behavior changes introduced
- [ ] Scaffolding only (no wiring)
- [ ] Baseline notes align with architect inventory
- [ ] Risk assessment covers R01-ASYNC, R02-MSG, R03-TEST

---

## 6. Tester MR Review

**Source:** `qa/01/test-inventory`  
**Target:** `arch/01/baseline-gate`

**Deliverables to Review:**

| File | Purpose | Review Criteria |
|------|---------|-----------------|
| `docs/PROJECT/tester/01_PHASE/01_TEST_INVENTORY.md` | Impacted test mapping | All 6 areas covered? Counts accurate? |
| `docs/PROJECT/tester/01_PHASE/01_OBSOLETE_TEST_CANDIDATES.md` | Removal candidates | Proper rationale? Replacement mapped? |
| `docs/PROJECT/tester/01_PHASE/01_CHARACTERIZATION_TESTS.md` | Baseline behavior tests | Required tests present and passing? |

**Verification Checklist:**
- [ ] Test inventory covers all impacted areas
- [ ] Obsolete candidates properly identified (awaiting approval)
- [ ] Characterization tests confirm baseline behavior
- [ ] No tests removed without approval

**Obsolete Test Candidates (Pending Your Approval):**

| Phase | Candidate Count | Primary Areas |
|-------|-----------------|---------------|
| Phase 02 | 5 | Message contract tests |
| Phase 04 | 10 | Tool execution, TUI loop internals |
| Phase 05 | 8 | Checkpoint flow divergence tests |

Approve early cleanup or defer to respective phases.

---

## 7. Gate Commands (Mandatory)

Run on `arch/01/baseline-gate` after merging both MRs:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

**Expected Results:**
- lint: All checks passed
- typecheck: Success, no issues
- test: 797+ passed, 5 skipped (or similar)

Record actual results in decision note.

---

## 8. Acceptance Criteria Verification

Per `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE.md`:

| Criterion | Verification Method | Status |
|-----------|---------------------|--------|
| Baseline inventory exists and is architect-approved | Review `01_BASELINE_INVENTORY.md` + `01_DEV_BASELINE_NOTES.md` | [ ] |
| Impacted test map exists with obsolete candidate list | Review `01_TEST_INVENTORY.md` + `01_OBSOLETE_TEST_CANDIDATES.md` | [ ] |
| Required gate commands pass | Run `lint`, `typecheck`, `test` | [ ] |
| No intentional runtime behavior change introduced | Diff review of all changes | [ ] |

All must pass for PASS decision.

---

## 9. Decision Protocol

### If Any S1/S2 Issues Found: **REWORK_REQUIRED**

- Return explicit rework list to Developer/Tester teams
- Do not merge to `main`
- Classification:
  - **S1 (Critical):** correctness/security regressions, broken acceptance criteria
  - **S2 (Major):** architectural boundary violations, major missing tests
  - **S3 (Minor):** non-blocking cleanup/documentation

### If All Criteria Satisfied: **PASS**

1. Merge Developer MR into `arch/01/baseline-gate`
2. Merge Tester MR into `arch/01/baseline-gate`
3. Re-run gate commands on gate branch
4. Open final MR: `arch/01/baseline-gate` → `main`
5. Merge to `main`
6. Publish decision note

---

## 10. Required Phase Decision Note

Publish to: `docs/REFACTOR/PHASES/01_PHASE_BASELINE_AND_GOVERNANCE_ARCHITECT_DECISION.md`

**Template:**
```markdown
# Architect Decision — Phase 01

**Phase ID:** 01_PHASE_BASELINE_AND_GOVERNANCE  
**Date:** YYYY-MM-DD  
**Decision:** PASS / REWORK_REQUIRED

## Acceptance Criteria Checklist

- [ ] Baseline inventory exists and is architect-approved
- [ ] Impacted test map exists with obsolete candidate list
- [ ] Required gate commands pass
- [ ] No intentional runtime behavior change introduced

## Command Results

```
uv run poe lint        → [result]
uv run poe typecheck   → [result]
uv run poe test        → [result]
```

## Rework Items (if REWORK_REQUIRED)

| Severity | Item | Owner |
|----------|------|-------|
| S1/S2/S3 | [description] | Developer/Tester |

## Merge Record

- Developer MR: [commit/merge ref]
- Tester MR: [commit/merge ref]
- Final MR: `arch/01/baseline-gate` → `main` [MR ref]
```

---

## 11. Control Check D (PM Validation Required)

Before phase closure, PM will verify:

- [ ] Architect reviewed all MRs
- [ ] Architect ran required commands (`lint`, `typecheck`, `test`)
- [ ] Architect published PASS or REWORK_REQUIRED decision note

If PASS:
- [ ] Architect merged `arch/01/baseline-gate` → `main`
- [ ] PM marks phase complete and unlocks next phase

If REWORK_REQUIRED:
- [ ] PM opens rework tickets (DEV/QA) with severity labels (S1/S2/S3)
- [ ] PM loops back to Step B and/or Step C, then Step D again

---

## 12. Done Definition

Done only when:
- [ ] Developer and Tester MRs reviewed
- [ ] Gate commands run and results recorded
- [ ] Decision (PASS or REWORK_REQUIRED) published
- [ ] If PASS: gate branch merged to `main`
- [ ] If REWORK_REQUIRED: actionable tickets issued to teams

---

*Phase 01 Step D — Architect Gate Assignment*
