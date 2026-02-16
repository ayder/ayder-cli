# Phase 06 Risk Register

| Risk ID | Risk | Severity | Current Evidence | Mitigation Plan | Verification |
|---------|------|----------|------------------|-----------------|--------------|
| R06-LEGACY-RESIDUE | Dead compatibility/orchestration code remains active after cleanup | High | Phase 06 scope explicitly targets leftover cleanup | Require explicit removal validation and runtime-path checks during gate review | Code search and regression checks confirm no active legacy path remains |
| R06-BEHAVIOR-DRIFT | Cleanup accidentally changes user-visible CLI/TUI behavior | High | Internal contract cleanup can affect wrappers and error surfaces | Enforce behavior-preserving implementation and regression matrix coverage | QA regression matrix passes for CLI, TUI, checkpoint, and tool execution flows |
| R06-TEST-MAPPING-GAP | Obsolete tests are removed without clear replacement coverage | High | Final obsolete-test removal is in-scope this phase | QA must provide remove->replace ledger before gate PASS | Architect review confirms complete mapping or approved deprecation rationale |
| R06-FLAKY-ASYNC | Final suite remains nondeterministic in async-heavy workflows | Medium | Prior phases touched async orchestration and worker paths | QA hardening focuses on deterministic async behavior and flaky closure | Repeated suite runs stay green and stable at gate |
| R06-DOC-DRIFT | Architecture/handoff docs do not match final implementation | Medium | Final documentation update is a discrete DEV task | Require final documentation update with architect spot-check against runtime wiring | Gate review validates docs align with delivered code paths |

## Phase 06 Exit Rule

Phase 06 cannot PASS with open S1/S2 items in:

- active legacy path removal
- regression/test migration completeness
- final architecture documentation alignment
