# Architect Decision — Phase 02

**Phase ID:** 02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT  
**Date:** 2026-02-16  
**Decision:** PASS

## Acceptance Criteria Checklist

- [x] One shared runtime factory used by both CLI and TUI
- [x] Message normalization prevents dict/object shape regressions
- [x] Required tests exist and pass
- [x] No open S1/S2 issues

## Command Results

```
uv run poe lint        → All checks passed!
uv run poe typecheck   → Success: no issues found in 59 source files
uv run poe test        → 862 passed, 5 skipped
```

## Test Suite Consolidation Decision

**Chosen Option:** A — Keep Both

**Rationale:**
Developer tests (`tests/test_*.py`) provide quick unit test coverage for factory and contract internals. Tester tests (`tests/application/test_*.py`) provide comprehensive acceptance coverage including integration points. Both suites add complementary value and can coexist.

**Actions Taken:** None — both test suites retained as-is.

## Rework Items

None. No S1, S2, or S3 issues identified.

## Merge Record

- Developer MR: `dev/02/runtime-factory` → `arch/02/runtime-factory-gate` (`e5a2c1d`)
- Tester MR: `qa/02/factory-contract-tests` → `arch/02/runtime-factory-gate` (`f8b3d9a`)
- Test consolidation: N/A (Option A — no consolidation needed)
- Final MR: `arch/02/runtime-factory-gate` → `main` (`c7d9e2f`)

## Architecture Summary

### Runtime Factory
- Module: `src/ayder_cli/application/runtime_factory.py`
- Interface: `create_runtime(*, config, project_root, model_name) -> RuntimeComponents`
- Components: 9 (config, llm_provider, process_manager, project_ctx, tool_registry, tool_executor, checkpoint_manager, memory_manager, system_prompt)
- CLI Integration: `cli_runner.py::_build_services()` delegates to factory
- TUI Integration: `tui/app.py::AyderApp.__init__()` uses factory

### Message Contract
- Module: `src/ayder_cli/application/message_contract.py`
- Helpers: `get_message_role`, `get_message_content`, `get_message_tool_calls`, `to_message_dict`
- Integration Points:
  - `memory.py::_build_conversation_summary()`
  - `tui/chat_loop.py::_handle_checkpoint()`
  - `tui/commands.py::handle_compact()`, `handle_save_memory()`, `do_clear()`

### Test Coverage
- Total Tests: 862 (797 baseline + 65 new)
- New Tests:
  - Developer: 21 unit tests
  - Tester: 44 acceptance tests

---

*Phase 02 Gate Decision — APPROVED*
