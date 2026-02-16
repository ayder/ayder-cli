# Phase 02 Risk Register

| Risk ID | Risk | Severity | Current Evidence | Mitigation Plan | Verification |
|---------|------|----------|------------------|-----------------|--------------|
| R02-FACTORY | Shared factory adoption can break CLI/TUI initialization parity | High | CLI uses `_build_services()` while TUI composes inline in `AyderApp.__init__()` | Introduce `create_runtime()` as single composition root; migrate CLI and TUI via thin wrappers; keep TUI-only UI wiring local | Runtime factory tests validate component parity; `lint`/`typecheck`/`test` gate all pass |
| R02-MSG | Mixed message shapes (dict + object) can break checkpoint summary and memory/compact flows | High | `append_raw()` can store objects; multiple summary paths use dict-only `msg.get(...)` | Add message contract helpers for dict/object-safe role/content access; apply in checkpoint and memory summary paths | Message-contract tests cover dict and object messages with checkpoint summary generation |
| R02-PARITY | CLI and TUI may diverge in behavior while both claim shared composition | Medium | TUI currently omits `llm_provider`/`tool_executor` when creating `MemoryManager`; custom-call result shaping differs by loop | Enforce shared runtime component list from factory; explicitly document allowed surface differences (UI callbacks only) | Tests assert CLI/TUI consume factory-built dependencies and preserve expected UX behavior |

## Carry-Over From Phase 01

- `R02-MSG` from Phase 01 remains open and is escalated to **High** for execution in Phase 02 due direct behavior impact.

## Phase 02 Exit Expectation

Phase 02 cannot be architect-approved with open S1/S2 issues in:

- shared factory adoption correctness
- message normalization correctness
- coverage for remove→replace test mapping in affected paths
