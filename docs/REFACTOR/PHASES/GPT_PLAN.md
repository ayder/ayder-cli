# Refactor PRD Delivery Plan

## Problem
Produce a detailed multi-phase PRD in `docs/REFACTOR/PHASES` with explicit team workflows for Developers, Testers, and Architects, including phase gates, rework loops, and acceptance criteria.

## Approach
Create a master governance PRD plus per-phase execution documents that define implementation tasks, parallel testing tasks (including obsolete test removal and replacement), architect gate checks, and clear exit criteria.

## Workplan
- [x] Inspect existing docs and test layout
- [x] Define phase architecture and team operating model
- [x] Create master PRD (`00_PRD_MASTER.md`)
- [x] Create phase docs 01..06 with team-specific task breakdowns
- [x] Encode async-loop mandate (shared async engine for CLI and TUI)
- [x] Add acceptance criteria and rework protocol per phase
- [x] Verify docs consistency and presence under `docs/REFACTOR/PHASES`

## Notes
- CLI and TUI must use one shared async orchestration loop.
- Testers remove obsolete tests only with replacement coverage mapping.
- Architects gate each phase with lint/typecheck/test (and test-all where required).

## Next Steps
- [ ] User reviews `docs/REFACTOR/PHASES/GPT_PLAN.md` and requests adjustments if needed.
