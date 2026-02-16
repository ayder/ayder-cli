# Test Inventory — Phase 01

**Phase ID:** `01_PHASE_BASELINE_AND_GOVERNANCE`  
**Generated:** 2026-02-16  
**Branch:** `qa/01/test-inventory`  

---

## Impacted Test Areas

### tests/services/tools/test_executor.py

- **Purpose:** Tool execution flow testing for CLI path
- **Key Tests:**
  - `TestToolExecutor::test_executor_initialization` - Basic executor setup
  - `TestToolExecutor::test_handle_tool_call` - OpenAI tool call handling
  - `TestToolExecutor::test_handle_tool_call_declined` - Declined tool handling
  - `TestToolExecutor::test_execute_tool_calls_with_multiple_tools` - Multi-tool execution
  - `TestToolExecutor::test_handle_custom_calls_validation_error` - Validation errors
  - `TestToolExecutor::test_handle_custom_calls_write_file_with_diff` - Write file with diff
  - `TestExecuteSingleCall::test_execute_single_call_success` - Unified execution method
  - `TestExecuteSingleCall::test_execute_single_call_declined` - Declined confirmation
  - `TestExecuteSingleCall::test_execute_single_call_write_file_diff` - Diff confirmation
  - `TestExecuteSingleCall::test_execute_single_call_auto_approved` - Permission auto-approval
- **Refactor Impact:** **HIGH** - Execution path will change with async convergence in Phase 04
- **Action Required:** Map to new execution contract in Phase 04-05; tests mock ToolExecutor internals that will be replaced

---

### tests/services/test_llm*.py

- **Purpose:** LLM provider testing (OpenAI, Anthropic, Gemini)
- **Key Tests:**
  - `TestOpenAIProvider::test_chat_basic_call` - Basic chat functionality
  - `TestOpenAIProvider::test_chat_with_tools` - Tool-enabled chat
  - `TestOpenAIProvider::test_chat_with_options` - Options passthrough
  - `TestAnthropicProvider::test_system_message_extraction` - Message conversion
  - `TestAnthropicProvider::test_tool_schema_translation` - Tool schema mapping
  - `TestAnthropicProvider::test_text_only_response_wrapping` - Response wrapping
  - `TestAnthropicProvider::test_tool_use_response_wrapping` - Tool call wrapping
  - `TestCreateLLMProvider::test_returns_openai_for_openai_provider` - Factory method
- **Refactor Impact:** **MEDIUM** - Message contract normalization in Phase 02
- **Action Required:** Validate message shape compatibility after message contract changes

---

### tests/ui/test_tui_chat_loop.py

- **Purpose:** TUI chat loop behavior testing
- **Key Tests:**
  - `TestRunTextOnly::test_text_only_response` - Basic message flow
  - `TestRunTextOnly::test_iteration_increments` - Iteration tracking
  - `TestRunOpenAIToolCalls::test_auto_approved_tool_execution` - Auto-approved tools
  - `TestRunOpenAIToolCalls::test_needs_confirmation_approved` - Confirmation flow
  - `TestRunOpenAIToolCalls::test_needs_confirmation_denied` - Denied confirmation
  - `TestRunXMLFallback::test_xml_tool_call_detected` - XML fallback parsing
  - `TestRunJSONFallback::test_json_tool_call_detected` - JSON fallback parsing
  - `TestCancellation::test_cancelled_before_llm_call` - Cancellation handling
  - `TestIterationAndCheckpoint::test_tokens_accumulate` - Token tracking
  - `TestToolNeedsConfirmation::test_*` - Permission-based confirmation logic
  - `TestCheckpointCycle::test_checkpoint_creates_and_resets` - Checkpoint behavior
  - `TestCheckpointCycle::test_checkpoint_resets_messages_keeps_system` - Message reset
- **Refactor Impact:** **HIGH** - Loop will converge with CLI in Phase 04
- **Action Required:** Characterization tests for current behavior; significant internals will change

---

### tests/test_memory.py

- **Purpose:** Memory persistence and MemoryManager testing
- **Key Tests:**
  - `TestSaveMemory::test_save_basic_memory` - Basic memory save
  - `TestSaveMemory::test_save_memory_with_category` - Categorized memory
  - `TestLoadMemory::test_load_all_memories` - Memory retrieval
  - `TestLoadMemory::test_load_filter_by_category` - Filtered loading
  - `TestMemoryManager::test_initialization` - Manager setup
  - `TestMemoryManager::test_build_checkpoint_prompt` - Checkpoint prompt building
  - `TestMemoryManager::test_build_quick_restore_message_with_checkpoint` - Restore messages
  - `TestMemoryManager::test_create_checkpoint_success` - Checkpoint creation via LLM
  - `TestMemoryManager::test_restore_from_checkpoint` - Checkpoint restoration
  - `TestMemoryManager::test_build_conversation_summary` - Summary generation
- **Refactor Impact:** **MEDIUM** - Checkpoint flow changes in Phase 05
- **Action Required:** Verify checkpoint read/write behavior preserved; MemoryManager.create_checkpoint() path diverges from TUI

---

### tests/test_checkpoint_manager.py

- **Purpose:** Checkpoint I/O operations testing
- **Key Tests:**
  - `TestCheckpointManager::test_initialization` - Manager setup
  - `TestCheckpointManager::test_initialization_restores_cycle_count` - Cycle restoration
  - `TestCheckpointManager::test_save_checkpoint_success` - Checkpoint save
  - `TestCheckpointManager::test_save_checkpoint_increments_cycle` - Cycle incrementing
  - `TestCheckpointManager::test_read_checkpoint_with_content` - Checkpoint read
  - `TestCheckpointManager::test_clear_checkpoint` - Checkpoint clear
  - `TestCheckpointManager::test_has_saved_checkpoint_true/false` - Existence checks
- **Refactor Impact:** **HIGH** - Checkpoint creation path divergence between CLI and TUI
- **Action Required:** Validate both CLI (via MemoryManager) and TUI (direct via CheckpointManager) checkpoint paths converge in Phase 05

---

### tests/test_cli.py

- **Purpose:** CLI entry point and command parsing testing
- **Key Tests:**
  - `TestBuildServices::test_build_services_success_with_structure_macro` - Service building
  - `TestBuildServices::test_build_services_with_exception_in_structure_macro` - Error handling
  - `TestRunCommand::test_run_command_success` - Command execution success
  - `TestRunCommand::test_run_command_error` - Command execution error
  - `TestMainFunction::test_main_permission_flags_indirect` - Permission flag parsing
  - `TestMainPermissionHandling::test_main_passes_write_permission_to_run_command` - Permission passing
  - `TestMainPermissionHandling::test_main_passes_both_permissions_to_run_command` - Multi-permission
  - `TestMainTaskOptions::test_main_tasks_flag` - Tasks flag handling
  - `TestMainTaskOptions::test_main_implement_flag` - Implement flag handling
  - `TestMainTUIAndInteractive::test_main_default_tui_mode` - TUI fallback
  - `TestCreateParser::test_parser_permission_flags` - Parser configuration
  - `TestCreateParser::test_parser_iterations_flag` - Iterations flag
- **Refactor Impact:** **LOW** - Entry point stable; internal service construction may change
- **Action Required:** Baseline characterization; verify service construction changes don't break CLI

---

## Test Count Summary

| Test File | Test Count | Impact Level | Notes |
|-----------|------------|--------------|-------|
| `tests/services/tools/test_executor.py` | 17 | HIGH | Tool execution internals |
| `tests/services/test_llm.py` | 30 | MEDIUM | Message contract |
| `tests/services/test_llm_gemini.py` | 10 | MEDIUM | Provider-specific |
| `tests/services/test_llm_verbose.py` | 4 | LOW | Logging only |
| `tests/ui/test_tui_chat_loop.py` | 64 | HIGH | Loop convergence target |
| `tests/test_memory.py` | 26 | MEDIUM | Checkpoint flow |
| `tests/test_checkpoint_manager.py` | 14 | HIGH | I/O operations |
| `tests/test_cli.py` | 46 | LOW | Entry point stable |

---

## Migration Mapping Notes

### Phase 02 (Message Contract)
- Tests validating message shape conversions (AnthropicProvider message tests) need review
- Tool result message format tests will need adaptation

### Phase 04 (Shared Async Engine)
- ToolExecutor tests will need significant rework for async execution
- TuiChatLoop and ChatLoop tests will converge; many will become obsolete

### Phase 05 (Checkpoint Convergence)
- MemoryManager.create_checkpoint() tests vs TuiChatLoop checkpoint tests need alignment
- CheckpointManager I/O tests should remain valid (stable interface)

---

*Generated for Phase 01 QA Deliverables*
