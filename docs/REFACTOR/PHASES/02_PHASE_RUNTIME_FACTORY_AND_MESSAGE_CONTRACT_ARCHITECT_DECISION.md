# Architect Decision — Phase 02

**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Date:** 2026-02-16  
**Decision:** **REWORK_REQUIRED**

## Acceptance Criteria Checklist

- [x] One shared runtime factory used by both CLI and TUI
- [x] Message normalization integrated to prevent dict/object regressions in target paths
- [ ] Required tests exist and pass
- [ ] No open S1/S2 issues

## Acceptance Verification Notes

- Developer MR reviewed and merged to gate:
  - `src/ayder_cli/application/runtime_factory.py`
  - `src/ayder_cli/application/message_contract.py`
  - CLI/TUI wiring + integration files (`cli_runner.py`, `tui/app.py`, `memory.py`, `tui/chat_loop.py`, `tui/commands.py`)
  - developer tests (`tests/test_runtime_factory.py`, `tests/test_message_contract.py`)
- Tester MR reviewed and merged to gate:
  - `docs/PROJECT/tester/02_PHASE/02_TEST_MIGRATION_MAPPING.md`
  - acceptance-oriented suites in `tests/application/`
- ARC-02.1 architecture review result:
  - duplicated composition root in CLI removed in favor of shared factory delegation
  - TUI adopts shared factory for core runtime dependencies
  - no Phase 04 async-loop convergence work introduced

## Command Results

```bash
uv run poe lint      → PASS (ruff: all checks passed)
uv run poe typecheck → PASS (mypy: success, no issues in 59 files)
uv run poe test      → FAIL (stopped at tests/application/test_message_contract.py::TestToMessageDict::test_to_message_dict_from_dict)
```

Supplementary verification:

```bash
uv run pytest tests/test_runtime_factory.py tests/test_message_contract.py -q --timeout=60
→ PASS (21 passed)

uv run pytest tests/application/test_runtime_factory.py tests/application/test_message_contract.py -q --timeout=60
→ FAIL (5 failed, 39 passed)
```

## Test Suite Consolidation Decision

**Chosen Option:** **A — Keep Both**

**Rationale:**
- Developer suite (`tests/test_*.py`) provides quick unit-level validation for implementation iteration.
- Tester suite (`tests/application/test_*.py`) provides broader acceptance coverage and migration evidence.
- Keeping both preserves layered validation depth; consolidation adds churn without immediate benefit.

**Actions Taken:**
- No test suite removal/consolidation performed in this gate.
- Rework required to make the tester acceptance suite green and aligned with runtime/message contract behavior.

## Rework Items

| Severity | Item | Owner |
|----------|------|-------|
| S2 | Fix `tests/application/test_runtime_factory.py` path assertions to match `ProjectContext.root` (`Path`, not raw string comparisons). | Tester |
| S2 | Update `tests/application/test_runtime_factory.py::test_tui_uses_factory_components` patch targets to current factory-based wiring (no longer patches removed symbols in `tui/app.py`). | Tester |
| S2 | Relax `tests/application/test_message_contract.py::test_to_message_dict_from_dict` identity assertion (`is`) to contract-aligned value checks. | Tester |
| S2 | Harden `get_message_tool_calls()` to guarantee list output for object messages with non-list/Mock-like `tool_calls` values. | Developer |
| S3 | Clean invalid fixture literal in tester suite (`"assistant9;00m"`) and normalize message-role test data. | Tester |

## Merge Record

- Developer MR source branch: `dev/02/runtime-factory`
  - merged into gate branch via commit: `d9c7edd`
- Tester MR source branch: `qa/02/factory-contract-tests`
  - merged into gate branch via commit: `9a6e7e0`
- Final MR path: `arch/02/runtime-factory-gate` → `main`
  - **Not merged (REWORK_REQUIRED)**
