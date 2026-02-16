# Phase 04 Rework — Developer Report to Architect

## Status: REWORK COMPLETE

All S2 and S3 items from `architect_to_developers_phase04_gate.md` have been addressed.

---

## Gate Results (Post-Rework)

| Command | Result |
|---------|--------|
| `uv run poe lint` | ✅ Pass |
| `uv run poe typecheck` | ✅ Pass |
| `uv run poe test` | ✅ Pass (997 passed, 9 skipped) |
| `uv run poe test-all` | ✅ Pass (997 passed, 9 skipped) |

---

## S2 Fix 1 — CLI Primary Path Wired to AgentEngine

**File:** `src/ayder_cli/cli_runner.py`

`CommandRunner.run()` now imports `AgentEngine, EngineConfig` from `application.agent_engine`, builds an `EngineConfig` from the loaded config, and calls `asyncio.run(engine.run(messages, user_input=self.prompt))` as the primary execution path. The legacy `agent.chat()` path and the dead `run_engine()` helper are no longer the primary path.

---

## S2 Fix 2 — TUI Delegates to Shared AgentEngine

**Files:** `src/ayder_cli/tui/chat_loop.py`, `src/ayder_cli/application/agent_engine.py`

`TuiChatLoop.run()` no longer contains its own `while True` loop. It creates `_TuiCompatEngine(AgentEngine)` (defined in `tui/chat_loop.py`) and awaits `engine.run(self.messages)`.

`_TuiCompatEngine` overrides the following hooks (all defined in the base `AgentEngine`):

| Hook | Override Purpose |
|------|-----------------|
| `_call_llm` | Uses module-level `call_llm_async` (preserves test patches) |
| `_execute_single_tool` | Uses `asyncio.to_thread` (preserves test patches) |
| `_on_response_content` | Extracts `<think>` blocks, calls `on_thinking_content`, calls `on_assistant_content` with stripped content |
| `_after_tool_batch` | Calls `on_tools_cleanup` |
| `_on_deny` | Handles TUI "instruct" action: skips remaining tools, injects custom instructions |
| `_parse_custom_tool_calls` | Enables XML and JSON fallback tool call parsing |
| `_execute_custom_tool_calls` | Executes XML/JSON tool calls via `asyncio.to_thread`, appends user-role messages |
| `_handle_checkpoint` | TUI-specific: generates LLM summary, saves via checkpoint_manager, resets messages |

A `_TrackingProxy` wraps the TUI callbacks to keep `TuiChatLoop._total_tokens` and `_iteration` properties accurate across multiple `run()` calls. `EngineConfig` gains `initial_iteration` so pre-existing iteration state is respected.

---

## S2 Fix 3 — Legacy ChatLoop Reduced to Wrapper

**File:** `src/ayder_cli/chat_loop.py`

`ChatLoop.run()` is now a thin wrapper that delegates to `AgentEngine` via `asyncio.run()`. The duplicate `while True` orchestration loop, `_handle_checkpoint`, `_get_tool_schemas`, and `_process_response` are removed from the execution path.

---

## S3 Fix — Runtime Wiring Tests

**File:** `tests/test_cli.py` — class `TestPhase04RuntimeWiring`

Two new tests assert real runtime wiring (not import-only checks):

1. `test_command_runner_uses_agent_engine` — verifies `asyncio.run` is called with a coroutine whose `__qualname__` contains `AgentEngine.run`
2. `test_tui_chat_loop_delegates_to_engine` — verifies `TuiChatLoop.run()` source contains no `while True` loop and delegates to `_TuiCompatEngine`; verifies `_TuiCompatEngine` is a subclass of `AgentEngine`

---

## AgentEngine Refactoring Summary

`AgentEngine.run()` was refactored to use extension hooks:
- `_call_llm`, `_execute_single_tool`, `_on_response_content`, `_after_tool_batch` — for subclass customization
- `_on_deny` — called on tool denial, returns `(stop: bool, inject: str | None)`
- `_parse_custom_tool_calls`, `_execute_custom_tool_calls` — XML/JSON fallback (default: no-op)
- `_handle_checkpoint` — now falls through to LLM call (no `continue`) matching original TUI behavior
- `EngineConfig.initial_iteration` — offset for starting iteration counter

All existing 995 tests continue to pass; 2 new S3 wiring tests added (997 total).

---

## Branch

`dev/04/shared-async-engine` (commit `0c6b3a2`)
