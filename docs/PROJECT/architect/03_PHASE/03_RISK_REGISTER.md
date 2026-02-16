# Phase 03 Risk Register

| Risk ID | Risk | Severity | Current Evidence | Mitigation Plan | Verification |
|---------|------|----------|------------------|-----------------|--------------|
| R03-BOUNDARY | Service modules keep direct imports to `ayder_cli.ui`, violating architecture boundary | High | `services/tools/executor.py` and `services/llm.py` currently import UI helpers | Introduce `InteractionSink` and `ConfirmationPolicy` protocols; remove direct UI imports from services | `rg "from ayder_cli\\.ui import|import ayder_cli\\.ui" src/ayder_cli/services` returns no matches |
| R03-BEHAVIOR | CLI/TUI output and confirmation UX regresses during decoupling | High | Existing behavior is coupled to specific UI function calls in service code | Add CLI/TUI adapters that preserve exact user-facing flow and text semantics | Interface-driven tests pass; manual smoke checks for CLI and TUI interaction parity |
| R03-DI | Runtime composition becomes fragmented across entry points | Medium | Phase 02 introduced shared runtime factory; Phase 03 adds adapter injection complexity | Keep adapter selection in runtime factory and forbid ad-hoc service construction in callers | Factory-based construction tests pass in CLI/TUI integration points |
| R03-TEST-FIRST | Developer implementation diverges from tester-defined interface contracts | Medium | Phase 03 process requires tests-first in QA branch | Publish explicit interface spec before implementation and require dev branch to pull QA tests first | Gate review confirms interface alignment and contract test pass |
| R03-EVENTS | Verbose/debug and tool lifecycle events become inconsistent across providers | Medium | LLM providers and executor currently emit UI output directly with mixed pathways | Centralize interaction events behind a single sink interface and shared adapter policy | Provider/executor tests validate event emission expectations |

## Carry-Over Context

- Phase 02 passed and provided shared runtime composition; Phase 03 builds on
  that foundation by isolating presentation concerns behind interfaces.

## Phase 03 Exit Expectation

Phase 03 cannot be architect-approved with open S1/S2 issues in:

- service-to-presentation import boundaries
- confirmation/output behavior equivalence
- adapter injection consistency across CLI and TUI
