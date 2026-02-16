# Phase 03 Architecture Design — Service/UI Decoupling

## Scope and Objective

Phase 03 removes direct presentation coupling from service-layer modules and
replaces it with explicit interaction contracts. The goal is to keep CLI/TUI
behavior functionally equivalent while moving display/confirmation behavior to
adapters owned by entry and presentation layers.

---

## Current Coupling Snapshot

Current direct service-to-presentation imports:

- `src/ayder_cli/services/tools/executor.py` imports functions from
  `ayder_cli.ui` for confirmation, tool call rendering, and result rendering.
- `src/ayder_cli/services/llm.py` imports `print_llm_request_debug` from
  `ayder_cli.ui` in provider verbose paths.

This creates a reverse dependency from services to presentation that blocks
clean runtime composition and test-first interface validation.

---

## Target Boundary

### Layer Rule

- `src/ayder_cli/services/**` MUST NOT import `ayder_cli.ui`.
- Presentation concerns (Rich rendering, TUI callbacks) live in adapters.
- Services operate only on interface contracts and data.

### Interface Contracts (Phase 03 Canonical)

Proposed location: `src/ayder_cli/services/interactions.py`

```python
from typing import Any, Protocol


class InteractionSink(Protocol):
    def on_tool_call(self, tool_name: str, args_json: str) -> None: ...
    def on_tool_result(self, result: str) -> None: ...
    def on_tool_skipped(self) -> None: ...
    def on_file_preview(self, file_path: str) -> None: ...
    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None: ...


class ConfirmationPolicy(Protocol):
    def confirm_action(self, description: str) -> bool: ...
    def confirm_file_diff(
        self, file_path: str, new_content: str, description: str
    ) -> bool: ...
```

### Service Integration Targets

1. `ToolExecutor` constructor receives:
   - `interaction_sink: InteractionSink`
   - `confirmation_policy: ConfirmationPolicy`
2. `LLMProvider` verbose paths use `InteractionSink.on_llm_request_debug(...)`
   instead of direct `ui.py` imports.

---

## Adapter Strategy

### CLI Adapter

Adapter module owned by entry/presentation side maps interfaces to existing Rich
UI functions so current behavior remains equivalent.

- `InteractionSink` → existing print functions currently in `ui.py`
- `ConfirmationPolicy` → existing prompt/diff confirmation flow

### TUI Adapter

Adapter module owned by TUI side maps interfaces to TUI callbacks/widgets.

- non-blocking event notifications for tool states
- confirmation requests routed through current modal/approval mechanics

---

## Dependency Injection Plan

`create_runtime()` remains the composition root:

1. Build service instances with adapter instances injected.
2. CLI runtime injects CLI adapter pair.
3. TUI runtime injects TUI adapter pair.
4. Default no-op adapters allowed for non-interactive/testing scenarios.

This preserves single construction flow while keeping adapter choice
surface-specific.

---

## Event Model (Minimal Contract)

A lightweight event sink is preferred over introducing a heavyweight event bus in
Phase 03. If event objects are needed, keep them local and typed:

```python
@dataclass
class ToolEvent:
    kind: str  # "tool_call" | "tool_result" | "tool_skipped"
    name: str | None = None
    payload: str | None = None
```

Phase 03 scope prioritizes decoupling; broad event bus expansion can be deferred
to later phases if needed.

---

## Test-First Contract Guidance

Testers define interface-first tests before implementation in
`qa/03/service-ui-decoupling`:

- service modules import boundary guard tests
- executor behavior through fake sink + fake confirmation policy
- verbose LLM reporting through injected sink

Developers then implement against these tests in
`dev/03/service-ui-decoupling`.

---

## Acceptance Mapping

Phase 03 Step A is complete when:

- service/UI contracts are documented for tester/dev branches
- adapter ownership is explicitly scoped to CLI/TUI sides
- DI approach is clear for runtime composition
- risks are published for gate planning

