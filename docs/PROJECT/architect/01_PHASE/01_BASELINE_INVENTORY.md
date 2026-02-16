# Phase 01 Baseline Inventory

## 1. CLI Orchestration Path
- Entry: `src/ayder_cli/cli.py::main()`
- Flow:
  1. `create_parser()` defines CLI flags and task/file/stdin inputs.
  2. `main()` parses args, resolves permission flags and iteration limit.
  3. Dispatch:
     - `--tasks`, `--implement`, `--implement-all` -> `cli_runner` task helpers.
     - no prompt inputs -> TUI fallback via `run_tui(...)`.
     - prompt input present -> `cli_runner.run_command(...)`.
  4. `cli_runner.CommandRunner.run()` builds dependencies via `_build_services()`, creates `ChatSession`, creates `Agent`, and runs `agent.chat(prompt)`.
  5. `Agent.chat()` builds `LoopConfig` and delegates execution to `ChatLoop.run(...)`.
- Key files:
  - `src/ayder_cli/cli.py`
  - `src/ayder_cli/cli_runner.py`
  - `src/ayder_cli/client.py`
  - `src/ayder_cli/chat_loop.py`

## 2. TUI Orchestration Path
- Entry: `src/ayder_cli/tui/app.py::AyderApp`
- Flow:
  1. `AyderApp.__init__()` loads config/model, builds LLM provider, creates tool registry/process manager, and initializes checkpoint + memory managers.
  2. `AyderApp` creates `TuiChatLoop` with `TuiLoopConfig` and `AppCallbacks`.
  3. `compose()` mounts `ChatView`, `ToolPanel`, `ActivityBar`, input bar, and status bar.
  4. `handle_input_submitted()` enqueues user text, appends user message, and triggers `start_llm_processing()`.
  5. `start_llm_processing()` runs `_run_chat_loop()` worker, which awaits `TuiChatLoop.run(...)`.
  6. `AppCallbacks` bridges loop events to UI updates and confirmation modal flow.
- Key files:
  - `src/ayder_cli/tui/app.py`
  - `src/ayder_cli/tui/chat_loop.py`

## 3. Checkpoint Flow (Both Paths)
- CLI path:
  - Iteration limit enforced in `ChatLoop` via `IterationController`.
  - On overflow, `ChatLoop._handle_checkpoint()`:
    - restores from existing checkpoint (`MemoryManager.restore_from_checkpoint`) if file exists, or
    - creates checkpoint (`MemoryManager.create_checkpoint`) by prompting LLM, optionally executing write tool calls, resetting session, and injecting restore context.
  - File persistence and cycle metadata handled by `CheckpointManager` (`save_checkpoint`, `read_checkpoint`, `clear_checkpoint`) under `.ayder/memory/current_memory.md`.
- TUI path:
  - Iteration limit enforced in `TuiChatLoop.run()`.
  - On overflow, `TuiChatLoop._handle_checkpoint()`:
    - summarizes recent messages,
    - calls LLM with checkpoint prompt (`tools=[]`),
    - writes summary directly with `CheckpointManager.save_checkpoint(...)`,
    - resets message list (keeps system), appends restore message from `MemoryManager.build_quick_restore_message()`.
- Divergence notes:
  - CLI checkpoint creation path goes through `MemoryManager.create_checkpoint()` and may execute tool calls.
  - TUI checkpoint creation path writes checkpoint directly after an async LLM call.

## 4. Tool Execution Flow (Both Paths)
- CLI path:
  - `ChatLoop` parses OpenAI tool calls first, XML custom calls second (`parse_custom_tool_calls`).
  - `ToolCallHandler.execute()` delegates to `ToolExecutor`.
  - `ToolExecutor` performs normalize -> validate -> confirm -> execute against `ToolRegistry`.
  - Confirmation behavior:
    - permission auto-approve by tool permission category,
    - diff-based confirmation for file-modifying tools,
    - prompt confirmation otherwise.
  - Results are appended back into session as tool/user messages; terminal tools stop loop.
- TUI path:
  - `TuiChatLoop` handles OpenAI tool calls first, XML/JSON fallback second.
  - OpenAI calls split into:
    - auto-approved calls executed in parallel (`asyncio.gather` + `to_thread`),
    - confirmation-required calls executed sequentially via `AppCallbacks.request_confirmation()` -> `CLIConfirmScreen`.
  - UI feedback emitted through callbacks (`on_tool_start`, `on_tool_complete`, `on_tools_cleanup`) to `ToolPanel` and `ActivityBar`.
  - Tool results are appended to conversation (`role=tool` for OpenAI calls, aggregated `role=user` text for custom calls).
- Divergence notes:
  - CLI uses centralized `ToolExecutor` and synchronous control flow.
  - TUI executes directly against `ToolRegistry` with mixed parallel/sequential strategy and UI callback mediation.

## 5. Risk Observations (Initial)
- Checkpoint behavior divergence exists between CLI and TUI creation paths, which may create inconsistent summaries or restore behavior.
- Tool execution result shape differs (`role=tool` vs aggregated `role=user` custom-call results) and may complicate message-contract convergence.
- CLI and TUI both parse fallback custom calls, but through different execution pathways, increasing parity risk for edge cases.
