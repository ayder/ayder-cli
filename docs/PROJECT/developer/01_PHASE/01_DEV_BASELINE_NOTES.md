# Developer Baseline Notes — Phase 01

## CLI Flow Verification

- Entry point confirmed: `src/ayder_cli/cli.py::main()` parses args via `create_parser()`, builds permissions set from `-r/-w/-x` flags, resolves `iterations` from config or CLI flag, then dispatches:
  - `--tasks` → `_run_tasks_cli()`
  - `--implement TASK` → `_run_implement_cli(task, permissions, iterations)`
  - `--implement-all` → `_run_implement_all_cli(permissions, iterations)`
  - no input → `run_tui(permissions, iterations)` (TUI fallback)
  - prompt present → `run_command(prompt, permissions, iterations)`
- Service building pattern: `cli_runner.CommandRunner._build_services()` builds `LLMClient`, `ToolRegistry` (via `create_default_registry`), `ProcessManager`, `CheckpointManager`, `MemoryManager`, then creates `ChatSession` and `Agent`.
- `Agent.chat(prompt)` constructs a `LoopConfig` and delegates to `ChatLoop.run(...)`.
- `ChatLoop` uses `IterationController` to count iterations; on overflow, `_handle_checkpoint()` is called.
- Observations:
  - Read permission is auto-granted by default; write/execute require explicit flags.
  - `cli.py` is thin—all service wiring lives in `cli_runner.py`.
  - Lazy imports inside `main()` (`cli_runner`, `tui`, `config`) keep startup fast for the TUI path.

## TUI Flow Verification

- Entry point confirmed: `src/ayder_cli/tui/app.py::AyderApp` (Textual `App` subclass).
- Callback pattern for UI updates:
  - `AyderApp` initialises `AppCallbacks` dataclass; callbacks fire `on_tool_start`, `on_tool_complete`, `on_tools_cleanup`, `on_stream_text`, `on_confirmation_needed`.
  - `handle_input_submitted()` appends user message, enqueues to `_input_queue`, and calls `start_llm_processing()`.
  - `start_llm_processing()` spawns `_run_chat_loop()` as a Textual `@work` worker; worker awaits `TuiChatLoop.run(messages, callbacks)`.
  - `CLIConfirmScreen` is pushed for tool confirmations; result is passed back via `AppCallbacks.request_confirmation()`.
- Observations:
  - `TuiChatLoop` is async throughout; no blocking calls inside the worker.
  - All UI state changes go through `call_from_thread` / reactive Textual patterns.
  - `AppCallbacks` is the sole decoupling boundary between loop logic and Textual widgets.

## Checkpoint Behavior Notes

- CLI checkpoint trigger: `IterationController` reaches `max_iterations` inside `ChatLoop.run()`; `_handle_checkpoint()` is called synchronously.
  - If a checkpoint file exists: `MemoryManager.restore_from_checkpoint()` reads it and resets context.
  - If not: `MemoryManager.create_checkpoint()` prompts the LLM, optionally executes write tool calls, resets session, then injects restore context via `build_quick_restore_message()`.
  - Persistence: `CheckpointManager.save_checkpoint()` / `read_checkpoint()` / `clear_checkpoint()` — file at `.ayder/memory/current_memory.md`.
- TUI checkpoint trigger: `TuiChatLoop.run()` checks iteration count; on overflow, `_handle_checkpoint()` is called async.
  - Summarises recent messages, calls LLM with empty tool list (`tools=[]`), writes summary directly via `CheckpointManager.save_checkpoint()`, resets message list (keeps system prompt), appends restore message.
- Divergence observations:
  - CLI path may execute tool calls as part of checkpoint creation; TUI path bypasses tool execution for checkpoint writes.
  - TUI path calls LLM with `tools=[]` ensuring a pure text summary; CLI path uses the normal tool-capable LLM call, so checkpoint quality may differ.
  - Both paths call `MemoryManager.build_quick_restore_message()` for the restore injection.

## Tool Execution Notes

- CLI confirmation flow:
  - `ChatLoop` calls `ToolCallHandler.execute()` → `ToolExecutor.execute_all()`.
  - `ToolExecutor` pipeline: normalize → validate → permission-check → confirm (diff-based for file tools, stdin prompt for others) → execute via `ToolRegistry.call()`.
  - Results appended as `role=tool` messages for OpenAI structured calls; XML custom-call results appended as `role=user` text.
- TUI confirmation flow:
  - `TuiChatLoop` splits OpenAI calls into auto-approved (parallel via `asyncio.gather` + `to_thread`) and confirmation-required (sequential via `AppCallbacks.request_confirmation()` → modal screen).
  - XML/JSON fallback custom calls executed in a secondary pass, results aggregated into a single `role=user` message.
  - UI feedback via callbacks updates `ToolPanel` and `ActivityBar` in real time.
- Result formatting differences:
  - CLI: each tool result → individual `role=tool` message (standard OpenAI format).
  - TUI OpenAI calls: same `role=tool` format.
  - TUI custom/XML calls: aggregated into single `role=user` text block — differs from CLI.

## Implementation Concerns for Future Phases

- Risk areas identified:
  - **Async migration (R01-ASYNC):** CLI `ChatLoop` is synchronous (`for` loop + blocking LLM calls); TUI `TuiChatLoop` is async. Any shared engine requires either making CLI async or keeping a sync shim.
  - **Message contract (R02-MSG):** Aggregated `role=user` custom-call results in TUI vs. individual `role=tool` in CLI will break normalization unless an adapter is introduced.
  - **Checkpoint divergence:** CLI may produce richer checkpoints (via tool calls); TUI produces simpler text-only summaries. Future shared checkpoint logic must unify these.
  - **Test surface:** Tests for `ChatLoop` and `TuiChatLoop` couple to internal iteration logic; any refactor to a shared base class will require careful test migration.
- Recommended refactoring order:
  1. Phase 02: Define normalized message contract + adapter for custom-call results.
  2. Phase 03: Abstract `IterationController` and checkpoint logic into a shared base.
  3. Phase 04: Introduce async wrapper for CLI path; unify checkpoint creation.
  4. Phase 05+: Migrate to shared engine, remove duplicated loop logic.
