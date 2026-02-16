# Phase 06 — Stabilization, Cleanup, and Final Sign-off

## Phase Goal

Finalize refactor by removing obsolete leftovers, hardening tests, and obtaining final architectural sign-off.

## Dependencies

- Phase 05 PASS.

---

## Phase Spec (Behavior Contract)

1. No stale/dead legacy orchestration code remains as active path.
2. Test suite reflects new architecture and no longer depends on removed internals.
3. Architecture docs and team handoff notes are complete.

---

## Developer Tasks

### DEV-06.1 Legacy Cleanup
- Remove or deprecate dead compatibility layers no longer needed.
- Resolve low-risk boundary leaks left from previous phases.

### DEV-06.2 API/Internal Contract Cleanup
- Remove stale interfaces and duplicate abstractions.
- Keep public behavior stable.

### DEV-06.3 Documentation Finalization
- Update architecture documentation to match final implementation.
- Add migration notes for maintainers.

---

## Tester Tasks (Parallel)

### QA-06.1 Final Obsolete Test Removal
- Remove remaining obsolete tests tied to removed code paths.
- Ensure remove→replace mapping is complete and archived.

### QA-06.2 Regression Matrix
- Execute full regression plan:
  - CLI workflows
  - TUI workflows
  - checkpoint/memory workflows
  - tool execution and permissions

### QA-06.3 Final Suite Hardening
- Close flaky tests.
- Ensure deterministic async test behavior.

---

## Architect Tasks (Gate)

### ARC-06.1 Final Architecture Review
- Validate final architecture against PRD constraints:
  - shared async loop
  - decoupled services
  - converged behavior

### ARC-06.2 Final Command Gate
Run:
```bash
uv run poe check-all
uv run poe test-all
```

### ARC-06.3 Program Sign-off
- PASS only when all final exit criteria are satisfied.
- Publish final sign-off note and any deferred backlog items.

---

## Acceptance Criteria

- No active legacy orchestration conflicts remain.
- Final tests and checks pass.
- Documentation reflects delivered architecture.
- Architect final PASS issued.

---

## Exit Artifacts

- Final remove→replace test ledger
- Final architecture sign-off note
- Deferred backlog list (if any, non-blocking only)
