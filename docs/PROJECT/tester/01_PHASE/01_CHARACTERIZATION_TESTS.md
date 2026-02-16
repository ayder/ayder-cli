# Baseline Characterization Tests — Phase 01

**Phase ID:** `01_PHASE_BASELINE_AND_GOVERNANCE`  
**Generated:** 2026-02-16  
**Branch:** `qa/01/test-inventory`  
**Status:** BASELINE CONFIRMED

---

## Summary

This document confirms the baseline characterization tests for current behavior. These tests establish the expected behavior that must be preserved through the refactor phases.

---

## CLI Command Path

### Test: `tests/test_cli.py::TestRunCommand::test_run_command_success`

- **Coverage:** Entry point through command execution
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/test_cli.py::TestRunCommand::test_run_command_success -v
  ```
- **Notes:** 
  - Verifies CLI can parse args and invoke runner
  - Tests `_build_services()` -> `ChatSession` -> `Agent` -> `Agent.chat()` flow
  - Validates return code 0 on success
  - Mocks external dependencies (LLM, services)

### Test: `tests/test_cli.py::TestBuildServices::test_build_services_success_with_structure_macro`

- **Coverage:** Service construction and initialization
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/test_cli.py::TestBuildServices::test_build_services_success_with_structure_macro -v
  ```
- **Notes:**
  - Verifies service dependency construction
  - Tests project structure macro injection
  - Validates `Config`, `LLMProvider`, `ToolExecutor`, `ProjectContext` creation

### Test: `tests/test_cli.py::TestMainPermissionHandling::test_main_passes_both_permissions_to_run_command`

- **Coverage:** Permission flag propagation
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/test_cli.py::TestMainPermissionHandling::test_main_passes_both_permissions_to_run_command -v
  ```
- **Notes:**
  - Verifies `-w` and `-x` flags propagate to `run_command()`
  - Tests permission set construction (`{'r', 'w', 'x'}`)

---

## TUI Chat Loop

### Test: `tests/ui/test_tui_chat_loop.py::TestRunTextOnly::test_text_only_response`

- **Coverage:** Input processing through response generation (text-only)
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/ui/test_tui_chat_loop.py::TestRunTextOnly::test_text_only_response -v
  ```
- **Notes:**
  - Verifies TUI can process user input and generate response
  - Tests callback events: `thinking_start`, `thinking_stop`, `assistant_content`, `token_usage`
  - Validates message appended to conversation history
  - Mocks LLM response

### Test: `tests/ui/test_tui_chat_loop.py::TestRunOpenAIToolCalls::test_auto_approved_tool_execution`

- **Coverage:** Tool execution flow with auto-approval
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/ui/test_tui_chat_loop.py::TestRunOpenAIToolCalls::test_auto_approved_tool_execution -v
  ```
- **Notes:**
  - Verifies auto-approved tools execute without confirmation
  - Tests tool start/complete callback events
  - Validates tool result message appended to conversation

### Test: `tests/ui/test_tui_chat_loop.py::TestRunOpenAIToolCalls::test_needs_confirmation_approved`

- **Coverage:** Confirmation flow for permission-requiring tools
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/ui/test_tui_chat_loop.py::TestRunOpenAIToolCalls::test_needs_confirmation_approved -v
  ```
- **Notes:**
  - Verifies `write_file` with `{'r'}` permission triggers confirmation
  - Tests `request_confirmation` callback invocation
  - Validates tool execution after approval

---

## Checkpoint Operations

### Test: `tests/test_checkpoint_manager.py::TestCheckpointManager::test_save_checkpoint_success`

- **Coverage:** Checkpoint persistence round-trip (save)
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/test_checkpoint_manager.py::TestCheckpointManager::test_save_checkpoint_success -v
  ```
- **Notes:**
  - Verifies checkpoint can be saved with cycle metadata
  - Tests file creation in `.ayder/memory/`
  - Validates checkpoint format with cycle count and timestamp

### Test: `tests/test_checkpoint_manager.py::TestCheckpointManager::test_read_checkpoint_with_content`

- **Coverage:** Checkpoint persistence round-trip (read)
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/test_checkpoint_manager.py::TestCheckpointManager::test_read_checkpoint_with_content -v
  ```
- **Notes:**
  - Verifies checkpoint can be read back after save
  - Tests content preservation
  - Validates round-trip integrity

### Test: `tests/test_checkpoint_manager.py::TestCheckpointManager::test_save_checkpoint_increments_cycle`

- **Coverage:** Checkpoint cycle tracking
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/test_checkpoint_manager.py::TestCheckpointManager::test_save_checkpoint_increments_cycle -v
  ```
- **Notes:**
  - Verifies cycle count increments on each checkpoint
  - Tests cycle count persistence

### Test: `tests/test_memory.py::TestMemoryManager::test_restore_from_checkpoint`

- **Coverage:** Checkpoint restoration via MemoryManager
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/test_memory.py::TestMemoryManager::test_restore_from_checkpoint -v
  ```
- **Notes:**
  - Verifies session restoration from checkpoint
  - Tests message clearing with system prompt preservation
  - Validates restore message injection

### Test: `tests/ui/test_tui_chat_loop.py::TestCheckpointCycle::test_checkpoint_creates_and_resets`

- **Coverage:** TUI checkpoint creation and iteration reset
- **Status:** ✅ **EXISTING** - Test verified passing
- **Verification:**
  ```bash
  uv run pytest tests/ui/test_tui_chat_loop.py::TestCheckpointCycle::test_checkpoint_creates_and_resets -v
  ```
- **Notes:**
  - Verifies checkpoint creation on max_iterations exceeded
  - Tests iteration reset after checkpoint
  - Validates system message about checkpoint

---

## New Characterization Tests Added

| Test File | Test Name | Purpose | Status |
|-----------|-----------|---------|--------|
| *None required* | - | Existing baseline coverage sufficient | N/A |

---

## Baseline Test Execution Summary

### All Baseline Tests Pass

```bash
# CLI tests
uv run pytest tests/test_cli.py -v --timeout=30
# 46 passed

# TUI chat loop tests
uv run pytest tests/ui/test_tui_chat_loop.py -v --timeout=60
# 64 passed

# Checkpoint manager tests
uv run pytest tests/test_checkpoint_manager.py -v --timeout=30
# 14 passed

# Memory tests
uv run pytest tests/test_memory.py -v --timeout=30
# 26 passed
```

### Full Suite Verification

```bash
uv run poe test
# 733 passed, 5 skipped in 9.19s
```

---

## Characterization Coverage Map

| Behavior | Test(s) | Phase Risk |
|----------|---------|------------|
| CLI entry point | `TestRunCommand::test_run_command_success` | Low |
| Service construction | `TestBuildServices::*` | Low |
| Permission propagation | `TestMainPermissionHandling::*` | Low |
| TUI message flow | `TestRunTextOnly::test_text_only_response` | High |
| TUI tool execution | `TestRunOpenAIToolCalls::*` | High |
| TUI confirmation flow | `TestRunOpenAIToolCalls::test_needs_confirmation_*` | High |
| Checkpoint save | `TestCheckpointManager::test_save_checkpoint_*` | Medium |
| Checkpoint read | `TestCheckpointManager::test_read_checkpoint_*` | Medium |
| Checkpoint restore | `TestMemoryManager::test_restore_from_checkpoint` | Medium |
| TUI checkpoint cycle | `TestCheckpointCycle::test_checkpoint_creates_and_resets` | High |

---

## Notes for Phase Migration

### Phase 02 (Message Contract)
- Characterization tests should validate message format stability
- New adapter tests needed for message contract changes

### Phase 04 (Shared Async Engine)
- CLI and TUI characterization tests will converge
- Current separate path tests become unified behavior tests

### Phase 05 (Checkpoint Convergence)
- CLI checkpoint creation (via MemoryManager) and TUI checkpoint creation will unify
- Checkpoint I/O tests (CheckpointManager) should remain stable

---

*Generated for Phase 01 QA Deliverables — All baseline characterization tests confirmed passing*
