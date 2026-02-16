# Phase 04 Risk Register

| Risk ID | Risk | Severity | Current Evidence | Mitigation Plan | Verification |
|---------|------|----------|------------------|-----------------|--------------|
| R04-SOURCE-TRUTH | CLI/TUI each keep separate orchestration logic after migration | High | Existing loop logic spans multiple modules/surfaces | Enforce single shared async engine in `application/agent_engine.py`; wrappers delegate only | Code search confirms one orchestration core; gate review verifies no duplicate decision loops |
| R04-WRAPPER-DRIFT | Wrapper-specific behavior diverges between CLI and TUI for same inputs | High | Surface-specific code paths can drift during refactor | Add wrapper contract tests and equivalence tests using identical mocked LLM/tool responses | QA equivalence suite passes and architect confirms parity |
| R04-CANCEL | TUI cancellation handling regresses when switching to shared coroutine | High | TUI worker lifecycle currently controls cancellation semantics | Preserve cancellation bridge in wrapper; add cancellation-focused tests in shared engine and TUI path | Cancellation tests pass; no hanging worker behavior in review |
| R04-LEGACY | Legacy sync loop remains functional source-of-truth by accident | Medium | Legacy sync pathways exist and may retain control flow | Restrict legacy loop to thin compatibility wrapper or remove dead logic | Code search and tests validate wrapper-only behavior |
| R04-TEST-FIRST | Dev implementation starts before QA contracts, causing rework | Medium | Phase timeline introduces parallel DEV/QA activity | Lock phase as mandatory test-first; QA contract tests must exist before DEV merge review | Architect re-check confirms QA-defined contracts predate and validate DEV implementation |

## Dependency Confirmation

- Phase 03 status is PASS (`.ayder/architect_to_PM_phase03_gate.md`).
- Phase 04 kickoff is unblocked.

## Exit Gate Expectation

Phase 04 cannot pass architect gate with open S1/S2 issues in:

- shared async source-of-truth enforcement
- CLI/TUI wrapper parity and cancellation behavior
- legacy sync-loop de-primarying
