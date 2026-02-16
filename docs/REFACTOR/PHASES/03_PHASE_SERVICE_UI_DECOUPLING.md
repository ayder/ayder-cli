# Phase 03 — Service/UI Decoupling

## Phase Goal

Remove direct service-layer dependencies on presentation modules and replace them with explicit interfaces/adapters.

## Dependencies

- Phase 02 PASS.

---

## Phase Spec (Behavior Contract)

1. `services/*` modules must not import `ui.py` directly.
2. Tool execution confirmations and output notifications must flow through explicit interfaces.
3. CLI/TUI output behavior remains functionally equivalent.

---

## Developer Tasks

### DEV-03.1 Define Interaction Interfaces
- Introduce interfaces/protocols for:
  - event sink / notification
  - confirmation policy for tool execution

### DEV-03.2 Refactor Tool Executor
- Update `src/ayder_cli/services/tools/executor.py`:
  - remove direct imports from `ayder_cli.ui`
  - inject interaction interfaces via constructor
  - keep existing execution semantics

### DEV-03.3 Refactor LLM Verbose Reporting
- Update `src/ayder_cli/services/llm.py`:
  - remove direct `ui.py` debug print dependency in provider classes
  - use interface-driven event/debug hooks

### DEV-03.4 Provide Adapters
- Provide CLI adapter implementation mapped to current Rich output behavior.
- Provide TUI adapter implementation mapped to TUI callbacks.

---

## Tester Tasks (Parallel)

### QA-03.1 Remove Obsolete Service/UI-Coupled Tests
- Remove tests tightly mocking direct `ui.py` imports inside services.
- Replace with interface-driven unit tests.

### QA-03.2 Add Executor Interface Tests
- Add tests with fake/stub confirmation + event sink.
- Verify:
  - permission behavior
  - confirmation flow
  - tool result propagation

### QA-03.3 Add Architecture Guard Test
- Add a boundary test that fails if service modules import `ayder_cli.ui` directly.

---

## Architect Tasks (Gate)

### ARC-03.1 Boundary Review
- Confirm service layer is presentation-agnostic.
- Confirm adapters are in entry/presentation side, not services.

### ARC-03.2 Static Boundary Check
Run:
```bash
rg "from ayder_cli\\.ui import|import ayder_cli\\.ui" src/ayder_cli/services
```
Expected: no matches.

### ARC-03.3 Command Gate
Run:
```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

---

## Acceptance Criteria

- No direct service → `ui.py` imports remain.
- Executor and provider tests are interface-based.
- CLI/TUI output/confirmation behavior remains equivalent.
- Architect PASS with no open S1/S2 issues.

---

## Exit Artifacts

- Service/UI decoupling report
- Updated remove→replace test mapping
- Architect gate note (PASS/REWORK_REQUIRED)
