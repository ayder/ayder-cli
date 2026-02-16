# Phase 01 Refactor Workspace Scaffolding Plan

## Objective
Define the future application composition module layout without wiring runtime behavior in this phase.

## Target Structure (Phase 01 Placeholder)
```text
src/ayder_cli/
└── application/
    ├── __init__.py
    └── README.md
```

## Directory Creation Commands
```bash
mkdir -p src/ayder_cli/application
touch src/ayder_cli/application/__init__.py
```

## Placeholder File Content

### `src/ayder_cli/application/__init__.py`
```python
"""Application composition layer placeholders for refactor phases."""
```

### `src/ayder_cli/application/README.md`
```markdown
# application package

This package will host runtime composition and orchestration boundaries introduced
incrementally in refactor phases 02-06. Phase 01 keeps this package as scaffold
only; no runtime wiring is allowed in this phase.
```

## Phase-by-Phase Population Plan
- **Phase 02**: Introduce runtime-factory and message-contract assembly entry points.
- **Phase 03**: Add service-to-UI boundary adapters/interfaces.
- **Phase 04**: Introduce shared async engine composition hooks for CLI/TUI.
- **Phase 05**: Add converged checkpoint/tool execution policy wiring.
- **Phase 06**: Remove transitional compatibility glue and finalize package ownership docs.

## Guardrails
- Keep existing import paths untouched in Phase 01.
- Do not move orchestration logic yet.
- Any new module additions must be placeholder-only until phase-scoped approval.
