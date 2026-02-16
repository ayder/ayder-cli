# Phase 01 — Baseline and Governance Setup

## Phase Goal

Establish a controlled baseline before architectural change:

- shared understanding of current behavior,
- test migration plan,
- gate process and artifacts.

## Dependencies

- `00_PRD_MASTER.md` approved by Architects.

---

## Phase Spec (Behavior Contract)

This phase must not introduce intentional runtime behavior changes.  
It prepares governance, inventory, and baseline checks only.

---

## Developer Tasks

### DEV-01.1 Baseline Inventory
- Document current key flows and file ownership:
  - CLI orchestration path
  - TUI orchestration path
  - checkpoint flow in both paths
  - tool execution path in both paths
- Produce inventory artifact for Architect review.

### DEV-01.2 Refactor Workspace Scaffolding
- Create/confirm target module placeholders (no behavior wiring yet):
  - `src/ayder_cli/application/` package marker(s)
- Keep imports untouched in runtime paths during this phase.

### DEV-01.3 Risk Register
- Provide a concise risk list:
  - async migration risk
  - message shape risk
  - test break risk
- Include mitigation proposal per risk.

---

## Tester Tasks (Parallel)

### QA-01.1 Test Inventory and Mapping
- Build test map for impacted areas:
  - `tests/services/tools/test_executor.py`
  - `tests/services/test_llm*.py`
  - `tests/ui/test_tui_chat_loop.py`
  - `tests/test_memory.py`
  - `tests/test_checkpoint_manager.py`
  - `tests/test_cli.py`

### QA-01.2 Obsolete-Test Candidate List
- Identify tests likely tied to internals expected to change.
- Do not remove yet unless Architect approves early cleanup.

### QA-01.3 Baseline Characterization Tests
- Add/confirm characterization tests for current behavior:
  - CLI command run path basic success
  - TUI chat loop basic success
  - checkpoint read/write smoke

---

## Architect Tasks (Gate)

### ARC-01.1 Baseline Review
- Validate inventory completeness and correctness.
- Confirm no unapproved behavioral changes.

### ARC-01.2 Command Gate
Run:
```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

### ARC-01.3 Sign-off Decision
- PASS if baseline + governance artifacts complete and checks pass.
- REWORK_REQUIRED with explicit DEV/QA ticket list otherwise.

---

## Acceptance Criteria

- Baseline inventory exists and is architect-approved.
- Impacted test map exists with obsolete candidate list.
- Required gate commands pass.
- No intentional runtime behavior change introduced.

---

## Exit Artifacts

- Baseline inventory
- Test migration map (initial)
- Architect gate note (PASS/REWORK_REQUIRED)
