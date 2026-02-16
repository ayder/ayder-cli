# Phase 05 Architecture Design — Checkpoint and Execution Convergence

## Scope and Objective

Phase 05 converges CLI and TUI behavior so both interfaces enforce the same:

1. checkpoint orchestration policy
2. tool execution policy (permissions, confirmation, error semantics)
3. validation authority

This phase builds on Phase 04 PASS and targets parity guarantees instead of
surface-specific behavior drift.

---

## Current Divergence Snapshot

### Checkpoint Handling

- **CLI path**: `Agent -> ChatLoop._handle_checkpoint()` delegates to
  `MemoryManager` + `CheckpointManager`.
- **TUI path**: `TuiChatLoop._handle_checkpoint()` performs its own checkpoint
  orchestration inline.

### Tool Execution Handling

- **CLI path**: `ChatLoop -> ToolExecutor` (normalize -> validate -> confirm ->
  execute).
- **TUI path**: `TuiChatLoop` executes tools through direct
  `registry.execute(...)` calls in async helpers and applies separate
  confirmation logic.

This divergence is exactly what Phase 05 must remove.

---

## Target Convergence Contracts

### Contract 1 — Shared Checkpoint Orchestration

Introduce a shared checkpoint orchestration service in the application layer
and route both CLI and TUI iteration-limit flows through it.

Requirements:
- deterministic checkpoint decision path (restore-existing vs create-new)
- identical reset/restore state transitions across interfaces
- no duplicated checkpoint policy logic in wrappers

### Contract 2 — Shared Tool Execution Policy Path

All tool calls in both interfaces must use the same execution policy path.

Requirements:
- no direct TUI bypass path for core tool execution
- parity on permission-denied behavior
- parity on confirmation/denial behavior
- parity on tool error formatting/propagation

### Contract 3 — Validation Centralization

Validation authority must be explicit and singular.

Requirements:
- normalization + validation happen once in one authority path
- no conflicting secondary validation layer in wrappers
- user-visible validation errors remain stable

### Contract 4 — State Transition Safety

Checkpoint reset/restore and post-tool continuation transitions must be
deterministic and equivalent in CLI and TUI flows.

---

## TEST-FIRST Execution Directive (Mandatory)

Phase 05 is **STRICTLY TEST-FIRST**:

1. QA defines parity and convergence tests first.
2. DEV implements only against QA-defined contracts.
3. Architect gate blocks PASS if ordering or parity evidence is missing.

---

## Acceptance Mapping Checklist

- [ ] Shared checkpoint behavior parity tests exist and pass.
- [ ] Shared tool execution policy parity tests exist and pass.
- [ ] Validation authority is centralized and documented.
- [ ] No CLI/TUI bypass path undermines convergence.
- [ ] No open S1/S2 issues at architect gate.
