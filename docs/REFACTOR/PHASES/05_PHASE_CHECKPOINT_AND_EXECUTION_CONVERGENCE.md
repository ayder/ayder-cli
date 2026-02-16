# Phase 05 — Checkpoint and Execution Convergence

## Phase Goal

Converge CLI and TUI behavior for checkpoint and tool execution policies so they are consistent and testable.

## Dependencies

- Phase 04 PASS.

---

## Phase Spec (Behavior Contract)

1. CLI and TUI use the same checkpoint orchestration policy.
2. CLI and TUI use the same tool execution policy path (confirmation/permissions/error semantics).
3. Duplicate validation or conflicting validation layers are removed or explicitly centralized.

---

## Developer Tasks

### DEV-05.1 Shared Checkpoint Service
- Introduce a shared checkpoint orchestration service used by the async engine.
- Keep storage details in checkpoint manager/storage primitives.

### DEV-05.2 Execution Path Convergence
- Remove direct TUI bypass execution paths that call tool registry directly for core operations.
- Route both interfaces through shared execution orchestration.

### DEV-05.3 Validation Centralization
- Resolve duplicate normalization/validation across tool execution stack.
- Define single authority for schema validation and keep it consistent.

### DEV-05.4 State Transition Safety
- Ensure checkpoint reset/restore state transitions are deterministic and equivalent across interfaces.

---

## Tester Tasks (Parallel)

### QA-05.1 Remove Obsolete Divergent-Path Tests
- Remove tests that intentionally lock in old CLI/TUI divergence.
- Replace with convergence assertions.

### QA-05.2 Add Checkpoint Parity Tests
- Assert same checkpoint trigger and reset behavior in CLI and TUI for equivalent scenarios.

### QA-05.3 Add Execution Policy Parity Tests
- Confirm parity on:
  - permission-denied behavior
  - user confirmation behavior
  - error propagation format

### QA-05.4 Add Validation Path Tests
- Assert validation is not redundantly applied in conflicting ways.
- Verify expected validation errors remain user-visible and stable.

---

## Architect Tasks (Gate)

### ARC-05.1 Convergence Review
- Verify checkpoint and tool policy parity across interfaces.
- Ensure no hidden bypass path undermines convergence.

### ARC-05.2 Command Gate
Run:
```bash
uv run poe lint
uv run poe typecheck
uv run poe test
uv run poe test-all
```

### ARC-05.3 Rework Decision
- Any parity mismatch is S1/S2 and blocks phase PASS.

---

## Acceptance Criteria

- Shared checkpoint behavior across CLI/TUI is verified by tests.
- Shared tool execution policy across CLI/TUI is verified by tests.
- Validation authority is centralized and documented.
- Architect PASS with no open S1/S2 issues.

---

## Exit Artifacts

- Checkpoint convergence report
- Execution policy convergence report
- Architect gate note (PASS/REWORK_REQUIRED)
