# Developer Risk Assessment — Phase 01

## R01-ASYNC: Async Migration Risk

**Description:** CLI currently uses a synchronous `ChatLoop` (blocking iteration loop + blocking LLM calls). TUI uses `TuiChatLoop` which is fully async (`async def run`, `asyncio.gather`, `await`). Convergence to a shared engine requires bridging these two concurrency models.

**Impact:** High

**Evidence from code:**
- `chat_loop.py`: `ChatLoop.run()` is a synchronous `while` loop calling blocking I/O (`client.chat(...)`).
- `tui/chat_loop.py`: `TuiChatLoop.run()` is `async def`, awaits LLM and tool calls throughout.

**Mitigation:**
- In Phase 01 (now): inventory all blocking I/O call sites in CLI path (`client.chat`, `ToolExecutor.execute_all`, checkpoint writes).
- In Phase 04: wrap CLI path in `asyncio.run()` shim or convert `ChatLoop` to async incrementally with a sync compatibility wrapper.
- Characterization tests against CLI `ChatLoop` behavior must be in place before any async migration starts.
- Define explicit await boundaries at `LLMClient.chat`, `ToolExecutor`, and `CheckpointManager` interfaces before convergence.

---

## R02-MSG: Message Shape Risk

**Description:** CLI and TUI produce different message structures for tool results. This will obstruct any attempt to share conversation history, logging, or replay logic.

**Impact:** Medium

**Evidence from code:**
- CLI: each tool result appended as `{"role": "tool", "tool_call_id": ..., "content": ...}` (OpenAI structured format).
- TUI XML/custom fallback: all custom-call results aggregated into one `{"role": "user", "content": "<aggregated text>"}` message.
- TUI OpenAI path: same `role=tool` format as CLI — only the custom-call fallback differs.

**Mitigation:**
- Phase 02 deliverable: document exact message schemas emitted by both paths.
- Design a `NormalizedToolResult` contract that both paths produce before appending to conversation history.
- Implement an adapter/mapper for the TUI custom-call aggregation to emit `role=tool` messages instead.
- Add regression tests asserting message shape parity for equivalent tool calls in both paths.

---

## R03-TEST: Test Breakage Risk

**Description:** Existing tests are coupled to internal implementation details of `ChatLoop`, `TuiChatLoop`, `ToolExecutor`, and checkpoint flow. Refactoring internals in later phases will break these tests.

**Impact:** Medium

**Evidence from code:**
- Test suite covers `ChatLoop` iteration, `IterationController` reset behavior, `ToolExecutor` pipeline, and checkpoint manager directly.
- Tests reference internal method signatures likely to change during loop unification.

**Mitigation:**
- Before each refactor phase: produce a behavior-contract test (characterization test) for the component being changed.
- Maintain a test migration map: old test file → new test file + behavior contract it validates.
- Prioritize integration-level tests that assert observable outputs (LLM messages, file writes) over unit tests on internals.
- Do not delete old tests until replacement characterization tests exist and pass.
- Current test count: 660+ tests, all passing in ~1.8s — establish this as the green baseline before any phase begins.

---

## Additional Developer Notes

- All risks sourced from architect's `01_RISK_REGISTER.md` and confirmed against live source code.
- No runtime behavior changes were introduced in Phase 01.
- Risk scores should be re-evaluated at Architect Gate review (Phase 01 Step D).
- R01-ASYNC is the highest-priority risk and should drive the async migration design in Phase 04.
