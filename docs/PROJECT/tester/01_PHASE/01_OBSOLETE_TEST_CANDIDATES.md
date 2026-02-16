# Obsolete Test Candidates — Phase 01

**Phase ID:** `01_PHASE_BASELINE_AND_GOVERNANCE`  
**Generated:** 2026-02-16  
**Branch:** `qa/01/test-inventory`  
**Status:** PENDING ARCHITECT APPROVAL

---

## Overview

This document identifies test candidates that are likely to become obsolete during the refactor phases. **No tests should be removed without explicit Architect approval**, per the Test Migration Policy in `docs/REFACTOR/PHASES/00_PRD_MASTER.md`.

---

## Candidate List (Pending Architect Approval)

### Phase 04 Candidates (Shared Async Engine)

| Test File | Test Name(s) | Reason Obsolete | Replacement Plan |
|-----------|--------------|-----------------|------------------|
| `tests/services/tools/test_executor.py` | `TestToolExecutor::test_handle_tool_call*` | Tests sync ToolExecutor internal methods; async engine will use different execution model | Replace with behavior characterization tests for async tool execution contract |
| `tests/services/tools/test_executor.py` | `TestToolExecutor::test_execute_tool_calls_*` | Tests sync batch execution; async engine uses parallel/sequential strategy | Replace with async execution flow tests |
| `tests/ui/test_tui_chat_loop.py` | `TestRunOpenAIToolCalls::test_auto_approved_tool_execution` | Tests TUI-specific parallel execution; will converge with CLI | Unified async execution tests in shared engine |
| `tests/ui/test_tui_chat_loop.py` | `TestCancellation::test_cancelled_*` | Tests TUI-specific cancellation; will be handled by shared engine | Shared engine cancellation tests |

### Phase 05 Candidates (Checkpoint Convergence)

| Test File | Test Name(s) | Reason Obsolete | Replacement Plan |
|-----------|--------------|-----------------|------------------|
| `tests/test_memory.py` | `TestMemoryManager::test_create_checkpoint_success` | CLI-specific checkpoint path via MemoryManager; TUI uses direct path | Unified checkpoint creation tests |
| `tests/test_memory.py` | `TestMemoryManager::test_create_checkpoint_with_tool_calls` | Tool execution during checkpoint is CLI-specific | Unified checkpoint behavior tests |
| `tests/ui/test_tui_chat_loop.py` | `TestCheckpointCycle::test_checkpoint_creates_and_resets` | TUI-specific checkpoint path; will converge | Unified checkpoint cycle tests |
| `tests/ui/test_tui_chat_loop.py` | `TestCheckpointCycle::test_checkpoint_resets_messages_keeps_system` | TUI-specific message reset behavior | Unified message management tests |

### Implementation-Coupled Tests (All Phases)

| Test File | Test Name(s) | Reason Obsolete | Replacement Plan |
|-----------|--------------|-----------------|------------------|
| `tests/services/tools/test_executor.py` | `TestExecuteSingleCall::*` | Tests internal `_execute_single_call` method directly | Behavior tests through public execute interface |
| `tests/ui/test_tui_chat_loop.py` | `TestExtractThinkBlocks::*` | Tests private helper functions | Integration tests through public loop interface |
| `tests/ui/test_tui_chat_loop.py` | `TestStripToolMarkup::*` | Tests private helper functions | Integration tests through public loop interface |
| `tests/ui/test_tui_chat_loop.py` | `TestParseArguments::*` | Tests private helper functions | Integration tests through public loop interface |
| `tests/ui/test_tui_chat_loop.py` | `TestParseJsonToolCalls::*` | Tests private helper functions | Integration tests through public loop interface |
| `tests/ui/test_tui_chat_loop.py` | `TestRegexExtractJsonToolCalls::*` | Tests private helper functions | Integration tests through public loop interface |

---

## Early Cleanup Approved (if Architect approves)

| Test File | Test Name | Approval Status | Notes |
|-----------|-----------|-----------------|-------|
| *None at this time* | - | - | Awaiting Phase completion and Architect review |

---

## Detailed Rationale

### 1. Tool Execution Path Divergence

**Current State:**
- CLI: Uses `ToolExecutor` with sync execution flow via `_handle_tool_call()` and `_execute_single_call()`
- TUI: Uses direct `ToolRegistry` execution with mixed parallel/sequential async strategy

**Planned Convergence (Phase 04-05):**
- Both paths use shared async execution engine
- Tool execution becomes presentation-agnostic
- Confirmation handling unified

**Impact on Tests:**
- Tests directly mocking `ToolExecutor` internals will need replacement
- Tests asserting on sync execution order will become invalid
- Tests for TUI-specific parallel execution will need rework

### 2. Message Format Divergence

**Current State:**
- CLI: Appends tool messages via `ToolExecutor.execute_tool_calls()`
- TUI: Mixes `role=tool` messages with aggregated `role=user` fallback results

**Planned Convergence (Phase 02):**
- Normalized message contract across both paths
- Consistent tool result message format

**Impact on Tests:**
- Tests validating specific message formats may need updates
- Tests for fallback XML/JSON parsing may become obsolete if unified

### 3. Checkpoint Flow Divergence

**Current State:**
- CLI: `MemoryManager.create_checkpoint()` may execute tool calls during checkpoint
- TUI: Direct async LLM call then writes checkpoint via `CheckpointManager`

**Planned Convergence (Phase 05):**
- Unified checkpoint creation path
- Consistent behavior across interfaces

**Impact on Tests:**
- CLI-specific checkpoint creation tests will need replacement
- TUI-specific checkpoint tests will need replacement
- `CheckpointManager` I/O tests should remain valid (interface preserved)

### 4. Internal Helper Function Tests

**Current State:**
- Many tests exercise private helper functions (`_extract_think_blocks`, `_strip_tool_markup`, etc.)

**Planned State:**
- Private helpers may be refactored or moved
- Public interface behavior tests are more stable

**Impact on Tests:**
- Tests on private functions are brittle
- Should be replaced with tests through public interface

---

## Notes

- **Do not remove without Architect approval** — Each removal must be explicitly approved
- **Each removal must map to replacement coverage** — No reduction in behavior coverage
- **Phase-gated removal** — Candidates are grouped by the phase when they become obsolete
- **Re-evaluation at each gate** — This list should be reviewed at each Architect gate

---

## Tracking

| Date | Action | By |
|------|--------|-----|
| 2026-02-16 | Initial candidate list created | QA Engineer |
| | Architect review | Pending |
| | Approved for removal | Pending |
| | Replaced with new tests | Pending |

---

*Generated for Phase 01 QA Deliverables — Subject to Architect Approval*
