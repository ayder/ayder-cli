# Phase 01 Risk Register

| Risk ID | Risk | Severity | Current Evidence | Mitigation Proposal | Owner |
|---------|------|----------|------------------|---------------------|-------|
| R01-ASYNC | Async migration from current sync CLI loop to shared async engine can introduce behavior drift | High | CLI uses `Agent -> ChatLoop.run()` synchronous loop while TUI uses `TuiChatLoop.run()` async workflow | Freeze baseline with characterization coverage before convergence; define explicit await boundaries and transition checkpoints in Phase 04 | Architect + Dev |
| R02-MSG | Message shape divergence between CLI and TUI tool-result handling can break future shared contract | Medium | CLI appends tool messages through `ToolExecutor`; TUI mixes `role=tool` + aggregated `role=user` fallback results | Define normalized message contract in Phase 02 and add adapter mapping tests for both pipelines | Architect + Dev + QA |
| R03-TEST | Refactor phases may invalidate internals-coupled tests and reduce confidence | Medium | Existing tests span CLI, checkpoint, TUI loop, and tool execution internals likely to shift | Build remove->replace test migration map and characterization suite per phase before deleting obsolete tests | QA + Architect |

## Additional Notes
- No intentional runtime behavior changes were introduced in this kickoff phase.
- Risks are tracked as open and should be re-scored at Architect Gate step (Phase 01 Step D).
