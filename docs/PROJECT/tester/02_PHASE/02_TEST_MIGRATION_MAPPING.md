# Test Migration Mapping — Phase 02

**Phase ID:** `02_PHASE_RUNTIME_FACTORY_AND_MESSAGE_CONTRACT`  
**Generated:** 2026-02-16  
**Branch:** `qa/02/factory-contract-tests` → `arch/02/runtime-factory-gate`  
**Status:** PENDING ARCHITECT APPROVAL

---

## Overview

This document maps obsolete tests to their replacements for Phase 02. Per the Test Migration Policy, no tests are removed without Architect approval during the gate review.

---

## QA-02.1 Obsolete Wiring Tests (Pending Removal)

### Tests Obsoleted by Factory Introduction

| Test File | Test Name(s) | Reason Obsolete | Replacement Test |
|-----------|--------------|-----------------|------------------|
| `tests/test_cli.py` | `TestBuildServices::test_build_services_with_exception_in_structure_macro` | Tests old `_build_services()` inline composition | `test_runtime_factory_handles_structure_macro_failure` |
| `tests/test_cli.py` | `TestBuildServices::test_build_services_success_with_structure_macro` | Tests old `_build_services()` inline composition | `test_factory_consistent_system_prompt` |
| `tests/test_cli.py` | `TestBuildServices::test_build_services_with_custom_config` | Tests old `_build_services()` config handling | `test_factory_accepts_config_override` |
| `tests/test_cli.py` | `TestBuildServices::test_build_services_with_custom_project_root` | Tests old `_build_services()` project root handling | `test_factory_accepts_project_root` |
| `tests/test_cli.py` | `TestRunCommand::*` (indirectly) | Tests runner that uses old composition | `test_cli_uses_factory_components` |

### Tests That Should Be UPDATED (Not Removed)

| Test File | Current Test | Required Update | Notes |
|-----------|--------------|-----------------|-------|
| `tests/test_cli.py` | `TestBuildServices::*` | Update to test factory delegation | Keep testing CLI integration, but through factory |
| `tests/test_cli.py` | `TestRunCommand::test_run_command_success` | Add factory verification | Verify factory-built deps are used |
| `tests/test_cli.py` | `TestRunCommand::test_run_command_error` | Add factory error handling | Verify factory errors propagate correctly |

---

## QA-02.2 New Runtime Factory Tests

### Added Tests

| Test File | Test Name | Purpose | Verification |
|-----------|-----------|---------|--------------|
| `tests/application/test_runtime_factory.py` | `test_runtime_factory_assembles_all_components` | Factory returns all 9 components | All fields in RuntimeComponents present |
| `tests/application/test_runtime_factory.py` | `test_factory_components_not_none` | No component is None | All 9 components initialized |
| `tests/application/test_runtime_factory.py` | `test_factory_accepts_config_override` | Injected config used | Config parameter honored |
| `tests/application/test_runtime_factory.py` | `test_factory_accepts_project_root` | Custom project root | project_root parameter honored |
| `tests/application/test_runtime_factory.py` | `test_factory_accepts_model_name` | Model name override | model_name parameter honored |
| `tests/application/test_runtime_factory.py` | `test_cli_uses_factory_components` | CLI integration | _build_services() uses factory |
| `tests/application/test_runtime_factory.py` | `test_cli_factory_integration_preserves_behavior` | CLI behavior preserved | Same outputs as before |
| `tests/application/test_runtime_factory.py` | `test_tui_uses_factory_components` | TUI integration | AyderApp uses factory |
| `tests/application/test_runtime_factory.py` | `test_cli_tui_factory_parity` | Composition parity | CLI/TUI get equivalent deps |
| `tests/application/test_runtime_factory.py` | `test_factory_consistent_system_prompt` | System prompt consistency | Factory produces valid prompt |
| `tests/application/test_runtime_factory.py` | `test_factory_project_structure_macro` | Structure macro inclusion | Project structure in prompt |
| `tests/application/test_runtime_factory.py` | `test_factory_handles_structure_macro_failure` | Graceful degradation | No error on structure failure |
| `tests/application/test_runtime_factory.py` | `test_factory_default_values` | Sensible defaults | Current dir, loaded config |

---

## QA-02.3 New Message Contract Tests

### Added Tests

| Test File | Test Name | Purpose | Verification |
|-----------|-----------|---------|--------------|
| `tests/application/test_message_contract.py` | `test_get_message_role_from_dict` | Dict role extraction | `{"role": "user"}` → `"user"` |
| `tests/application/test_message_contract.py` | `test_get_message_role_from_object` | Object role extraction | `msg.role` → role value |
| `tests/application/test_message_contract.py` | `test_get_message_role_missing_field` | Missing role handling | Returns `"unknown"` |
| `tests/application/test_message_contract.py` | `test_get_message_role_various_roles` | All standard roles | system, user, assistant, tool |
| `tests/application/test_message_contract.py` | `test_get_message_content_from_dict` | Dict content extraction | `{"content": "..."}` → content |
| `tests/application/test_message_contract.py` | `test_get_message_content_from_object` | Object content extraction | `msg.content` → content |
| `tests/application/test_message_contract.py` | `test_get_message_content_missing_field` | Missing content handling | Returns `""` |
| `tests/application/test_message_contract.py` | `test_get_message_content_none_value` | None content handling | Returns `""` |
| `tests/application/test_message_contract.py` | `test_get_message_content_non_string` | Type coercion | Non-string → string |
| `tests/application/test_message_contract.py` | `test_get_message_tool_calls_from_dict` | Dict tool_calls extraction | Returns tool_calls list |
| `tests/application/test_message_contract.py` | `test_get_message_tool_calls_from_object` | Object tool_calls extraction | Returns tool_calls list |
| `tests/application/test_message_contract.py` | `test_get_message_tool_calls_missing` | Missing tool_calls | Returns `[]` |
| `tests/application/test_message_contract.py` | `test_get_message_tool_calls_multiple` | Multiple tool calls | Handles list of calls |
| `tests/application/test_message_contract.py` | `test_to_message_dict_from_dict` | Dict passthrough | Returns same dict |
| `tests/application/test_message_contract.py` | `test_to_message_dict_from_object` | Object conversion | Converts to dict |
| `tests/application/test_message_contract.py` | `test_to_message_dict_preserves_tool_calls` | Tool calls preserved | tool_calls in output |
| `tests/application/test_message_contract.py` | `test_checkpoint_summary_with_mixed_messages` | Mixed format handling | Dict + object messages |
| `tests/application/test_message_contract.py` | `test_checkpoint_summary_with_tool_calls` | Tool call messages | Handles tool messages |
| `tests/application/test_message_contract.py` | `test_checkpoint_summary_with_missing_content` | Missing content | Returns empty string |
| `tests/application/test_message_contract.py` | `test_empty_dict_message` | Empty message | All defaults |
| `tests/application/test_message_contract.py` | `test_unicode_content` | Unicode handling | Preserves unicode |

---

## Remove → Replace Summary Table

| Phase 02 Action | Count | Details |
|-----------------|-------|---------|
| Tests to Update | 4 | `TestBuildServices::*` tests need factory integration |
| Tests Added (Factory) | 13 | New runtime factory tests |
| Tests Added (Contract) | 22 | New message contract tests |
| **Net Change** | **+31** | Significant coverage increase |

---

## Migration Notes

### For Architect Review

1. **Factory Integration**
   - Old `_build_services()` tests should be updated to test factory delegation
   - New factory tests validate 9-component assembly
   - CLI/TUI parity test ensures consistent composition

2. **Message Contract Integration**
   - Contract tests are forward-looking (DEV-02.4)
   - Tests use `pytest.importorskip()` to handle missing implementation
   - Once contract module exists, tests will run automatically

3. **Backward Compatibility**
   - `_build_services()` return signature preserved for CLI
   - AyderApp initialization order preserved for TUI
   - No breaking changes to public interfaces

---

## Approval Tracking

| Date | Action | By | Status |
|------|--------|-----|--------|
| 2026-02-16 | Migration mapping created | QA Engineer | Ready |
| | Architect review | Architect | Pending |
| | Test removals approved | Architect | Pending |
| | New tests approved | Architect | Pending |

---

## Verification Commands

```bash
# Run new factory tests (will skip until DEV implementation)
uv run pytest tests/application/test_runtime_factory.py -v

# Run new message contract tests (will skip until DEV implementation)
uv run pytest tests/application/test_message_contract.py -v

# Run all tests
uv run poe test

# Run lint
uv run poe lint
```

---

*Generated for Phase 02 QA Deliverables — Pending Architect Approval*
