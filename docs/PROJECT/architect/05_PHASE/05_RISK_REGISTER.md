# Phase 05 Risk Register

| Risk ID | Risk | Severity | Current Evidence | Mitigation Plan | Verification |
|---------|------|----------|------------------|-----------------|--------------|
| R05-CHK-DIVERGENCE | CLI and TUI checkpoint behavior stays divergent after refactor | High | CLI checkpoint flow is in `chat_loop.py`; TUI has separate inline checkpoint flow in `tui/chat_loop.py` | Move checkpoint policy into one shared application service; make both surfaces delegate | Parity tests confirm equivalent trigger/reset/restore behavior across CLI/TUI |
| R05-EXEC-BYPASS | TUI keeps direct `registry.execute(...)` path, bypassing shared execution policy | High | TUI loop currently executes tools directly in async helper methods | Route both interfaces through shared execution orchestration path | Search + tests confirm no core bypass path remains |
| R05-VALIDATION-DRIFT | Validation runs in multiple layers with conflicting outcomes | High | Tool validation exists in `ToolExecutor`; divergent wrapper logic risks duplicate/conflicting checks | Define single validation authority path and remove redundant checks | Validation-path tests assert stable, single-source errors |
| R05-STATE-TRANSITION | Reset/restore sequence differs between interfaces causing inconsistent continuation | Medium | CLI and TUI currently maintain independent checkpoint state transitions | Define and enforce deterministic transition contract in shared orchestrator | State transition tests cover restore-existing and create-new flows |
| R05-TEST-ORDER | DEV implementation starts before QA parity contracts are locked | Medium | Phase requires convergence assertions that are easy to misinterpret without contract tests first | Enforce strict test-first order in kickoff briefing and gate reviews | QA-first evidence and failing-then-passing contract tests present at gate |

## Carry-Over Context

- Phase 04 is PASS and remains a hard dependency for Phase 05 start.

## Phase 05 Exit Expectation

Phase 05 cannot be architect-approved with open S1/S2 issues in:

- checkpoint parity across CLI/TUI
- execution policy parity across CLI/TUI
- validation centralization and error consistency
