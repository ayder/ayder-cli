# PRD Master — Multi-Phase Refactor Program

## 1) Program Objective

Refactor `ayder-cli` into a cleaner, safer architecture with:

- one shared runtime composition path,
- one shared async orchestration engine for both CLI and TUI,
- decoupled service/presentation boundaries,
- converged checkpoint and tool execution behavior across interfaces.

This PRD is executed by three teams working in controlled parallel:

1. **Developers** — implement phase tasks
2. **Testers** — remove obsolete tests, add replacement tests from phase spec
3. **Architects** — gate each phase via review + test execution + acceptance checks

---

## 2) Non-Negotiable Constraints

1. **Single async loop**: CLI and TUI must run the same async orchestration logic.
   - CLI uses `asyncio.run(...)`
   - TUI `await`s the same engine in worker flow
2. No second sync orchestration loop should remain as source-of-truth.
3. Keep tool plugin/discovery model unless a phase explicitly requires targeted fixes.
4. No broad rewrite; phase-by-phase incremental delivery only.

---

## 3) Team Charters

## Developers (Execution Team)

- Implement only scoped phase tasks.
- Keep diffs minimal and behavior-preserving unless phase spec says behavior changes.
- Add/adjust code comments only where logic is non-obvious.
- Provide short implementation notes for Architect review.

## Testers (Validation Team)

- Work in parallel with Developers during each phase.
- Remove obsolete tests tied to replaced internals.
- Add replacement tests tied to phase spec behavior.
- Maintain or improve coverage in changed areas.
- Produce phase test report: what was removed, what was added, why.

## Architects (Gate Team)

- Review architecture and boundary adherence.
- Run required checks and decide gate status:
  - **PASS**
  - **REWORK_REQUIRED**
- Provide actionable rework items for Developers/Testers.
- Own acceptance criteria enforcement and phase transition approval.

---

## 4) Phase Execution Workflow

1. **Phase Kickoff (Architect)**
   - Publish phase scope and acceptance checklist.
   - Confirm dependency readiness from previous phase.

2. **Parallel Implementation (Developers + Testers)**
   - Developers implement.
   - Testers update/remove/add tests simultaneously.

3. **Architect Gate**
   - Code review + boundary checks.
   - Run mandatory command set.
   - Decide PASS or REWORK_REQUIRED.

4. **Rework Loop (if needed)**
   - Architect issues rework list with severity tags.
   - Developers/Testers patch and resubmit.
   - Gate rerun by Architect.

5. **Phase Closure**
   - Acceptance criteria all green.
   - Artifacts archived.
   - Next phase unlocked.

---

## 5) Mandatory Command Set (Architect Gates)

Use project standard commands:

```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

Additionally:

- For TUI/loop phases: run targeted TUI tests (and `test-all` when needed):
  ```bash
  uv run poe test-all
  ```

Architects may run targeted tests first, but gate is not PASS without full required checks.

---

## 6) Test Migration Policy (Required Each Phase)

When Testers remove tests:

1. A removed test must be mapped to:
   - replacement test(s), or
   - explicit deprecation rationale approved by Architects.
2. No test removal without behavior coverage replacement unless feature is intentionally removed.
3. Keep a phase-level table:
   - Removed test
   - Reason obsolete
   - Replacement test

---

## 7) Acceptance Gate Rubric

Each phase is accepted only if all are true:

- Functional criteria met (phase-specific).
- Architecture constraints met (especially async loop convergence path).
- Required tests added and obsolete tests migrated.
- Lint/typecheck/test commands pass for phase scope.
- Architect review has no unresolved high-severity issues.

---

## 8) Phase Map

| Phase | Focus | Primary Outcome |
|---|---|---|
| 01 | Baseline & governance | Stable baseline, inventory, gate mechanics |
| 02 | Runtime factory + message contract | Shared composition + normalized message model |
| 03 | Service/UI decoupling | No direct service → UI imports |
| 04 | Shared async engine | One async loop for CLI + TUI |
| 05 | Checkpoint + execution convergence | Same checkpoint/tool policy across interfaces |
| 06 | Stabilization & cleanup | Remove leftovers, finalize architecture |

---

## 9) Rework Severity Model

- **S1 (Critical):** correctness/security regressions, broken acceptance criteria
- **S2 (Major):** architectural boundary violations, major missing tests
- **S3 (Minor):** non-blocking cleanup/documentation

PASS requires no open S1/S2 items.

---

## 10) Final Program Exit Criteria

Program completes when:

1. CLI and TUI use the same async orchestration engine.
2. Service layer is presentation-agnostic.
3. Checkpoint and tool execution behavior is converged across interfaces.
4. Deprecated/obsolete tests are replaced with spec-aligned tests.
5. Architects sign off phase 06 as PASS.
