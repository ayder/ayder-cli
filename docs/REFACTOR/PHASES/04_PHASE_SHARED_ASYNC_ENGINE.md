# Phase 04 — Shared Async Engine (CLI + TUI)

## Phase Goal

Implement one shared async orchestration engine used by both CLI and TUI.

## Dependencies

- Phase 03 PASS.

---

## Phase Spec (Behavior Contract)

1. There is one shared async orchestration implementation for both interfaces.
2. CLI invokes this async engine via `asyncio.run(...)`.
3. TUI awaits the same engine in worker lifecycle.
4. Any legacy sync loop is wrapper-only (or removed), not source-of-truth logic.

---

## Developer Tasks

### DEV-04.1 Build Shared Async Engine
- Introduce `src/ayder_cli/application/agent_engine.py` (target naming may vary).
- Move core orchestration logic here:
  - iteration control
  - llm call loop
  - tool call routing
  - checkpoint trigger integration

### DEV-04.2 CLI Integration
- Update CLI path to call shared async engine with `asyncio.run(...)`.
- Keep CLI UX and output formatting behavior stable.

### DEV-04.3 TUI Integration
- Update TUI path to await the same async engine from worker context.
- Preserve cancellation handling and callback behavior.

### DEV-04.4 Legacy Loop Handling
- Convert old sync loop modules to thin compatibility wrappers or remove dead logic.
- Ensure no duplicated orchestration logic remains.

---

## Tester Tasks (Parallel)

### QA-04.1 Remove Obsolete Loop Tests
- Remove tests that only validate deprecated sync-loop internals.
- Add explicit replacement references.

### QA-04.2 Add Shared Engine Tests
- Add unit tests for async engine behavior:
  - text-only response
  - tool-call response
  - iteration overflow path
  - cancellation path (where applicable)

### QA-04.3 Add Wrapper Contract Tests
- Verify CLI wrapper calls shared async engine via `asyncio.run`.
- Verify TUI wrapper awaits the same async engine.

### QA-04.4 Add Equivalence Tests
- Given same mocked LLM/tool responses, assert same decision outcomes in CLI and TUI pathways.

---

## Architect Tasks (Gate)

### ARC-04.1 Architecture Review
- Confirm single async engine is source of orchestration truth.
- Confirm CLI and TUI are wrappers around same engine.

### ARC-04.2 Code Search Validation
Run checks to ensure no duplicate orchestration core remains in legacy loops.

### ARC-04.3 Command Gate
Run:
```bash
uv run poe lint
uv run poe typecheck
uv run poe test
uv run poe test-all
```

---

## Acceptance Criteria

- One shared async orchestration implementation is used by CLI and TUI.
- No separate sync orchestration loop remains as primary logic.
- Async engine tests + wrapper tests pass.
- Architect PASS with no open S1/S2 issues.

---

## Exit Artifacts

- Shared async engine design note
- Loop migration test report (removed/replaced)
- Architect gate note (PASS/REWORK_REQUIRED)
