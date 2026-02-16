# Project Managers Workflow — Refactor Program Coordination

This workflow defines how Project Managers coordinate Developer, Tester, and Architect teams phase-by-phase with strict control checks.

## Scope

- Applies to all refactor phases in `docs/REFACTOR/PHASES/`.
- Enforces prompt assignment order:
  1. **Architect**
  2. **Developer**
  3. **Tester**
  4. **Architect**

## Source Prompts

- PM prompt: `docs/REFACTOR/PROJECT_MANAGER_PROMPT.md`
- Architect prompt: `docs/REFACTOR/ARCHITECT_PROMPT.md`
- Developer prompt: `docs/REFACTOR/DEVELOPER_PROMPT.md`
- Tester prompt: `docs/REFACTOR/TESTER_PROMPT.md`
- Master PRD: `docs/REFACTOR/PHASES/00_PRD_MASTER.md`

## Team Resource Map (If in Doubt)

PM should direct teams to these resources immediately:

- **Developers**
  1. `PHASE_DOC`
  2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md`
  3. `docs/REFACTOR/DEVELOPER_PROMPT.md`
  4. `AGENTS.md` and `.ayder/PROJECT_STRUCTURE.md`

- **Testers**
  1. `PHASE_DOC`
  2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md`
  3. `docs/REFACTOR/TESTER_PROMPT.md`
  4. Existing tests under `tests/` and `AGENTS.md` test standards

- **Architects**
  1. `PHASE_DOC`
  2. `docs/REFACTOR/PHASES/00_PRD_MASTER.md`
  3. `docs/REFACTOR/ARCHITECT_PROMPT.md`
  4. Team MR evidence + command outputs

If ambiguity remains, PM must issue a written clarification note before work proceeds.

---

## 1) Standard Git Workflow Model

For each phase (`PHASE_ID`):

- Project branch: `<PROJECT_BRANCH>`
- Architect gate branch: `arch/<PHASE_ID>/gate`
- Developer work branch: `dev/<PHASE_ID>/<TASK_SCOPE>`
- Tester work branch: `qa/<PHASE_ID>/<TEST_SCOPE>`

Merge path:

1. `dev/*` MR -> `arch/<PHASE_ID>/gate`
2. `qa/*` MR -> `arch/<PHASE_ID>/gate`
3. Architect final MR: `arch/<PHASE_ID>/gate` -> `<PROJECT_BRANCH>`

No direct Developer/Tester merges to `<PROJECT_BRANCH>`.

---

## 2) PM Step-by-Step Assignment Order (Mandatory)

## Step A — Assign Architect (Kickoff)

PM assigns `ARCHITECT_PROMPT.md` first with:

- `PHASE_ID`
- `PHASE_DOC`
- `PROJECT_BRANCH`
- `ARCH_GATE_BRANCH = arch/<PHASE_ID>/gate`
- empty MR list placeholders

### PM Check Control A (must pass before Step B)

- [ ] Architect created/refreshed gate branch.
- [ ] Architect published phase kickoff note:
  - scope boundaries
  - acceptance checklist
  - phase risks
- [ ] Architect confirmed dependency from prior phase is PASS.

If any item fails, PM blocks phase start.

---

## Step B — Assign Developer

After Step A passes, PM assigns `DEVELOPER_PROMPT.md` with:

- `PHASE_ID`, `PHASE_DOC`
- `PROJECT_BRANCH`
- `ARCH_GATE_BRANCH`
- `TASK_SCOPE`

### PM Check Control B (must pass before Step C)

- [ ] Developer branch `dev/<PHASE_ID>/<TASK_SCOPE>` exists.
- [ ] Developer confirms DEV tasks in scope (`DEV-*`) from phase doc.
- [ ] Developer posted implementation plan + expected changed files.

If scope is unclear, PM sends it back before coding continues.

---

## Step C — Assign Tester

After Step B passes, PM assigns `TESTER_PROMPT.md` with:

- `PHASE_ID`, `PHASE_DOC`
- `PROJECT_BRANCH`
- `ARCH_GATE_BRANCH`
- `TEST_SCOPE`

### PM Check Control C (must pass before Step D)

- [ ] Tester branch `qa/<PHASE_ID>/<TEST_SCOPE>` exists.
- [ ] Tester posted remove→replace test migration plan.
- [ ] Tester listed targeted acceptance-criteria tests for this phase.

If test migration mapping is missing, PM blocks gate request.

---

## Step D — Re-Assign Architect (Gate + Merge Decision)

PM returns to Architect with:

- Developer MR(s) list
- Tester MR(s) list
- phase acceptance checklist

Architect performs review, runs gate commands, and returns PASS or REWORK_REQUIRED.

### PM Check Control D (Final Gate)

- [ ] Architect reviewed all phase MRs.
- [ ] Architect ran required commands:
  - `uv run poe lint`
  - `uv run poe typecheck`
  - `uv run poe test`
  - `uv run poe test-all` (if phase requires)
- [ ] Architect published decision note (PASS/REWORK_REQUIRED).

If PASS:
- [ ] Architect merged gate branch to `<PROJECT_BRANCH>`.
- [ ] PM marks phase complete and unlocks next phase.

If REWORK_REQUIRED:
- [ ] PM logs S1/S2/S3 rework tasks and reassigns to Developer/Tester.
- [ ] Return to Step B or C as needed, then back to Step D.

---

## 3) Rework Loop Control

When Architect returns REWORK_REQUIRED:

1. PM splits feedback into DEV and QA actionable tickets.
2. PM sets severity and owner:
   - S1 critical -> immediate
   - S2 major -> blocking
   - S3 minor -> may defer only if Architect approves
3. PM tracks closure evidence per ticket (commit/MR/test proof).
4. PM requests Architect re-gate only after all S1/S2 are resolved.

---

## 4) Phase Tracking Template (PM Copy/Paste)

Use this per phase:

```md
## Phase <PHASE_ID> Tracker

### Inputs
- Phase doc:
- Project branch:
- Architect gate branch:

### Step A — Architect Kickoff
- Status:
- Evidence link:

### Step B — Developer Assigned
- Branch:
- MR:
- Status:

### Step C — Tester Assigned
- Branch:
- MR:
- Remove→Replace mapping:
- Status:

### Step D — Architect Gate
- Gate commands result:
- Decision: PASS / REWORK_REQUIRED
- Decision note link:

### Final
- Merged to project branch: Yes/No
- Next phase unlocked: Yes/No
```

---

## 5) PM Acceptance Checklist Per Phase

A phase is closed only when all are true:

- [ ] Assignment order followed: Architect -> Developer -> Tester -> Architect.
- [ ] Developer MR merged to gate branch.
- [ ] Tester MR merged to gate branch.
- [ ] Architect gate decision is PASS.
- [ ] Gate branch merged to project branch.
- [ ] Decision and evidence archived.

---

## 6) Operational Notes

- Keep communication and evidence in MR descriptions and phase decision notes.
- Never skip Architect kickoff or final Architect gate.
- For async-loop phases, PM must explicitly verify the acceptance criterion:
  - CLI and TUI use the same async engine; no separate sync orchestration source-of-truth.
