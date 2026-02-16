# Phase 06 Architecture Design — Stabilization and Final Sign-off

## Scope and Objective

Phase 06 finalizes the refactor program by:

1. removing obsolete legacy orchestration leftovers
2. stabilizing public/internal contracts without behavior drift
3. completing architecture documentation and handoff notes

Dependency: Phase 05 PASS is required and already satisfied.

---

## Development/Testing Strategy Decision

Phase 06 runs with a **parallel DEV+QA strategy** (not strict test-first):

- DEV executes stabilization and cleanup implementation tasks.
- QA executes final regression and obsolete test migration in parallel.
- QA owns broad test/mocking redesign and final hardening.
- DEV may add only minimal wiring/proof tests directly tied to implementation.

### Guardrails

1. No destructive cleanup without QA remove->replace mapping.
2. Public behavior remains stable while internals are cleaned.
3. Shared async architecture convergence from prior phases must remain intact.
4. Any S1/S2 findings at gate force REWORK_REQUIRED.

---

## Phase 06 Technical Boundaries

### Legacy Path Cleanup

- Remove inactive compatibility layers and dead orchestration paths.
- Ensure no stale legacy route remains an active execution path.

### Contract Cleanup

- Remove duplicate/stale internal abstractions.
- Keep CLI/TUI observable behavior stable.

### Documentation Finalization

- Update final architecture notes to match delivered runtime wiring.
- Record maintainers' migration/handoff notes.

---

## Acceptance Mapping Checklist

- [ ] No active legacy orchestration conflicts remain.
- [ ] Test suite reflects final architecture and no removed-internal coupling remains.
- [ ] Architecture docs and handoff notes are complete.
- [ ] `uv run poe check-all` passes.
- [ ] `uv run poe test-all` passes.
- [ ] Architect gate closes with no open S1/S2 issues.

