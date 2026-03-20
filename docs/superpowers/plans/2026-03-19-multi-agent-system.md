# Multi-Agent System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a full multi-agent system where users define specialized agents (via `config.toml` or `/agent` TUI command), each running as an independent `ChatLoop` with its own LLM provider, model, and context window, producing structured summaries injected back into the main agent's context.

**Architecture:** Agents are first-class runtime objects managed by `AgentRegistry`. Each agent runs an isolated `ChatLoop` via `AgentRunner`, with shared `ProcessManager`/`ProjectContext` but isolated `AIProvider`/`ToolRegistry`/`ContextManager`. **All dispatches are non-blocking (Approach A):** both LLM-dispatched (`call_agent` tool) and user-dispatched (`/agent` command) fire-and-forget the agent in the background. The agent's `AgentSummary` is injected into the main context via `ChatLoop`'s `pre_iteration_hook` when the agent completes. `AgentCallbacks` auto-approves tool confirmations and routes events to an `AgentPanel` widget.

**Dispatch flow:**
- `AgentRegistry.dispatch(name, task)` is a **sync method** (thread-safe via `run_coroutine_threadsafe`)
- Schedules agent run as an `asyncio.Task` on the event loop, returns immediately with a status string
- Both `call_agent` tool handler and `/agent` command handler call the same `dispatch()` method
- Summary arrives asynchronously via `_summary_queue` → `pre_iteration_hook` → system message injection

**Tech Stack:** Python 3.12, Pydantic (config), asyncio, Textual (TUI), existing `ChatLoop`/`ChatCallbacks` from `loops/chat_loop.py`.

**Spec:** `docs/superpowers/specs/2026-03-19-multi-agent-support-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/ayder_cli/agents/__init__.py` | Package exports: `AgentConfig`, `AgentSummary`, `AgentRunner`, `AgentRegistry` |
| `src/ayder_cli/agents/config.py` | `AgentConfig` Pydantic model |
| `src/ayder_cli/agents/summary.py` | `AgentSummary` dataclass |
| `src/ayder_cli/agents/runner.py` | `AgentRunner` — wraps one `ChatLoop` execution per agent dispatch |
| `src/ayder_cli/agents/registry.py` | `AgentRegistry` — lifecycle management, dispatch, capability prompts |
| `src/ayder_cli/agents/callbacks.py` | `AgentCallbacks` — implements `ChatCallbacks` for autonomous agent runs |
| `src/ayder_cli/agents/tool.py` | `call_agent` tool definition + handler |
| `tests/agents/__init__.py` | Test package |
| `tests/agents/test_config.py` | Tests for `AgentConfig` + `Config` agent parsing |
| `tests/agents/test_summary.py` | Tests for `AgentSummary` |
| `tests/agents/test_runner.py` | Tests for `AgentRunner` |
| `tests/agents/test_registry.py` | Tests for `AgentRegistry` |
| `tests/agents/test_callbacks.py` | Tests for `AgentCallbacks` |
| `tests/agents/test_tool.py` | Tests for `call_agent` tool |

### Modified Files

| File | Changes |
|------|---------|
| `src/ayder_cli/core/config.py` | Add `agent_timeout` field, `agents` dict field, update `flatten_nested_sections` to parse `[agents.*]` TOML sections |
| `src/ayder_cli/application/runtime_factory.py` | Add `create_agent_runtime()` factory function |
| `src/ayder_cli/loops/chat_loop.py` | Add optional `pre_iteration_hook` callback to `ChatLoop.run()` |
| `src/ayder_cli/tui/app.py` | Initialize `AgentRegistry`, mount `AgentPanel`, wire summary injection |
| `src/ayder_cli/tui/widgets.py` | Add `AgentPanel` widget |
| `src/ayder_cli/tui/commands.py` | Add `/agent` command handler |
| `src/ayder_cli/tools/registry.py` | Add `register_dynamic_tool()`, `_dynamic_definitions` list, update `get_schemas()`/`get_system_prompts()` |
| `.claude/AGENTS.md` | Update structure docs for new `agents/` package |
| `docs/PROJECT_STRUCTURE.md` | Update architecture docs |

---

## Task 1: AgentConfig + Config Integration

**Files:**
- Create: `src/ayder_cli/agents/__init__.py`
- Create: `src/ayder_cli/agents/config.py`
- Modify: `src/ayder_cli/core/config.py:232-308` (Config model + flatten_nested_sections)
- Test: `tests/agents/__init__.py`
- Test: `tests/agents/test_config.py`

- [ ] **Step 1: Write the failing tests for AgentConfig**

```python
# tests/agents/test_config.py
"""Tests for AgentConfig and Config agent parsing."""

import pytest
from ayder_cli.agents.config import AgentConfig


class TestAgentConfig:
    def test_minimal_agent_config(self):
        """AgentConfig with only name and system_prompt."""
        cfg = AgentConfig(name="test-agent", system_prompt="You are a test agent.")
        assert cfg.name == "test-agent"
        assert cfg.provider is None
        assert cfg.model is None
        assert cfg.system_prompt == "You are a test agent."

    def test_full_agent_config(self):
        """AgentConfig with all fields set."""
        cfg = AgentConfig(
            name="code-reviewer",
            provider="anthropic",
            model="claude-sonnet-4-5",
            system_prompt="You review code.",
        )
        assert cfg.name == "code-reviewer"
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-5"

    def test_agent_config_is_frozen(self):
        """AgentConfig should be immutable."""
        cfg = AgentConfig(name="test", system_prompt="test")
        with pytest.raises(Exception):
            cfg.name = "changed"

    def test_empty_system_prompt_default(self):
        """system_prompt defaults to empty string."""
        cfg = AgentConfig(name="test")
        assert cfg.system_prompt == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ayder_cli.agents'`

- [ ] **Step 3: Implement AgentConfig**

```python
# src/ayder_cli/agents/__init__.py
"""Multi-agent system: config, registry, runner, and tool."""

from ayder_cli.agents.config import AgentConfig

__all__ = ["AgentConfig"]
```

```python
# src/ayder_cli/agents/config.py
"""AgentConfig — Pydantic model for agent definitions."""

from pydantic import BaseModel, ConfigDict


class AgentConfig(BaseModel):
    """Configuration for a single agent, parsed from [agents.<name>] TOML sections."""

    model_config = ConfigDict(frozen=True)

    name: str
    provider: str | None = None      # None = inherit from main config
    model: str | None = None         # None = inherit from main config
    system_prompt: str = ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Write failing tests for Config agent parsing**

Add to `tests/agents/test_config.py`:

```python
from ayder_cli.core.config import Config


class TestConfigAgentParsing:
    def test_config_default_no_agents(self):
        """Config has empty agents dict by default."""
        cfg = Config()
        assert cfg.agents == {}
        assert cfg.agent_timeout == 300

    def test_config_agent_timeout_custom(self):
        """agent_timeout can be set via app section."""
        cfg = Config(**{"app": {"agent_timeout": 600}, "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}}})
        assert cfg.agent_timeout == 600

    def test_config_parses_agents_section(self):
        """Agents parsed from [agents.*] TOML sections."""
        data = {
            "app": {"provider": "openai"},
            "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}},
            "agents": {
                "code-reviewer": {
                    "system_prompt": "You review code.",
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-5",
                },
                "test-writer": {
                    "system_prompt": "You write tests.",
                },
            },
        }
        cfg = Config(**data)
        assert len(cfg.agents) == 2
        assert "code-reviewer" in cfg.agents
        assert cfg.agents["code-reviewer"].name == "code-reviewer"
        assert cfg.agents["code-reviewer"].provider == "anthropic"
        assert cfg.agents["code-reviewer"].model == "claude-sonnet-4-5"
        assert cfg.agents["test-writer"].name == "test-writer"
        assert cfg.agents["test-writer"].provider is None

    def test_config_agent_name_from_key(self):
        """Agent name is derived from TOML key, overriding explicit name."""
        data = {
            "app": {"provider": "openai"},
            "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}},
            "agents": {
                "my-agent": {
                    "name": "wrong-name",
                    "system_prompt": "test",
                },
            },
        }
        cfg = Config(**data)
        assert cfg.agents["my-agent"].name == "my-agent"

    def test_config_agent_timeout_validation(self):
        """agent_timeout must be positive."""
        with pytest.raises(Exception):
            Config(**{"app": {"agent_timeout": 0}})
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_config.py::TestConfigAgentParsing -v`
Expected: FAIL — `Config` has no `agents` field or `agent_timeout` field

- [ ] **Step 7: Add agents and agent_timeout to Config model**

**Note:** Do NOT add `from __future__ import annotations` — it breaks Pydantic's runtime type resolution for validators. Python 3.12 supports `dict[str, Any]` natively.

Add two fields to `Config` class body (after `context_manager` field, around line 259):

```python
    agent_timeout: int = Field(default=300)
    agents: dict[str, Any] = Field(default_factory=dict)  # dict[str, AgentConfig] — Any to avoid circular import
```

Add validator for `agent_timeout` (after `validate_max_history_messages`, around line 349):

```python
    @field_validator("agent_timeout")
    @classmethod
    def validate_agent_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("agent_timeout must be positive")
        return v
```

Update `flatten_nested_sections` to parse `[agents.*]` sections. Add before `return new_data` (around line 308):

```python
        # Parse [agents.*] sections into AgentConfig objects
        agents_section = data.get("agents")
        if isinstance(agents_section, dict):
            from ayder_cli.agents.config import AgentConfig
            parsed_agents = {}
            for key, agent_data in agents_section.items():
                if isinstance(agent_data, dict):
                    agent_data = agent_data.copy()
                    agent_data["name"] = key  # TOML key wins
                    parsed_agents[key] = AgentConfig(**agent_data)
            new_data["agents"] = parsed_agents
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_config.py -v`
Expected: PASS (9 tests)

- [ ] **Step 9: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ --timeout=10 -x -q`
Expected: All existing tests pass

- [ ] **Step 10: Commit**

```bash
git add src/ayder_cli/agents/__init__.py src/ayder_cli/agents/config.py src/ayder_cli/core/config.py tests/agents/__init__.py tests/agents/test_config.py
git commit -m "feat(agents): add AgentConfig and Config integration for [agents.*] TOML parsing"
```

---

## Task 2: AgentSummary

**Files:**
- Create: `src/ayder_cli/agents/summary.py`
- Modify: `src/ayder_cli/agents/__init__.py`
- Test: `tests/agents/test_summary.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/test_summary.py
"""Tests for AgentSummary dataclass."""

from ayder_cli.agents.summary import AgentSummary


class TestAgentSummary:
    def test_completed_summary(self):
        s = AgentSummary(
            agent_name="code-reviewer",
            status="completed",
            summary="Found 3 issues.",
            error=None,
        )
        assert s.agent_name == "code-reviewer"
        assert s.status == "completed"
        assert s.summary == "Found 3 issues."
        assert s.error is None

    def test_error_summary(self):
        s = AgentSummary(
            agent_name="test-writer",
            status="error",
            summary="Partial progress: wrote 2 tests.",
            error="API key invalid",
        )
        assert s.status == "error"
        assert s.error == "API key invalid"

    def test_timeout_summary(self):
        s = AgentSummary(
            agent_name="analyzer",
            status="timeout",
            summary="Analyzed 5 of 10 files.",
            error=None,
        )
        assert s.status == "timeout"

    def test_format_for_injection(self):
        """format_for_injection produces a readable multi-line string."""
        s = AgentSummary(
            agent_name="reviewer",
            status="completed",
            summary="All good.",
            error=None,
        )
        text = s.format_for_injection()
        assert "reviewer" in text
        assert "completed" in text
        assert "All good." in text

    def test_format_for_injection_with_error(self):
        s = AgentSummary(
            agent_name="reviewer",
            status="error",
            summary="Partial.",
            error="Connection timeout",
        )
        text = s.format_for_injection()
        assert "Connection timeout" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ayder_cli.agents.summary'`

- [ ] **Step 3: Implement AgentSummary**

```python
# src/ayder_cli/agents/summary.py
"""AgentSummary — structured result of an agent run."""

from dataclasses import dataclass


@dataclass
class AgentSummary:
    """Result of a single agent dispatch."""

    agent_name: str
    status: str          # "completed" | "timeout" | "error"
    summary: str         # what the agent accomplished (even partial)
    error: str | None    # error details if status != "completed"

    def format_for_injection(self) -> str:
        """Format summary for injection into the main agent's context."""
        lines = [
            f'[Agent "{self.agent_name}" {self.status}]',
            f"STATUS: {self.status}",
            f"SUMMARY: {self.summary}",
        ]
        if self.error:
            lines.append(f"ERROR: {self.error}")
        return "\n".join(lines)
```

Update `src/ayder_cli/agents/__init__.py`:

```python
"""Multi-agent system: config, registry, runner, and tool."""

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.summary import AgentSummary

__all__ = ["AgentConfig", "AgentSummary"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_summary.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/summary.py src/ayder_cli/agents/__init__.py tests/agents/test_summary.py
git commit -m "feat(agents): add AgentSummary dataclass with format_for_injection"
```

---

## Task 3: AgentCallbacks

**Files:**
- Create: `src/ayder_cli/agents/callbacks.py`
- Test: `tests/agents/test_callbacks.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/test_callbacks.py
"""Tests for AgentCallbacks — autonomous agent callback implementation."""

import asyncio
import pytest
from ayder_cli.agents.callbacks import AgentCallbacks
from ayder_cli.loops.chat_loop import ChatCallbacks


class TestAgentCallbacks:
    def test_implements_protocol(self):
        """AgentCallbacks must satisfy the ChatCallbacks protocol."""
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        assert isinstance(cb, ChatCallbacks)

    def test_on_assistant_content(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        # Should not raise — just collects content
        cb.on_assistant_content("Hello world")
        assert cb.last_content == "Hello world"

    def test_on_assistant_content_accumulates(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        cb.on_assistant_content("Hello ")
        cb.on_assistant_content("world")
        assert cb.last_content == "Hello world"

    def test_is_cancelled_false_by_default(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        assert cb.is_cancelled() is False

    def test_is_cancelled_true_when_event_set(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        cancel_event.set()
        assert cb.is_cancelled() is True

    @pytest.mark.asyncio
    async def test_request_confirmation_auto_approves(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        result = await cb.request_confirmation("run_shell_command", {"command": "ls"})
        assert result is not None
        assert getattr(result, "action", None) == "approve"

    def test_noop_methods_dont_raise(self):
        """All no-op callbacks should not raise."""
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        cb.on_thinking_start()
        cb.on_thinking_stop()
        cb.on_thinking_content("thinking...")
        cb.on_token_usage(100)
        cb.on_tool_start("id1", "read_file", {"path": "test.py"})
        cb.on_tool_complete("id1", "file contents")
        cb.on_tools_cleanup()
        cb.on_system_message("System message")

    def test_on_progress_callback(self):
        """If on_progress is provided, it receives agent events."""
        events = []
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(
            agent_name="test",
            cancel_event=cancel_event,
            on_progress=lambda name, event, data: events.append((name, event, data)),
        )
        cb.on_tool_start("id1", "read_file", {"path": "test.py"})
        assert len(events) == 1
        assert events[0][0] == "test"
        assert events[0][1] == "tool_start"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_callbacks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ayder_cli.agents.callbacks'`

- [ ] **Step 3: Implement AgentCallbacks**

```python
# src/ayder_cli/agents/callbacks.py
"""AgentCallbacks — ChatCallbacks implementation for autonomous agent runs.

Agents auto-approve all tool confirmations. Events are optionally forwarded
to a progress callback (used by AgentPanel in the TUI).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class AgentConfirmResult:
    """Auto-approval result returned by AgentCallbacks.request_confirmation."""
    action: str = "approve"


class AgentCallbacks:
    """ChatCallbacks implementation for agent runs.

    - Auto-approves all tool confirmations
    - Tracks last assistant content (for summary extraction)
    - Cancellation via asyncio.Event
    - Optional progress callback for TUI integration
    """

    def __init__(
        self,
        agent_name: str,
        cancel_event: asyncio.Event,
        on_progress: Callable[[str, str, Any], None] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self._cancel_event = cancel_event
        self._on_progress = on_progress
        self.last_content: str = ""

    def _emit(self, event: str, data: Any = None) -> None:
        if self._on_progress:
            self._on_progress(self.agent_name, event, data)

    # -- ChatCallbacks protocol methods --

    def on_thinking_start(self) -> None:
        self._emit("thinking_start")

    def on_thinking_stop(self) -> None:
        self._emit("thinking_stop")

    def on_assistant_content(self, text: str) -> None:
        self.last_content += text
        self._emit("assistant_content", text)

    def on_thinking_content(self, text: str) -> None:
        self._emit("thinking_content", text)

    def on_token_usage(self, total_tokens: int) -> None:
        self._emit("token_usage", total_tokens)

    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None:
        self._emit("tool_start", {"call_id": call_id, "name": name, "arguments": arguments})

    def on_tool_complete(self, call_id: str, result: str) -> None:
        self._emit("tool_complete", {"call_id": call_id, "result": result})

    def on_tools_cleanup(self) -> None:
        self._emit("tools_cleanup")

    def on_system_message(self, text: str) -> None:
        self._emit("system_message", text)

    async def request_confirmation(
        self, name: str, arguments: dict
    ) -> AgentConfirmResult:
        """Auto-approve all tool confirmations for autonomous agent runs."""
        logger.debug(f"Agent '{self.agent_name}' auto-approving tool: {name}")
        return AgentConfirmResult(action="approve")

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_callbacks.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/callbacks.py tests/agents/test_callbacks.py
git commit -m "feat(agents): add AgentCallbacks with auto-approval and progress events"
```

---

## Task 4: create_agent_runtime() Factory

**Files:**
- Modify: `src/ayder_cli/application/runtime_factory.py:1-79`
- Test: `tests/test_runtime_factory.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runtime_factory.py` (new test class):

```python
# Add imports at top:
from unittest.mock import patch, MagicMock
from ayder_cli.agents.config import AgentConfig
from ayder_cli.application.runtime_factory import create_agent_runtime

class TestCreateAgentRuntime:
    """Tests for agent-specific runtime assembly."""

    def test_creates_runtime_with_agent_config(self):
        """create_agent_runtime returns RuntimeComponents for an agent."""
        agent_cfg = AgentConfig(name="test-agent", system_prompt="You are a test.")
        parent_cfg = Config()
        project_ctx = ProjectContext(".")
        pm = MagicMock()

        mock_registry = MagicMock()
        mock_registry.get_system_prompts.return_value = ""

        with patch("ayder_cli.application.runtime_factory.provider_orchestrator") as mock_orch, \
             patch("ayder_cli.application.runtime_factory.create_default_registry", return_value=mock_registry):
            mock_provider = MagicMock()
            mock_orch.create.return_value = mock_provider

            rt = create_agent_runtime(
                agent_config=agent_cfg,
                parent_config=parent_cfg,
                project_ctx=project_ctx,
                process_manager=pm,
                permissions={"r", "w", "x"},
            )

        assert rt.config is not None
        assert rt.llm_provider == mock_provider
        assert rt.process_manager == pm
        assert rt.project_ctx == project_ctx
        assert rt.system_prompt != ""
        assert "You are a test." in rt.system_prompt

    def test_agent_provider_override(self):
        """When agent specifies provider, load_config_for_provider is used."""
        agent_cfg = AgentConfig(
            name="test", provider="anthropic", system_prompt="test"
        )
        parent_cfg = Config()
        project_ctx = ProjectContext(".")
        pm = MagicMock()

        mock_registry = MagicMock()
        mock_registry.get_system_prompts.return_value = ""

        with patch("ayder_cli.application.runtime_factory.provider_orchestrator") as mock_orch, \
             patch("ayder_cli.application.runtime_factory.load_config_for_provider") as mock_load, \
             patch("ayder_cli.application.runtime_factory.create_default_registry", return_value=mock_registry):
            mock_load.return_value = Config(provider="anthropic", driver="anthropic", api_key="test-key", model="claude-sonnet-4-5")
            mock_orch.create.return_value = MagicMock()

            rt = create_agent_runtime(
                agent_config=agent_cfg,
                parent_config=parent_cfg,
                project_ctx=project_ctx,
                process_manager=pm,
                permissions={"r"},
            )

        mock_load.assert_called_once_with("anthropic")

    def test_agent_model_override(self):
        """When agent specifies model, it overrides the resolved config's model."""
        agent_cfg = AgentConfig(
            name="test", model="custom-model", system_prompt="test"
        )
        parent_cfg = Config()
        project_ctx = ProjectContext(".")
        pm = MagicMock()

        mock_registry = MagicMock()
        mock_registry.get_system_prompts.return_value = ""

        with patch("ayder_cli.application.runtime_factory.provider_orchestrator") as mock_orch, \
             patch("ayder_cli.application.runtime_factory.create_default_registry", return_value=mock_registry):
            mock_orch.create.return_value = MagicMock()

            rt = create_agent_runtime(
                agent_config=agent_cfg,
                parent_config=parent_cfg,
                project_ctx=project_ctx,
                process_manager=pm,
                permissions={"r"},
            )

        assert rt.config.model == "custom-model"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_runtime_factory.py::TestCreateAgentRuntime -v`
Expected: FAIL — `ImportError: cannot import name 'create_agent_runtime'`

- [ ] **Step 3: Implement create_agent_runtime**

Add to `src/ayder_cli/application/runtime_factory.py` (after `create_runtime` function):

```python
def create_agent_runtime(
    *,
    agent_config: "AgentConfig",
    parent_config: Config,
    project_ctx: "ProjectContext",
    process_manager: "ProcessManager",
    permissions: set[str],
) -> RuntimeComponents:
    """Assemble runtime components for a single agent run.

    Does NOT call create_runtime() — assembles components directly.
    Shares ProcessManager and ProjectContext with parent; isolates
    AIProvider, ToolRegistry, and ContextManager.

    Args:
        agent_config: Agent-specific configuration.
        parent_config: Parent's Config for inheriting provider/model defaults.
        project_ctx: Shared project context (same project for all agents).
        process_manager: Shared process manager (global process limit).
        permissions: Global permission set from ExecutionPolicy.

    Returns:
        RuntimeComponents with agent-specific wiring.
    """
    from ayder_cli.agents.config import AgentConfig  # noqa: F811

    # 1. Resolve provider config
    if agent_config.provider:
        cfg = load_config_for_provider(agent_config.provider)
    else:
        cfg = parent_config

    # 2. Apply model override
    if agent_config.model:
        cfg = cfg.model_copy(update={"model": agent_config.model})

    # 3. Create isolated AIProvider
    llm_provider = provider_orchestrator.create(cfg)

    # 4. Create isolated ToolRegistry (shared PM and ProjectContext)
    tool_registry = create_default_registry(project_ctx, process_manager=process_manager)

    # 5. Build agent system prompt
    summary_suffix = (
        "\n\n---\nWhen you have completed your task, end your final response with "
        "a structured summary block:\n"
        "<agent-summary>\n"
        "FINDINGS: [what you found or accomplished]\n"
        "FILES_CHANGED: [list of files modified, or 'none']\n"
        "RECOMMENDATIONS: [any follow-up actions]\n"
        "</agent-summary>"
    )
    tool_tags = frozenset(cfg.tool_tags) if getattr(cfg, "tool_tags", None) else None
    tool_prompts = tool_registry.get_system_prompts(tags=tool_tags)
    system_prompt = agent_config.system_prompt + tool_prompts + summary_suffix

    return RuntimeComponents(
        config=cfg,
        llm_provider=llm_provider,
        process_manager=process_manager,
        project_ctx=project_ctx,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
    )
```

Update the existing import on line 11 of `runtime_factory.py` to include `load_config_for_provider`:

```python
from ayder_cli.core.config import Config, load_config, load_config_for_provider
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_runtime_factory.py -v`
Expected: PASS (all tests including new ones)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/application/runtime_factory.py tests/test_runtime_factory.py
git commit -m "feat(agents): add create_agent_runtime() factory for isolated agent runtimes"
```

---

## Task 5: AgentRunner

**Files:**
- Create: `src/ayder_cli/agents/runner.py`
- Modify: `src/ayder_cli/agents/__init__.py`
- Test: `tests/agents/test_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/test_runner.py
"""Tests for AgentRunner — wraps one ChatLoop execution per agent dispatch."""

import asyncio
import re
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.agents.summary import AgentSummary


class TestAgentRunner:
    def _make_runner(self, **overrides):
        agent_cfg = AgentConfig(name="test-agent", system_prompt="You are a test.")
        parent_cfg = MagicMock()
        parent_cfg.model_copy.return_value = parent_cfg
        parent_cfg.model = "test-model"
        parent_cfg.num_ctx = 4096
        parent_cfg.max_output_tokens = 2048
        parent_cfg.stop_sequences = []
        parent_cfg.tool_tags = ["core"]
        parent_cfg.provider = "openai"
        parent_cfg.max_history_messages = 30

        defaults = dict(
            agent_config=agent_cfg,
            parent_config=parent_cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r", "w"},
            timeout=10,
        )
        defaults.update(overrides)
        return AgentRunner(**defaults)

    def test_init(self):
        runner = self._make_runner()
        assert runner.agent_name == "test-agent"
        assert runner.status == "idle"

    def test_parse_summary_block(self):
        """Extracts <agent-summary> from content."""
        content = (
            "I reviewed the code.\n"
            "<agent-summary>\n"
            "FINDINGS: Found 2 bugs\n"
            "FILES_CHANGED: none\n"
            "RECOMMENDATIONS: Fix bug in auth.py\n"
            "</agent-summary>"
        )
        runner = self._make_runner()
        summary = runner._parse_summary(content)
        assert "Found 2 bugs" in summary

    def test_parse_summary_fallback(self):
        """Falls back to full content when no <agent-summary> block."""
        content = "I finished reviewing the code. All looks good."
        runner = self._make_runner()
        summary = runner._parse_summary(content)
        assert summary == content

    def test_cancel(self):
        runner = self._make_runner()
        assert runner.cancel() is True
        assert runner.status == "cancelled"

    @pytest.mark.asyncio
    async def test_run_returns_summary(self):
        """AgentRunner.run() returns an AgentSummary."""
        runner = self._make_runner()

        # Mock create_agent_runtime
        mock_rt = MagicMock()
        mock_rt.config = runner._parent_config
        mock_rt.llm_provider = MagicMock()
        mock_rt.tool_registry = MagicMock()
        mock_rt.system_prompt = "test prompt"

        with patch("ayder_cli.agents.runner.create_agent_runtime", return_value=mock_rt), \
             patch("ayder_cli.agents.runner.ChatLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run = AsyncMock()

            result = await runner.run("Review this code")

        assert isinstance(result, AgentSummary)
        assert result.agent_name == "test-agent"

    @pytest.mark.asyncio
    async def test_run_timeout(self):
        """AgentRunner.run() produces timeout summary when exceeding timeout."""
        runner = self._make_runner(timeout=0.01)  # 10ms timeout

        mock_rt = MagicMock()
        mock_rt.config = runner._parent_config
        mock_rt.llm_provider = MagicMock()
        mock_rt.tool_registry = MagicMock()
        mock_rt.system_prompt = "test"

        async def slow_run(**kwargs):
            await asyncio.sleep(5)

        with patch("ayder_cli.agents.runner.create_agent_runtime", return_value=mock_rt), \
             patch("ayder_cli.agents.runner.ChatLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run = slow_run

            result = await runner.run("Do something")

        assert result.status == "timeout"
        assert result.agent_name == "test-agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ayder_cli.agents.runner'`

- [ ] **Step 3: Implement AgentRunner**

```python
# src/ayder_cli/agents/runner.py
"""AgentRunner — wraps one ChatLoop execution per agent dispatch.

Disposable: one instance per dispatch. Creates an isolated runtime,
runs a ChatLoop, and produces an AgentSummary.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

from ayder_cli.agents.callbacks import AgentCallbacks
from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.summary import AgentSummary
from ayder_cli.application.runtime_factory import create_agent_runtime
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

logger = logging.getLogger(__name__)

_SUMMARY_PATTERN = re.compile(
    r"<agent-summary>\s*(.*?)\s*</agent-summary>", re.DOTALL
)


class AgentRunner:
    """Executes a single agent task via ChatLoop."""

    def __init__(
        self,
        agent_config: AgentConfig,
        parent_config: Any,
        project_ctx: Any,
        process_manager: Any,
        permissions: set[str],
        timeout: int = 300,
        on_progress: Callable[[str, str, Any], None] | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._parent_config = parent_config
        self._project_ctx = project_ctx
        self._process_manager = process_manager
        self._permissions = permissions
        self._timeout = timeout
        self._on_progress = on_progress
        self._cancel_event = asyncio.Event()
        self.status: str = "idle"

    @property
    def agent_name(self) -> str:
        return self._agent_config.name

    def cancel(self) -> bool:
        """Cancel the running agent."""
        self._cancel_event.set()
        self.status = "cancelled"
        return True

    def _parse_summary(self, content: str) -> str:
        """Extract <agent-summary> block or fall back to full content."""
        match = _SUMMARY_PATTERN.search(content)
        if match:
            return match.group(1).strip()
        return content

    async def run(self, task: str) -> AgentSummary:
        """Execute the agent task and return a summary."""
        self.status = "running"

        try:
            rt = create_agent_runtime(
                agent_config=self._agent_config,
                parent_config=self._parent_config,
                project_ctx=self._project_ctx,
                process_manager=self._process_manager,
                permissions=self._permissions,
            )

            callbacks = AgentCallbacks(
                agent_name=self.agent_name,
                cancel_event=self._cancel_event,
                on_progress=self._on_progress,
            )

            messages = [
                {"role": "system", "content": rt.system_prompt},
                {"role": "user", "content": task},
            ]

            loop_config = ChatLoopConfig(
                model=rt.config.model,
                provider=rt.config.provider,
                num_ctx=rt.config.num_ctx,
                max_output_tokens=rt.config.max_output_tokens,
                stop_sequences=list(rt.config.stop_sequences) if rt.config.stop_sequences else [],
                permissions=self._permissions,
                tool_tags=frozenset(rt.config.tool_tags) if getattr(rt.config, "tool_tags", None) else None,
                max_history=getattr(rt.config, "max_history_messages", 30),
            )

            chat_loop = ChatLoop(
                llm=rt.llm_provider,
                registry=rt.tool_registry,
                messages=messages,
                config=loop_config,
                callbacks=callbacks,
            )

            try:
                await asyncio.wait_for(
                    chat_loop.run(),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                self._cancel_event.set()
                self.status = "timeout"
                summary_text = self._parse_summary(callbacks.last_content)
                return AgentSummary(
                    agent_name=self.agent_name,
                    status="timeout",
                    summary=summary_text or "Agent timed out before producing output.",
                    error=f"Agent exceeded {self._timeout}s timeout",
                )

            # Completed successfully
            self.status = "completed"
            summary_text = self._parse_summary(callbacks.last_content)
            return AgentSummary(
                agent_name=self.agent_name,
                status="completed",
                summary=summary_text or "Agent completed without producing a summary.",
                error=None,
            )

        except Exception as e:
            self.status = "error"
            logger.exception(f"Agent '{self.agent_name}' failed: {e}")
            return AgentSummary(
                agent_name=self.agent_name,
                status="error",
                summary="Agent encountered an error.",
                error=str(e),
            )
```

Update `src/ayder_cli/agents/__init__.py`:

```python
"""Multi-agent system: config, registry, runner, and tool."""

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.summary import AgentSummary
from ayder_cli.agents.runner import AgentRunner

__all__ = ["AgentConfig", "AgentSummary", "AgentRunner"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_runner.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ --timeout=10 -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/agents/runner.py src/ayder_cli/agents/__init__.py tests/agents/test_runner.py
git commit -m "feat(agents): add AgentRunner with timeout, cancellation, and summary parsing"
```

---

## Task 6: AgentRegistry

**Files:**
- Create: `src/ayder_cli/agents/registry.py`
- Modify: `src/ayder_cli/agents/__init__.py`
- Test: `tests/agents/test_registry.py`

**Architecture note:** `dispatch()` is a **sync method** that uses `asyncio.run_coroutine_threadsafe()` to schedule agent runs on the event loop. This is critical because:
- The `call_agent` tool handler runs inside `asyncio.to_thread()` (background thread), so it cannot use `await` or `asyncio.create_task()`
- The `/agent` command handler also runs synchronously (Textual's `_handle_command` calls handlers without `await`)
- `run_coroutine_threadsafe()` works from any thread — both the event loop thread and background threads

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/test_registry.py
"""Tests for AgentRegistry — lifecycle management for agents."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.summary import AgentSummary


@pytest.fixture
def agent_configs():
    return {
        "reviewer": AgentConfig(name="reviewer", system_prompt="You review code."),
        "writer": AgentConfig(name="writer", system_prompt="You write tests."),
    }


@pytest.fixture
def registry(agent_configs):
    return AgentRegistry(
        agents=agent_configs,
        parent_config=MagicMock(),
        project_ctx=MagicMock(),
        process_manager=MagicMock(),
        permissions={"r", "w"},
        agent_timeout=300,
    )


class TestAgentRegistry:
    def test_init(self, registry, agent_configs):
        assert len(registry.agents) == 2
        assert "reviewer" in registry.agents

    def test_get_status_idle(self, registry):
        assert registry.get_status("reviewer") == "idle"

    def test_get_status_unknown(self, registry):
        assert registry.get_status("nonexistent") is None

    def test_get_capability_prompts(self, registry):
        prompts = registry.get_capability_prompts()
        assert "reviewer" in prompts
        assert "writer" in prompts
        assert "call_agent" in prompts

    def test_get_capability_prompts_empty(self):
        reg = AgentRegistry(
            agents={},
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        assert reg.get_capability_prompts() == ""

    def test_get_capability_prompts_truncation(self):
        """System prompts longer than 100 chars are truncated."""
        agents = {
            "verbose": AgentConfig(
                name="verbose",
                system_prompt="A" * 200,
            ),
        }
        reg = AgentRegistry(
            agents=agents,
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        prompts = reg.get_capability_prompts()
        # Each agent description line should be truncated
        for line in prompts.splitlines():
            if line.startswith("- verbose:"):
                assert len(line) < 120  # name + truncated prompt

    def test_dispatch_unknown_agent(self, registry):
        """Dispatching unknown agent returns error string."""
        result = registry.dispatch("nonexistent", "do something")
        assert "not found" in result.lower()

    def test_dispatch_returns_status_string(self, registry):
        """dispatch() returns immediately with a status string."""
        # Set a mock loop so dispatch doesn't fail
        mock_loop = MagicMock()
        registry.set_loop(mock_loop)

        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner, \
             patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe") as mock_rcts:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"

            result = registry.dispatch("reviewer", "Review this")

        assert isinstance(result, str)
        assert "dispatched" in result.lower() or "reviewer" in result.lower()
        mock_rcts.assert_called_once()

    def test_dispatch_rejects_duplicate(self, registry):
        """Cannot dispatch same agent while it's already running."""
        registry._active["reviewer"] = MagicMock()
        result = registry.dispatch("reviewer", "another task")
        assert "already running" in result.lower()

    def test_cancel(self, registry):
        """cancel() delegates to the active AgentRunner."""
        mock_runner = MagicMock()
        mock_runner.cancel.return_value = True
        registry._active["reviewer"] = mock_runner

        assert registry.cancel("reviewer") is True
        mock_runner.cancel.assert_called_once()

    def test_cancel_not_running(self, registry):
        assert registry.cancel("reviewer") is False

    def test_drain_summaries_empty(self, registry):
        """drain_summaries returns empty list when no summaries."""
        assert registry.drain_summaries() == []

    @pytest.mark.asyncio
    async def test_drain_summaries_after_completion(self, registry):
        """drain_summaries returns summaries that were queued."""
        summary = AgentSummary(
            agent_name="reviewer", status="completed", summary="Done.", error=None
        )
        await registry._summary_queue.put(summary)
        result = registry.drain_summaries()
        assert len(result) == 1
        assert result[0].agent_name == "reviewer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ayder_cli.agents.registry'`

- [ ] **Step 3: Implement AgentRegistry**

```python
# src/ayder_cli/agents/registry.py
"""AgentRegistry — lifecycle management for agents.

All dispatches are non-blocking (Approach A). dispatch() is a sync method
that schedules agent runs on the event loop via run_coroutine_threadsafe.
Summaries are delivered via _summary_queue, drained by pre_iteration_hook.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.agents.summary import AgentSummary

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Manages agent lifecycle: dispatch, cancel, status, capability prompts.

    dispatch() is sync and thread-safe — works from both the event loop
    thread and from asyncio.to_thread() background threads (tool pipeline).
    """

    def __init__(
        self,
        agents: dict[str, AgentConfig],
        parent_config: Any,
        project_ctx: Any,
        process_manager: Any,
        permissions: set[str],
        agent_timeout: int = 300,
        on_progress: Callable[[str, str, Any], None] | None = None,
    ) -> None:
        self.agents = agents
        self._parent_config = parent_config
        self._project_ctx = project_ctx
        self._process_manager = process_manager
        self._permissions = permissions
        self._agent_timeout = agent_timeout
        self._on_progress = on_progress
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active: dict[str, AgentRunner] = {}
        self._summary_queue: asyncio.Queue[AgentSummary] = asyncio.Queue()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for scheduling agent runs.

        Must be called after the event loop is running (e.g., in on_mount).
        """
        self._loop = loop

    def get_status(self, name: str) -> str | None:
        """Get agent status: 'idle', 'running', 'completed', 'error', or None if unknown."""
        if name not in self.agents:
            return None
        runner = self._active.get(name)
        if runner is None:
            return "idle"
        return runner.status

    def get_capability_prompts(self) -> str:
        """Generate capability prompt text for the main LLM's system prompt."""
        if not self.agents:
            return ""

        lines = [
            "\n## Available Agents",
            "You can delegate tasks to specialized agents using the call_agent tool.",
            "Each agent runs independently with its own context and may use a different LLM.",
            "",
        ]
        for name, cfg in self.agents.items():
            desc = cfg.system_prompt[:100] if cfg.system_prompt else "(no description)"
            lines.append(f"- {name}: {desc}")

        return "\n".join(lines)

    def dispatch(self, name: str, task: str) -> str:
        """Fire-and-forget agent dispatch. Thread-safe. Returns status message.

        Schedules the agent run on the event loop via run_coroutine_threadsafe.
        Both call_agent tool handler and /agent command use this same method.
        """
        if name not in self.agents:
            return f"Error: Agent '{name}' not found in configured agents"
        if name in self._active:
            return f"Error: Agent '{name}' is already running"

        runner = AgentRunner(
            agent_config=self.agents[name],
            parent_config=self._parent_config,
            project_ctx=self._project_ctx,
            process_manager=self._process_manager,
            permissions=self._permissions,
            timeout=self._agent_timeout,
            on_progress=self._on_progress,
        )
        self._active[name] = runner

        async def _run_and_queue():
            try:
                summary = await runner.run(task)
                await self._summary_queue.put(summary)
            finally:
                self._active.pop(name, None)

        # Schedule on event loop (thread-safe)
        if self._loop is None:
            self._active.pop(name, None)
            return "Error: Agent registry not initialized (event loop not set)"
        asyncio.run_coroutine_threadsafe(_run_and_queue(), self._loop)

        task_preview = task[:80] + "..." if len(task) > 80 else task
        return (
            f"Agent '{name}' dispatched with task: {task_preview}\n"
            f"The agent is running in the background. "
            f"You will receive its summary when it completes."
        )

    def cancel(self, name: str) -> bool:
        """Cancel a running agent. Returns True if cancelled, False if not running."""
        runner = self._active.get(name)
        if runner is None:
            return False
        return runner.cancel()

    def drain_summaries(self) -> list[AgentSummary]:
        """Drain all completed summaries from the queue (non-blocking)."""
        summaries = []
        while not self._summary_queue.empty():
            try:
                summaries.append(self._summary_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return summaries
```

Update `src/ayder_cli/agents/__init__.py`:

```python
"""Multi-agent system: config, registry, runner, and tool."""

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.summary import AgentSummary
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.agents.registry import AgentRegistry

__all__ = ["AgentConfig", "AgentSummary", "AgentRunner", "AgentRegistry"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_registry.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/registry.py src/ayder_cli/agents/__init__.py tests/agents/test_registry.py
git commit -m "feat(agents): add AgentRegistry with dispatch, cancel, and capability prompts"
```

---

## Task 7: call_agent Tool

**Files:**
- Create: `src/ayder_cli/agents/tool.py`
- Test: `tests/agents/test_tool.py`

**Architecture note:** The handler is a **sync function** because it runs inside `asyncio.to_thread()` in the tool execution pipeline (`ChatLoop._exec_tool_async` → `execute_tool` → `tool_func(**call_args)`). It calls `registry.dispatch()` which is also sync (fire-and-forget via `run_coroutine_threadsafe`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/test_tool.py
"""Tests for the call_agent tool definition and handler."""

from unittest.mock import MagicMock

from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION, create_call_agent_handler
from ayder_cli.tools.definition import ToolDefinition


class TestAgentToolDefinition:
    def test_definition_is_tool_definition(self):
        assert isinstance(AGENT_TOOL_DEFINITION, ToolDefinition)

    def test_definition_name(self):
        assert AGENT_TOOL_DEFINITION.name == "call_agent"

    def test_definition_parameters(self):
        params = AGENT_TOOL_DEFINITION.parameters
        assert "name" in params["properties"]
        assert "task" in params["properties"]
        assert params["required"] == ["name", "task"]

    def test_definition_permission(self):
        assert AGENT_TOOL_DEFINITION.permission == "r"

    def test_definition_tags(self):
        assert "agents" in AGENT_TOOL_DEFINITION.tags


class TestCallAgentHandler:
    def test_handler_calls_dispatch(self):
        """Handler calls registry.dispatch() synchronously."""
        mock_registry = MagicMock()
        mock_registry.dispatch.return_value = (
            "Agent 'reviewer' dispatched with task: Review auth.py\n"
            "The agent is running in the background. "
            "You will receive its summary when it completes."
        )

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="reviewer", task="Review auth.py")

        mock_registry.dispatch.assert_called_once_with("reviewer", "Review auth.py")
        assert "dispatched" in result.lower()

    def test_handler_returns_error_for_unknown_agent(self):
        mock_registry = MagicMock()
        mock_registry.dispatch.return_value = "Error: Agent 'unknown' not found"

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="unknown", task="do something")

        assert "not found" in result.lower() or "error" in result.lower()

    def test_handler_returns_dispatch_result_directly(self):
        """Handler returns whatever registry.dispatch() returns."""
        mock_registry = MagicMock()
        mock_registry.dispatch.return_value = "Agent 'writer' dispatched with task: Write tests..."

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="writer", task="Write tests for auth.py")

        assert result == "Agent 'writer' dispatched with task: Write tests..."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agents/test_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ayder_cli.agents.tool'`

- [ ] **Step 3: Implement call_agent tool**

```python
# src/ayder_cli/agents/tool.py
"""call_agent tool — delegates tasks to specialized agents.

Provides the ToolDefinition for registration and a factory for the
sync handler. The handler is sync because it runs inside asyncio.to_thread()
in the tool execution pipeline. It calls registry.dispatch() which
schedules the agent via run_coroutine_threadsafe and returns immediately.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from ayder_cli.tools.definition import ToolDefinition

if TYPE_CHECKING:
    from ayder_cli.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)

AGENT_TOOL_DEFINITION = ToolDefinition(
    name="call_agent",
    description=(
        "Delegate a task to a specialized agent. The agent runs in the background "
        "with its own context and tools. You will receive its summary when it completes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent name from config (e.g., 'code-reviewer', 'test-writer')",
            },
            "task": {
                "type": "string",
                "description": "Task description for the agent to execute",
            },
        },
        "required": ["name", "task"],
    },
    permission="r",
    tags=("core", "agents"),
    system_prompt="",
)


def create_call_agent_handler(registry: AgentRegistry) -> Callable[..., str]:
    """Create a sync handler for the call_agent tool.

    The handler calls registry.dispatch() which is sync and thread-safe.
    It schedules the agent run in the background and returns immediately.
    """

    def handle_call_agent(*, name: str, task: str) -> str:
        return registry.dispatch(name, task)

    return handle_call_agent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/agents/test_tool.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/agents/tool.py tests/agents/test_tool.py
git commit -m "feat(agents): add call_agent tool definition and handler"
```

---

## Task 8: ChatLoop Pre-Iteration Hook

**Files:**
- Modify: `src/ayder_cli/loops/chat_loop.py:33-46` (ChatLoopConfig) and `src/ayder_cli/loops/chat_loop.py:99-103` (ChatLoop.run)
- Test: `tests/loops/test_chat_loop_hook.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/loops/test_chat_loop_hook.py
"""Tests for ChatLoop pre-iteration hook."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig


class FakeProvider:
    async def stream_with_tools(self, *a, **k):
        # Yield one text-only chunk then stop
        from ayder_cli.providers import NormalizedStreamChunk
        chunk = NormalizedStreamChunk()
        chunk.content = "Hello"
        chunk.done = True
        yield chunk


class FakeCallbacks:
    def __init__(self):
        self.cancelled = False
        self.call_count = 0

    def on_thinking_start(self): pass
    def on_thinking_stop(self): pass
    def on_assistant_content(self, text): pass
    def on_thinking_content(self, text): pass
    def on_token_usage(self, total_tokens): pass
    def on_tool_start(self, call_id, name, arguments): pass
    def on_tool_complete(self, call_id, result): pass
    def on_tools_cleanup(self): pass
    def on_system_message(self, text): pass
    async def request_confirmation(self, name, arguments): return None
    def is_cancelled(self):
        self.call_count += 1
        # Cancel after first iteration to prevent infinite loop
        if self.call_count > 1:
            return True
        return self.cancelled


class TestPreIterationHook:
    @pytest.mark.asyncio
    async def test_hook_called_before_llm(self):
        """pre_iteration_hook is called at the top of each iteration."""
        hook_called = []

        async def my_hook(messages):
            hook_called.append(len(messages))

        config = ChatLoopConfig()
        config.pre_iteration_hook = my_hook

        loop = ChatLoop(
            llm=FakeProvider(),
            registry=MagicMock(get_schemas=MagicMock(return_value=[])),
            messages=[{"role": "system", "content": "test"}],
            config=config,
            callbacks=FakeCallbacks(),
        )

        await loop.run()
        assert len(hook_called) >= 1

    @pytest.mark.asyncio
    async def test_no_hook_no_error(self):
        """ChatLoop works fine without a pre_iteration_hook."""
        config = ChatLoopConfig()

        loop = ChatLoop(
            llm=FakeProvider(),
            registry=MagicMock(get_schemas=MagicMock(return_value=[])),
            messages=[{"role": "system", "content": "test"}],
            config=config,
            callbacks=FakeCallbacks(),
        )

        # Should not raise
        await loop.run()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/loops/test_chat_loop_hook.py -v`
Expected: FAIL — `ChatLoopConfig` has no `pre_iteration_hook` attribute

- [ ] **Step 3: Add pre_iteration_hook to ChatLoopConfig and ChatLoop.run()**

In `src/ayder_cli/loops/chat_loop.py`, modify `ChatLoopConfig` (around line 33):

Add field after `verbose`:
```python
    pre_iteration_hook: Any | None = None  # async callable(messages) -> None
```

In `ChatLoop.run()` (around line 99-103), add hook call after the `is_cancelled` check:

```python
    async def run(self, *, no_tools: bool = False) -> None:
        """Main loop: call LLM, handle tools, repeat until text-only or cancel."""
        while True:
            if self.cb.is_cancelled():
                return

            # Pre-iteration hook (used for agent summary injection)
            if self.config.pre_iteration_hook is not None:
                await self.config.pre_iteration_hook(self.messages)

            # 1. Prepare schemas and messages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/loops/test_chat_loop_hook.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ --timeout=10 -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/loops/chat_loop.py tests/loops/test_chat_loop_hook.py
git commit -m "feat(agents): add pre_iteration_hook to ChatLoop for agent summary injection"
```

---

## Task 9: AgentPanel Widget

**Files:**
- Modify: `src/ayder_cli/tui/widgets.py` (add AgentPanel class)
- No separate test file — widget testing is done via TUI integration

- [ ] **Step 1: Add AgentPanel to widgets.py**

Add at the end of `src/ayder_cli/tui/widgets.py`, after the existing widget classes:

```python
class AgentPanel(Container):
    """Panel for displaying active and completed agent runs.

    Shows agent name, status, elapsed time, and summary.
    Placed below ToolPanel in the layout. Hidden when no agents active.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._agents: dict[str, Static] = {}

    def compose(self) -> ComposeResult:
        return
        yield

    def on_mount(self) -> None:
        self.display = False

    def update_agent(self, name: str, event: str, data: Any = None) -> None:
        """Handle an agent progress event."""
        if event == "tool_start" and isinstance(data, dict):
            tool_name = data.get("name", "?")
            self._update_widget(name, f"Running tool: {tool_name}")
        elif event == "assistant_content":
            pass  # Don't update on every content chunk
        elif event == "thinking_start":
            self._update_widget(name, "Thinking...")
        elif event == "tools_cleanup":
            self._update_widget(name, "Processing...")

    def add_agent(self, name: str) -> None:
        """Show a new agent as running."""
        text = Text()
        text.append(f"  Agent ", style="dim")
        text.append(f"{name}", style="bold magenta")
        text.append(f" running...", style="dim")

        widget = Static(text, classes="agent-item running")
        self._agents[name] = widget
        self.mount(widget)
        self.display = True

    def complete_agent(self, name: str, summary: str, status: str = "completed") -> None:
        """Mark agent as completed with summary."""
        if name in self._agents:
            widget = self._agents[name]
            text = Text()
            if status == "completed":
                text.append("  ✓ ", style="bold green")
            elif status == "timeout":
                text.append("  ⏱ ", style="bold yellow")
            else:
                text.append("  ✗ ", style="bold red")
            text.append(f"{name}", style="bold")
            preview = summary[:80] + "..." if len(summary) > 80 else summary
            text.append(f" — {preview}", style="dim")
            widget.update(text)
            widget.remove_class("running")

    def remove_agent(self, name: str) -> None:
        """Remove agent widget."""
        if name in self._agents:
            self._agents[name].remove()
            del self._agents[name]
        if not self._agents:
            self.display = False

    def _update_widget(self, name: str, status_text: str) -> None:
        if name not in self._agents:
            self.add_agent(name)
        widget = self._agents[name]
        text = Text()
        text.append(f"  Agent ", style="dim")
        text.append(f"{name}", style="bold magenta")
        text.append(f" — {status_text}", style="dim")
        widget.update(text)
```

Add `from typing import Any` to the imports at the top of `widgets.py` (it is not currently imported in this file).

- [ ] **Step 2: Update widgets __all__ or imports**

Add `AgentPanel` to the import in `src/ayder_cli/tui/widgets.py`'s module exports (if `__all__` exists) or confirm it's importable.

- [ ] **Step 3: Verify widget is importable**

Run: `uv run python -c "from ayder_cli.tui.widgets import AgentPanel; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/ayder_cli/tui/widgets.py
git commit -m "feat(agents): add AgentPanel widget for TUI agent status display"
```

---

## Task 10: /agent Command Handler

**Files:**
- Modify: `src/ayder_cli/tui/commands.py` (add handle_agent + COMMAND_MAP entry)

- [ ] **Step 1: Add /agent handler to commands.py**

**Note:** The handler must be **sync** because `_handle_command()` at line 546 of `app.py` calls handlers without `await`. The `registry.dispatch()` method is also sync (fire-and-forget).

Add the handler function before `COMMAND_MAP` (around line 925):

```python
def handle_agent(app: "AyderApp", args: str, chat_view: "ChatView") -> None:
    """Handle /agent command: dispatch, list, or cancel agents."""
    parts = args.strip().split(None, 1)
    if not parts:
        chat_view.add_system_message(
            "Usage: /agent <name> <task> | /agent list | /agent cancel <name>"
        )
        return

    subcommand = parts[0]

    if not hasattr(app, "_agent_registry") or app._agent_registry is None:
        chat_view.add_system_message("No agents configured. Add [agents.*] sections to config.toml.")
        return

    if subcommand == "list":
        agents = app._agent_registry.agents
        if not agents:
            chat_view.add_system_message("No agents configured.")
            return
        lines = ["Configured agents:"]
        for name in agents:
            status = app._agent_registry.get_status(name)
            lines.append(f"  {name}: {status}")
        chat_view.add_system_message("\n".join(lines))
        return

    if subcommand == "cancel":
        cancel_name = parts[1].strip() if len(parts) > 1 else ""
        if not cancel_name:
            chat_view.add_system_message("Usage: /agent cancel <name>")
            return
        if app._agent_registry.cancel(cancel_name):
            chat_view.add_system_message(f"Cancelling agent '{cancel_name}'...")
        else:
            chat_view.add_system_message(f"Agent '{cancel_name}' is not running.")
        return

    # /agent <name> <task>
    agent_name = subcommand
    task = parts[1] if len(parts) > 1 else ""
    if not task:
        chat_view.add_system_message(f"Usage: /agent {agent_name} <task description>")
        return

    if agent_name not in app._agent_registry.agents:
        chat_view.add_system_message(f"Unknown agent: '{agent_name}'")
        return

    # Show agent in panel and dispatch (sync, fire-and-forget)
    try:
        agent_panel = app.query_one("#agent-panel", AgentPanel)
        agent_panel.add_agent(agent_name)
    except Exception:
        pass

    result = app._agent_registry.dispatch(agent_name, task)
    chat_view.add_system_message(result)
```

Add `AgentPanel` to the imports at the top of `commands.py` (add to existing widgets import):
```python
from ayder_cli.tui.widgets import AgentPanel
```

Add `/agent` to `COMMAND_MAP`:
```python
    "/agent": handle_agent,
```

- [ ] **Step 2: Verify /agent is importable**

Run: `uv run python -c "from ayder_cli.tui.commands import COMMAND_MAP; assert '/agent' in COMMAND_MAP; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ayder_cli/tui/commands.py
git commit -m "feat(agents): add /agent command handler (dispatch, list, cancel)"
```

---

## Task 11: Wire Everything in AyderApp

**Files:**
- Modify: `src/ayder_cli/tui/app.py:19-248` (imports, __init__, compose)

- [ ] **Step 1: Add AgentRegistry initialization to AyderApp.__init__**

In `src/ayder_cli/tui/app.py`, add imports at the top:

```python
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION, create_call_agent_handler
from ayder_cli.tui.widgets import AgentPanel
```

**Initialization is split into two parts** because `self.chat_loop` is created at line 233-248, but we need to set `pre_iteration_hook` on it, which requires the registry to exist first.

**Part 1:** In `AyderApp.__init__`, after `self._init_system_prompt()` (around line 199), add the registry setup. **Do NOT pass `loop=` here** — the event loop is not running yet during `__init__`:

```python
        # Initialize agent registry if agents are configured
        self._agent_registry = None
        if hasattr(self.config, 'agents') and self.config.agents:
            def _agent_progress(name, event, data):
                """Forward agent events to AgentPanel."""
                try:
                    panel = self.query_one("#agent-panel", AgentPanel)
                    self.call_later(lambda: panel.update_agent(name, event, data))
                except Exception:
                    pass

            self._agent_registry = AgentRegistry(
                agents=self.config.agents,
                parent_config=self.config,
                project_ctx=rt.project_ctx,
                process_manager=self._process_manager,
                permissions=self.permissions,
                agent_timeout=getattr(self.config, 'agent_timeout', 300),
                on_progress=_agent_progress,
            )

            # Register call_agent tool
            handler = create_call_agent_handler(self._agent_registry)
            self.registry.register_dynamic_tool(AGENT_TOOL_DEFINITION, handler)

            # Append capability prompts to system prompt
            cap_prompts = self._agent_registry.get_capability_prompts()
            if cap_prompts and self.messages and self.messages[0].get("role") == "system":
                self.messages[0]["content"] += cap_prompts
```

**Part 2:** AFTER `self.chat_loop` is created (after line 248), wire the pre-iteration hook:

```python
        # Wire pre-iteration hook for async agent summary injection
        # (Must be after self.chat_loop is created above)
        if self._agent_registry:
            async def _inject_summaries(messages):
                summaries = self._agent_registry.drain_summaries()
                for s in summaries:
                    messages.append({"role": "system", "content": s.format_for_injection()})
                    chat_view = self.query_one("#chat-view", ChatView)
                    self.call_later(
                        lambda ss=s: chat_view.add_system_message(
                            f"Agent '{ss.agent_name}' {ss.status}: {ss.summary[:100]}"
                        )
                    )
                    try:
                        panel = self.query_one("#agent-panel", AgentPanel)
                        self.call_later(
                            lambda ss=s: panel.complete_agent(ss.agent_name, ss.summary, ss.status)
                        )
                    except Exception:
                        pass

            self.chat_loop.config.pre_iteration_hook = _inject_summaries
```

**Part 3:** In the existing `on_mount()` method (around line 455), add the event loop capture. This is where Textual's event loop is guaranteed to be running:

```python
    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.title = f"ayder - {self.model}"

        # Set the event loop on the agent registry now that it's running
        if self._agent_registry:
            import asyncio
            self._agent_registry.set_loop(asyncio.get_running_loop())

        # ... rest of existing on_mount code (banner, etc.) ...
```

- [ ] **Step 2: Add AgentPanel to compose()**

Modify `AyderApp.compose()` to include AgentPanel:

```python
    def compose(self) -> ComposeResult:
        """Compose the UI layout - terminal style with scrolling content."""
        yield ChatView(id="chat-view")
        yield ToolPanel(id="tool-panel")
        yield AgentPanel(id="agent-panel")
        yield ActivityBar(id="activity-bar")
        yield CLIInputBar(commands=self.commands, id="input-bar")
        yield StatusBar(model=self.model, permissions=self.permissions, id="status-bar")
```

- [ ] **Step 3: Add register_dynamic_tool to ToolRegistry**

`ToolRegistry` does not have this method. It must be added to `src/ayder_cli/tools/registry.py`.

**Key insight:** `get_schemas()` and `get_system_prompts()` read from the module-level `TOOL_DEFINITIONS` tuple — not from any instance attribute. `execute()` looks up handlers from `self._registry` dict. So `register_dynamic_tool` must:
1. Store the `ToolDefinition` in a per-instance `_dynamic_definitions` list
2. Register the handler in `self._registry`
3. Modify `get_schemas()` and `get_system_prompts()` to include `_dynamic_definitions`

Add `_dynamic_definitions` to `__init__` (after line 33):

```python
        self._dynamic_definitions: list = []
```

Add `register_dynamic_tool` method (after `register`):

```python
    def register_dynamic_tool(self, tool_def, handler: Callable) -> None:
        """Register a tool dynamically at runtime (e.g., call_agent).

        Adds the ToolDefinition to a per-instance list (included in schema
        queries) and the handler to _registry (for execution dispatch).
        """
        self._dynamic_definitions.append(tool_def)
        self._registry[tool_def.name] = handler
```

Update `get_schemas` (line 38-41) to include dynamic definitions:

```python
    def get_schemas(self, tags: frozenset | None = None) -> List[Dict[str, Any]]:
        all_defs = list(TOOL_DEFINITIONS) + self._dynamic_definitions
        if tags is None:
            return [td.to_openai_schema() for td in all_defs]
        return [td.to_openai_schema() for td in all_defs if set(td.tags) & tags]
```

Update `get_system_prompts` (line 54-57) to include dynamic definitions:

```python
    def get_system_prompts(self, tags: frozenset | None = None) -> str:
        all_defs = list(TOOL_DEFINITIONS) + self._dynamic_definitions
        defs = all_defs if tags is None else [td for td in all_defs if set(td.tags) & tags]
        return "".join(td.system_prompt for td in defs if td.system_prompt)
```

- [ ] **Step 4: Add /agent to command autocomplete list**

In `AyderApp.__init__`, add `/agent` to commands list if agents are configured:

```python
        if self._agent_registry:
            if "/agent" not in self.commands:
                self.commands.append("/agent")
```

- [ ] **Step 5: Verify app starts without agents (no regression)**

Run: `uv run python -c "from ayder_cli.tui.app import AyderApp; print('OK')"`
Expected: `OK` (no import errors)

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ --timeout=10 -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/tui/app.py src/ayder_cli/tui/widgets.py src/ayder_cli/tools/registry.py
git commit -m "feat(agents): wire AgentRegistry, AgentPanel, and call_agent tool into AyderApp"
```

---

## Task 12: Update Documentation

**Files:**
- Modify: `.claude/AGENTS.md`
- Modify: `docs/PROJECT_STRUCTURE.md`

- [ ] **Step 1: Update AGENTS.md structure**

Add `agents/` to the project structure tree section:

```
src/ayder_cli/
├── agents/                # Multi-agent system
│   ├── __init__.py        # Package exports
│   ├── callbacks.py       # AgentCallbacks (ChatCallbacks for agents)
│   ├── config.py          # AgentConfig (Pydantic model)
│   ├── registry.py        # AgentRegistry (lifecycle management)
│   ├── runner.py          # AgentRunner (isolated ChatLoop execution)
│   ├── summary.py         # AgentSummary (structured result)
│   └── tool.py            # call_agent tool definition + handler
```

Add to the module table:

| Module | Purpose |
|--------|---------|
| `agents/config.py` | `AgentConfig` Pydantic model for `[agents.*]` TOML sections |
| `agents/summary.py` | `AgentSummary` dataclass — structured result of agent runs |
| `agents/callbacks.py` | `AgentCallbacks` — `ChatCallbacks` for autonomous agents |
| `agents/runner.py` | `AgentRunner` — wraps one `ChatLoop` per agent dispatch |
| `agents/registry.py` | `AgentRegistry` — dispatch, cancel, status, capability prompts |
| `agents/tool.py` | `call_agent` tool definition + handler factory |

- [ ] **Step 2: Update docs/PROJECT_STRUCTURE.md**

Add agents section to the architecture doc:

```markdown
### Agent System (`agents/`)

The agent system enables specialized sub-agents, each running an isolated
`ChatLoop` with its own LLM provider, model, and context window.

**Key types:**
- `AgentConfig` — parsed from `[agents.*]` TOML sections
- `AgentSummary` — structured result injected into main context
- `AgentRunner` — wraps one `ChatLoop` run per dispatch
- `AgentRegistry` — lifecycle management, dispatch (blocking/async), cancel
- `AgentCallbacks` — `ChatCallbacks` implementation that auto-approves tools
- `call_agent` tool — registered when agents are configured

**Flow (Approach A — all dispatches are non-blocking):**
1. Config parsed → `AgentConfig` objects in `Config.agents`
2. `AyderApp.__init__` creates `AgentRegistry` if agents exist
3. LLM calls `call_agent` tool → `registry.dispatch()` (sync, fire-and-forget)
4. User runs `/agent <name> <task>` → same `registry.dispatch()` (sync, fire-and-forget)
5. Agent runs `ChatLoop` with isolated runtime + `AgentCallbacks` in background
6. Summary parsed from `<agent-summary>` block → `AgentSummary` → pushed to `_summary_queue`
7. `pre_iteration_hook` drains queue and injects summaries as system messages
```

- [ ] **Step 3: Commit**

```bash
git add .claude/AGENTS.md docs/PROJECT_STRUCTURE.md
git commit -m "docs: add agents package to structure docs"
```

---

## Task 13: Integration Test

**Files:**
- Create: `tests/agents/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/agents/test_integration.py
"""Integration test for the multi-agent system end-to-end."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.summary import AgentSummary
from ayder_cli.agents.tool import create_call_agent_handler
from ayder_cli.core.config import Config


class TestAgentIntegration:
    def test_config_to_dispatch_flow(self):
        """End-to-end: parse config → create registry → dispatch (fire-and-forget)."""
        # 1. Parse config with agents
        data = {
            "app": {"provider": "openai", "agent_timeout": 10},
            "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}},
            "agents": {
                "reviewer": {"system_prompt": "You review code."},
            },
        }
        cfg = Config(**data)
        assert "reviewer" in cfg.agents
        assert cfg.agent_timeout == 10

        # 2. Create registry
        registry = AgentRegistry(
            agents=cfg.agents,
            parent_config=cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r", "w"},
            agent_timeout=cfg.agent_timeout,
        )

        # 3. Verify capability prompts
        prompts = registry.get_capability_prompts()
        assert "reviewer" in prompts

        # 4. Dispatch via tool handler (sync, fire-and-forget)
        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentSummary(
                agent_name="reviewer", status="completed", summary="Found 2 issues.", error=None,
            ))

            handler = create_call_agent_handler(registry)
            result = handler(name="reviewer", task="Review auth.py")

        # dispatch() returns immediately with status message
        assert "dispatched" in result.lower()
        assert "reviewer" in result

    def test_summary_injection_format(self):
        """AgentSummary.format_for_injection produces valid system message content."""
        summary = AgentSummary(
            agent_name="test-agent",
            status="completed",
            summary="All tests pass. Coverage at 95%.",
            error=None,
        )
        text = summary.format_for_injection()
        assert "[Agent" in text
        assert "completed" in text
        assert "All tests pass" in text

    def test_config_no_agents_no_capability_prompts(self):
        """When no agents configured, capability prompts are empty."""
        cfg = Config()
        registry = AgentRegistry(
            agents=cfg.agents,
            parent_config=cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        assert registry.get_capability_prompts() == ""

    @pytest.mark.asyncio
    async def test_summary_arrives_via_queue(self):
        """After agent completes, summary is available via drain_summaries."""
        registry = AgentRegistry(
            agents={"test": AgentConfig(name="test", system_prompt="test")},
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        # Simulate a summary being queued (as would happen after agent completion)
        summary = AgentSummary(
            agent_name="test", status="completed", summary="Done.", error=None
        )
        await registry._summary_queue.put(summary)

        # drain_summaries returns it
        summaries = registry.drain_summaries()
        assert len(summaries) == 1
        assert summaries[0].agent_name == "test"

        # Queue is now empty
        assert registry.drain_summaries() == []
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/agents/test_integration.py -v`
Expected: PASS (4 tests)

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ --timeout=10 -x -q`
Expected: All tests pass

- [ ] **Step 4: Run linting and type checking**

Run: `uv run poe check-all`
Expected: All checks pass (or only pre-existing issues)

- [ ] **Step 5: Commit**

```bash
git add tests/agents/test_integration.py
git commit -m "test(agents): add integration test for config → registry → dispatch flow"
```
