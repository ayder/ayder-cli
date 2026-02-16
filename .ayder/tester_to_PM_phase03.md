# Tester to PM Report — Phase 03 Step B

## Summary
Test definitions complete for service/UI decoupling contracts. All test files created following **Test-First** methodology.

## Branch
`qa/03/service-ui-decoupling`

## Test Files Created

| File | Contract | Lines | Status |
|------|----------|-------|--------|
| `tests/services/test_boundary.py` | Contract 1 | 150 | ✅ Created |
| `tests/services/test_interaction_sink.py` | Contract 2 | 330 | ✅ Created |
| `tests/services/test_confirmation_policy.py` | Contract 2 | 270 | ✅ Created |
| `tests/services/test_executor_integration.py` | Contract 3 | 420 | ✅ Created |
| `tests/services/test_llm_verbose.py` | Contract 4 | 310 | ✅ Updated |
| `tests/application/test_service_ui_decoupling.py` | Integration | 430 | ✅ Created |

**Total: 6 new test files, ~1,910 lines of test definitions**

## Contract Coverage

| Contract | Test File | Coverage |
|----------|-----------|----------|
| 1. Service Boundary (no UI imports) | `test_boundary.py` | ✅ AST-based import detection |
| 2. InteractionSink Protocol | `test_interaction_sink.py` | ✅ Protocol definition + behavior tests |
| 2. ConfirmationPolicy Protocol | `test_confirmation_policy.py` | ✅ Protocol definition + flow tests |
| 3. Executor Integration | `test_executor_integration.py` | ✅ Interface injection + execution flow |
| 4. LLM Verbose Integration | `test_llm_verbose.py` | ✅ Sink-based verbose routing |
| 5. Adapter Ownership (documented) | `test_service_ui_decoupling.py` | ✅ Adapter pattern examples |

## Interface Protocols Defined

### InteractionSink
```python
@runtime_checkable
class InteractionSink(Protocol):
    def on_tool_call(self, tool_name: str, args_json: str) -> None: ...
    def on_tool_result(self, result: str) -> None: ...
    def on_tool_skipped(self) -> None: ...
    def on_file_preview(self, file_path: str) -> None: ...
    def on_llm_request_debug(self, messages, model, tools, options) -> None: ...
```

### ConfirmationPolicy
```python
@runtime_checkable
class ConfirmationPolicy(Protocol):
    def confirm_action(self, description: str) -> bool: ...
    def confirm_file_diff(self, file_path, new_content, description) -> bool: ...
```

## Test Results (Expected: Failing)

```bash
$ uv run pytest tests/services/test_boundary.py tests/services/test_interaction_sink.py \
    tests/services/test_confirmation_policy.py tests/services/test_executor_integration.py \
    tests/services/test_llm_verbose.py tests/application/test_service_ui_decoupling.py -v

Results: 75 tests collected
- 28 PASSED (protocol definition tests)
- 5 SKIPPED (optional checks)
- 42 FAILED (expected - implementation pending)
```

### Expected Failures Document Implementation Needs:

| Failure | Indicates |
|---------|-----------|
| `test_services_directory_has_no_ui_imports` | `executor.py` and `llm.py` need UI imports removed |
| `test_executor_accepts_sink_in_constructor` | `ToolExecutor.__init__()` needs `interaction_sink` param |
| `test_executor_accepts_policy_in_constructor` | `ToolExecutor.__init__()` needs `confirmation_policy` param |
| `test_provider_accepts_sink_in_constructor` | `OpenAIProvider.__init__()` needs `interaction_sink` param |
| `test_verbose_true_calls_sink_method` | `chat()` needs to call `sink.on_llm_request_debug()` |

## Commands Run

```bash
# Linting
$ uv run poe lint
All checks passed!

# Test run (expected failures for test-first)
$ uv run pytest tests/services/ tests/application/test_service_ui_decoupling.py -v --timeout=60
# Results: 28 passed, 5 skipped, 42 failed (as expected)
```

## Implementation Requirements for Developers

### 1. Define Protocols in `src/ayder_cli/services/__init__.py`
```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class InteractionSink(Protocol):
    def on_tool_call(self, tool_name: str, args_json: str) -> None: ...
    def on_tool_result(self, result: str) -> None: ...
    def on_tool_skipped(self) -> None: ...
    def on_file_preview(self, file_path: str) -> None: ...
    def on_llm_request_debug(self, messages, model, tools, options) -> None: ...

@runtime_checkable
class ConfirmationPolicy(Protocol):
    def confirm_action(self, description: str) -> bool: ...
    def confirm_file_diff(self, file_path, new_content, description) -> bool: ...
```

### 2. Update `ToolExecutor` (`src/ayder_cli/services/tools/executor.py`)
- Remove imports: `confirm_tool_call`, `confirm_with_diff`, `print_tool_call`, `print_tool_result`, `print_tool_skipped`, `print_file_content`, `describe_tool_action`
- Add constructor params: `interaction_sink: InteractionSink | None = None`, `confirmation_policy: ConfirmationPolicy | None = None`
- Replace direct UI calls with sink/policy method calls

### 3. Update LLM Providers (`src/ayder_cli/services/llm.py`)
- Remove imports: `print_llm_request_debug` from `ayder_cli.ui`
- Add constructor param: `interaction_sink: InteractionSink | None = None`
- Replace `_print_llm_request()` with `sink.on_llm_request_debug()` calls

### 4. Create CLI/TUI Adapters (out of scope for this phase, but tests verify interface compatibility)
- CLI adapter implements `InteractionSink` and `ConfirmationPolicy` using `ayder_cli.ui` functions
- TUI adapter implements same protocols for TUI callbacks

## Notes for Developers

### Key Interface Details

1. **InteractionSink.on_tool_call()** - Called BEFORE confirmation
2. **InteractionSink.on_tool_result()** - Called AFTER successful execution
3. **InteractionSink.on_tool_skipped()** - Called when user declines
4. **ConfirmationPolicy.confirm_action()** - For general tool confirmation
5. **ConfirmationPolicy.confirm_file_diff()** - For write/replace/insert/delete tools

### Backward Compatibility
- All interface parameters should be `Optional` with `None` default
- When sink/policy is `None`, behavior should remain unchanged (legacy mode)

### Permission Handling
- Auto-approved tools (permission in `granted_permissions`) skip `ConfirmationPolicy` calls
- Still call `InteractionSink` methods for notification

## MR Status
- **Source:** `qa/03/service-ui-decoupling`
- **Target:** `arch/03/service-ui-gate`
- **Status:** Ready for Developer handoff

## Next Steps
1. Developer pulls `qa/03/service-ui-decoupling` branch
2. Developer implements against test contracts
3. Tests should transition from FAIL to PASS as implementation progresses
4. Architect reviews when all tests pass

## Test-First Confirmation

✅ **Tests define the contract** - All interfaces and behaviors specified
✅ **Tests fail initially** - No implementation yet (correct for test-first)
✅ **Clear implementation path** - Developer knows exactly what to build
✅ **Lint passes** - Clean code structure

---

**Ready for Developer implementation phase.**
