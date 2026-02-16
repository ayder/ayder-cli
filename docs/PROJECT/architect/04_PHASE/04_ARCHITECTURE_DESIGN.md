# Phase 04 Architecture Design — Shared Async Engine

## Scope and Objective

Phase 04 establishes one shared async orchestration engine as the single
source-of-truth for both CLI and TUI conversation execution.

Goal:

1. Move orchestration flow into a shared async engine module.
2. Make CLI and TUI wrappers over the same engine.
3. Ensure any legacy sync loop is wrapper-only and not primary logic.

---

## Canonical Engine Boundary

### Source-of-Truth Module

- `src/ayder_cli/application/agent_engine.py`

This module owns orchestration responsibilities:

- iteration control
- LLM request/response loop
- tool call routing
- checkpoint trigger integration
- stop/cancel propagation

No duplicated orchestration logic may remain in CLI/TUI-specific loops.

---

## Interface Usage Contract

Both surfaces must use the same async engine entrypoint:

- CLI wrapper invokes engine through `asyncio.run(...)`.
- TUI worker awaits the same engine coroutine within worker lifecycle.

Wrapper responsibilities are limited to surface concerns:

- CLI: argument/session setup and terminal output hooks.
- TUI: worker lifecycle, cancellation bridge, UI callback plumbing.

---

## Legacy Loop Policy

- Legacy sync loop code may remain only as compatibility wrappers.
- Wrapper code must delegate orchestration decisions to the shared engine.
- Any in-wrapper duplicate orchestration branch is out-of-scope and blocking.

---

## Test-First Execution Contract

Phase 04 is **strictly TEST-FIRST**:

1. QA defines shared-engine and wrapper contract tests first.
2. DEV implementation is permitted only against those QA-defined tests.
3. Architect gate verifies shared-engine source-of-truth and parity outcomes.

Recommended required test coverage for this phase:

- async engine text-only path
- async engine tool-call path
- iteration overflow/termination behavior
- cancellation behavior
- CLI wrapper `asyncio.run(...)` contract
- TUI wrapper `await` contract
- CLI/TUI equivalence outcomes under identical mocked inputs

---

## Acceptance Mapping

Phase 04 implementation can be architect-approved only when all are true:

- one shared async orchestration implementation is used by CLI and TUI
- CLI wrapper uses `asyncio.run(...)` to invoke shared engine
- TUI wrapper awaits the same shared engine in worker lifecycle
- legacy sync loop is wrapper-only (or removed) and not source-of-truth
- no open S1/S2 issues remain at gate

