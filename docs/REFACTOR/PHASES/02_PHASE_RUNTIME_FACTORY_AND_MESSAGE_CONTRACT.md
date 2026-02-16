# Phase 02 — Runtime Factory and Message Contract

## Phase Goal

Create one shared runtime composition path and normalize message representation risks before deeper refactor.

## Dependencies

- Phase 01 PASS.

---

## Phase Spec (Behavior Contract)

1. CLI and TUI construct core runtime dependencies through one shared factory/composition module.
2. Message handling is normalized so checkpoint summarization is robust for dict/object message shapes.
3. No output/UX regression in normal CLI or TUI flows.

---

## Developer Tasks

### DEV-02.1 Shared Runtime Factory
- Implement shared composition module (example target):
  - `src/ayder_cli/application/runtime_factory.py` (or `bootstrap.py`)
- Factory must assemble:
  - config
  - llm provider
  - process manager
  - tool registry
  - tool executor
  - checkpoint/memory components

### DEV-02.2 Wire CLI to Factory
- Update `src/ayder_cli/cli_runner.py` to use shared factory.
- Remove direct duplicated wiring blocks.

### DEV-02.3 Wire TUI to Factory
- Update `src/ayder_cli/tui/app.py` to use same factory.
- Keep current TUI UX behavior unchanged.

### DEV-02.4 Message Normalization Contract
- Add helper for normalized message access (dict/object safe).
- Integrate where needed in:
  - session append/raw handling
  - memory/checkpoint summary preparation

---

## Tester Tasks (Parallel)

### QA-02.1 Remove Obsolete Wiring Tests
- Remove tests that assert old private composition internals.
- Keep a remove→replace mapping.

### QA-02.2 Add Runtime Factory Tests
- Add tests proving CLI and TUI receive factory-built dependencies.
- Validate composition parity for key dependencies.

### QA-02.3 Add Message Contract Tests
- Cover mixed message representations:
  - dict message
  - provider object message with attributes
- Verify checkpoint summary generation does not fail for either.

---

## Architect Tasks (Gate)

### ARC-02.1 Architecture Review
- Verify duplicated composition roots are removed or reduced to thin wrappers.
- Confirm factory is the single source of dependency assembly.

### ARC-02.2 Command Gate
Run:
```bash
uv run poe lint
uv run poe typecheck
uv run poe test
```

### ARC-02.3 Acceptance Review
- Validate remove→replace test mapping.
- Ensure no phase-inappropriate architectural churn.

---

## Acceptance Criteria

- One shared runtime factory used by both CLI and TUI.
- Message normalization prevents dict/object shape regressions.
- Required tests for factory and message contract exist and pass.
- Architect PASS with no open S1/S2 issues.

---

## Exit Artifacts

- Runtime factory integration note
- Test migration mapping update
- Architect gate note (PASS/REWORK_REQUIRED)
