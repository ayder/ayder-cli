# Optional Provider Dependencies — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `anthropic`, `google`, `qwen`, `glm` optional pip extras while `openai`/`ollama`/`deepseek` stay core; selecting an uninstalled driver fails fast with an actionable, ASCII error listing available drivers.

**Architecture:** A central `_CAPABILITIES` map in `ProviderOrchestrator` records each driver's provider class path + optional SDK module + pip extra. Availability is probed with `importlib.util.find_spec` (no heavy import). `create()` raises `ProviderUnavailableError` before importing a provider whose SDK is missing. Composition functions propagate; CLI/TUI entry points catch. `config.driver` is preserved verbatim; aliases (`dashscope`→`qwen`, `zhipu`→`glm`) resolve only at lookup.

**Tech Stack:** Python 3.12, hatchling, PEP 735 dependency-groups, pydantic config, pytest, Textual TUI.

**Spec:** `docs/superpowers/specs/2026-06-02-optional-provider-deps-design.md` (R2).

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `pyproject.toml` | core deps, optional extras, dev group, version | modify |
| `src/ayder_cli/providers/base.py` | `ProviderUnavailableError` exception | modify |
| `src/ayder_cli/providers/__init__.py` | export the exception | modify |
| `src/ayder_cli/providers/orchestrator.py` | capability map, availability, gated `create()`, `register()` | rewrite |
| `src/ayder_cli/core/config.py` | widen `validate_driver`, extend `_DRIVER_BY_PROVIDER` | modify |
| `src/ayder_cli/cli_runner.py` | catch `ProviderUnavailableError` before generic `Exception` | modify |
| `src/ayder_cli/cli.py` | catch around `run_tui` (interactive startup) | modify |
| `src/ayder_cli/tui/commands.py` | `_apply_provider_switch`: create-then-assign + catch | modify |
| `tests/providers/test_orchestrator_capabilities.py` | exception + orchestrator behavior | create |
| `tests/core/test_config.py` | widened driver validation | modify |
| `tests/ui/test_provider_switch.py` | in-session switch failure | create |
| `tests/agents/test_runner_provider_unavailable.py` | agent isolation | create |
| `README.md`, `CHANGELOG.md`, `docs/config.toml.example` | docs | modify |

> Branch note: this plan is executed on `feat/optional-provider-deps` (off `main`). The `cleanup/tier1-dead-code` branch is independent.

---

## Task 1: Packaging — extras, dev group, version bump

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `[project]` dependencies and version**

Set `version = "2.0.0"`. Replace the `dependencies = [...]` block with (removing only `anthropic` and `google-genai`; **keep** loguru/httpx):
```toml
dependencies = [
    "openai",
    "ollama>=0.6.2",
    "loguru",
    "httpx",
    "rich>=13.0.0",
    "textual>=1.0.0,<9.0.0",
    "python-dotenv>=1.0.0",
    "libcst>=1.0.0",
    "tiktoken>=0.7.0",
]
```

- [ ] **Step 2: Add `[project.optional-dependencies]`**

Insert immediately after the `dependencies` array (before `[project.urls]`):
```toml
[project.optional-dependencies]
anthropic = ["anthropic"]
google = ["google-genai"]
qwen = ["dashscope"]
glm = ["zhipuai"]
all = ["ayder-cli[anthropic,google,qwen,glm]"]
```

- [ ] **Step 3: Add the optional SDKs to the dev group explicitly**

In `[dependency-groups]`, append these four to the existing `dev = [...]` list (alongside pytest/ruff/etc.):
```toml
    "anthropic",
    "google-genai",
    "dashscope",
    "zhipuai",
```
(Do NOT use `ayder-cli[all]` here — self-referencing the project in a PEP 735 group is fragile.)

- [ ] **Step 4: Verify the manifest parses and resolves**

Run:
```bash
python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); \
core=d['project']['dependencies']; opt=d['project']['optional-dependencies']; \
assert not any('anthropic' in c or 'google-genai' in c for c in core), core; \
assert set(opt)=={'anthropic','google','qwen','glm','all'}, opt; \
assert d['project']['version']=='2.0.0'; print('pyproject OK')"
/opt/homebrew/bin/uv pip install -e ".[all]" >/dev/null && python -c "import anthropic, google.genai, dashscope, zhipuai; print('extras import OK')"
```
Expected: `pyproject OK` then `extras import OK`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build: make anthropic/google/qwen/glm optional extras; v2.0.0"
```

---

## Task 2: `ProviderUnavailableError` exception

**Files:**
- Modify: `src/ayder_cli/providers/base.py`
- Modify: `src/ayder_cli/providers/__init__.py`
- Test: `tests/providers/test_orchestrator_capabilities.py`

- [ ] **Step 1: Write the failing test**

Create `tests/providers/test_orchestrator_capabilities.py`:
```python
from ayder_cli.providers import ProviderUnavailableError


def test_provider_unavailable_error_message_is_ascii_and_actionable():
    err = ProviderUnavailableError(
        "anthropic", "anthropic",
        {"openai": True, "ollama": True, "deepseek": True,
         "anthropic": False, "google": False, "qwen": False, "glm": False},
    )
    msg = str(err)
    assert "the 'anthropic' driver is not installed" in msg
    assert "pip install ayder-cli[anthropic]" in msg
    assert "available:" in msg and "not installed:" in msg
    # available row lists core drivers; missing row lists anthropic
    assert "openai" in msg.split("available:")[1].split("not installed:")[0]
    assert "anthropic" in msg.split("not installed:")[1]
    # ASCII only — no check/cross glyphs
    assert all(ord(c) < 128 for c in msg)
    assert err.driver == "anthropic" and err.extra == "anthropic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/providers/test_orchestrator_capabilities.py::test_provider_unavailable_error_message_is_ascii_and_actionable -v`
Expected: FAIL with `ImportError: cannot import name 'ProviderUnavailableError'`.

- [ ] **Step 3: Add the exception to `providers/base.py`**

Append at the end of `src/ayder_cli/providers/base.py`:
```python
class ProviderUnavailableError(RuntimeError):
    """Raised when a driver's optional dependency is not installed.

    The string form is a complete, ASCII, user-facing message (already
    prefixed with 'Error:') so entry points can print str(e) verbatim.
    """

    def __init__(self, driver: str, extra: str, available: dict[str, bool]) -> None:
        self.driver = driver
        self.extra = extra
        self.available = available
        super().__init__(self._format())

    def _format(self) -> str:
        installed = [name for name, ok in self.available.items() if ok]
        missing = [name for name, ok in self.available.items() if not ok]
        return (
            f"Error: the '{self.driver}' driver is not installed.\n"
            f"  Install it with:  pip install ayder-cli[{self.extra}]\n"
            f"\n"
            f"Drivers in this install:\n"
            f"  available:      {', '.join(installed)}\n"
            f"  not installed:  {', '.join(missing)}"
        )
```

- [ ] **Step 4: Export it from `providers/__init__.py`**

In `src/ayder_cli/providers/__init__.py`, add `ProviderUnavailableError` to the `from .base import (...)` line and to `__all__`:
```python
from .base import AIProvider, NormalizedStreamChunk, ToolCallDef, _ToolCall, _FunctionCall, ProviderUnavailableError
```
and add `"ProviderUnavailableError",` to the `__all__` list.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python3 -m pytest tests/providers/test_orchestrator_capabilities.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/base.py src/ayder_cli/providers/__init__.py tests/providers/test_orchestrator_capabilities.py
git commit -m "feat(providers): add ProviderUnavailableError with actionable message"
```

---

## Task 3: Orchestrator capability map + availability + gated create()

**Files:**
- Rewrite: `src/ayder_cli/providers/orchestrator.py`
- Test: `tests/providers/test_orchestrator_capabilities.py` (append)

- [ ] **Step 1: Append failing tests**

Add to `tests/providers/test_orchestrator_capabilities.py`:
```python
import importlib.util
from types import SimpleNamespace

import pytest

from ayder_cli.providers.orchestrator import (
    ProviderOrchestrator, DriverCapability, _installed,
)


def _hide_optional(monkeypatch):
    """Make all optional SDKs look uninstalled; keep everything else real."""
    real = importlib.util.find_spec
    hidden = {"anthropic", "google.genai", "dashscope", "zhipuai"}

    def fake(name, *a, **k):
        if name in hidden:
            return None
        return real(name, *a, **k)

    monkeypatch.setattr("importlib.util.find_spec", fake)


def test_core_drivers_always_available(monkeypatch):
    _hide_optional(monkeypatch)
    avail = ProviderOrchestrator().available_drivers()
    assert avail["openai"] and avail["ollama"] and avail["deepseek"]
    assert not avail["anthropic"] and not avail["google"]
    assert not avail["qwen"] and not avail["glm"]
    # aliases are not separate rows
    assert "dashscope" not in avail and "zhipu" not in avail


def test_installed_treats_find_spec_exception_as_unavailable(monkeypatch):
    def boom(name, *a, **k):
        raise ValueError("namespace edge case")
    monkeypatch.setattr("importlib.util.find_spec", boom)
    assert _installed("anything") is False
    assert _installed(None) is True  # core never probes


def test_create_raises_provider_unavailable_for_missing_optional(monkeypatch):
    _hide_optional(monkeypatch)
    from ayder_cli.providers import ProviderUnavailableError
    cfg = SimpleNamespace(driver="anthropic")
    with pytest.raises(ProviderUnavailableError) as ei:
        ProviderOrchestrator().create(cfg)
    assert "pip install ayder-cli[anthropic]" in str(ei.value)


def test_alias_resolves_to_same_capability():
    o = ProviderOrchestrator()
    assert o._capabilities["qwen"].provider_path.endswith("qwen.QwenNativeProvider")
    assert o._canonical("dashscope") == "qwen"
    assert o._canonical("zhipu") == "glm"


def test_register_backward_compatible_two_args():
    o = ProviderOrchestrator()
    o.register("custom", "ayder_cli.providers.impl.openai.OpenAIProvider")
    cap = o._capabilities["custom"]
    assert isinstance(cap, DriverCapability) and cap.sdk_module is None  # core by default
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python3 -m pytest tests/providers/test_orchestrator_capabilities.py -v`
Expected: FAIL (`cannot import name 'DriverCapability'` / `_installed`).

- [ ] **Step 3: Rewrite `orchestrator.py`**

Replace the entire contents of `src/ayder_cli/providers/orchestrator.py` with:
```python
"""
Provider Orchestrator / Registry.

Maps driver names to provider class paths plus optional-dependency metadata.
Availability is probed lazily via importlib.util.find_spec so heavy SDKs are
never imported just to check whether they are installed. config.driver is
never mutated; vendor aliases resolve to a canonical family name at lookup.
"""

import importlib
import importlib.util
from dataclasses import dataclass

from ayder_cli.core.config import Config
from ayder_cli.providers.base import AIProvider, ProviderUnavailableError


@dataclass(frozen=True)
class DriverCapability:
    provider_path: str
    sdk_module: str | None = None   # None => core driver (no optional dependency)
    extra_name: str | None = None   # pip extra that provides sdk_module


def _installed(sdk_module: str | None) -> bool:
    """True if the SDK is importable. Core drivers (None) are always available."""
    if sdk_module is None:
        return True
    try:
        return importlib.util.find_spec(sdk_module) is not None
    except (ImportError, ValueError, AttributeError):
        return False


_IMPL = "ayder_cli.providers.impl"
# Insertion order controls how the availability list is displayed.
_CAPABILITIES: dict[str, DriverCapability] = {
    "openai":    DriverCapability(f"{_IMPL}.openai.OpenAIProvider"),
    "ollama":    DriverCapability(f"{_IMPL}.ollama.OllamaProvider"),
    "deepseek":  DriverCapability(f"{_IMPL}.deepseek.DeepSeekProvider"),
    "anthropic": DriverCapability(f"{_IMPL}.claude.ClaudeProvider",    "anthropic",    "anthropic"),
    "google":    DriverCapability(f"{_IMPL}.gemini.GeminiProvider",    "google.genai", "google"),
    "qwen":      DriverCapability(f"{_IMPL}.qwen.QwenNativeProvider",  "dashscope",    "qwen"),
    "glm":       DriverCapability(f"{_IMPL}.glm.GLMNativeProvider",    "zhipuai",      "glm"),
}
# Vendor-name aliases -> canonical family name.
_ALIASES: dict[str, str] = {"dashscope": "qwen", "zhipu": "glm"}


class ProviderOrchestrator:
    """Registry and factory for AI Providers."""

    def __init__(self) -> None:
        self._capabilities: dict[str, DriverCapability] = dict(_CAPABILITIES)
        self._aliases: dict[str, str] = dict(_ALIASES)

    def register(
        self,
        driver_name: str,
        provider_path: str,
        *,
        sdk_module: str | None = None,
        extra_name: str | None = None,
    ) -> None:
        """Register a provider. Backward compatible: 2-arg calls register a core driver."""
        self._capabilities[driver_name] = DriverCapability(provider_path, sdk_module, extra_name)

    def _canonical(self, driver: str) -> str:
        return self._aliases.get(driver, driver)

    def available_drivers(self) -> dict[str, bool]:
        """Map each canonical driver name -> whether its SDK is importable."""
        return {name: _installed(cap.sdk_module) for name, cap in self._capabilities.items()}

    def _import_provider(self, path: str) -> type[AIProvider]:
        module_name, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def create(self, config: Config, interaction_sink=None) -> AIProvider:
        """Instantiate the provider for config.driver, or raise if its SDK is missing."""
        driver = self._canonical(config.driver)
        cap = self._capabilities.get(driver)
        if cap is None:
            raise ValueError(
                f"Unsupported LLM driver '{config.driver}'. "
                f"Expected one of: {', '.join(self._capabilities.keys())}."
            )
        if not _installed(cap.sdk_module):
            raise ProviderUnavailableError(driver, cap.extra_name, self.available_drivers())
        provider_cls = self._import_provider(cap.provider_path)
        return provider_cls(config, interaction_sink=interaction_sink)


# Module-level singleton for easy import and setup
provider_orchestrator = ProviderOrchestrator()
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python3 -m pytest tests/providers/test_orchestrator_capabilities.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/providers/orchestrator.py tests/providers/test_orchestrator_capabilities.py
git commit -m "feat(providers): capability map + find_spec availability + gated create()"
```

---

## Task 4: Widen driver validation + provider→driver inference

**Files:**
- Modify: `src/ayder_cli/core/config.py` (`validate_driver` ~lines 348-353; `_DRIVER_BY_PROVIDER` ~lines 60-65)
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/core/test_config.py`:
```python
import pytest
from ayder_cli.core.config import Config


@pytest.mark.parametrize("drv", ["openai", "ollama", "deepseek", "anthropic",
                                 "google", "qwen", "dashscope", "glm", "zhipu"])
def test_validate_driver_accepts_all_supported(drv):
    assert Config(driver=drv).driver == drv  # preserved verbatim, incl. aliases


def test_validate_driver_rejects_unknown():
    with pytest.raises(Exception):
        Config(driver="not-a-driver")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python3 -m pytest tests/core/test_config.py -k validate_driver -v`
Expected: FAIL for `deepseek`/`qwen`/`dashscope`/`glm`/`zhipu` (rejected by the old tuple).

- [ ] **Step 3: Widen `validate_driver`**

Replace the `validate_driver` body in `src/ayder_cli/core/config.py`:
```python
    @field_validator("driver")
    @classmethod
    def validate_driver(cls, v: str) -> str:
        valid = (
            "openai", "ollama", "deepseek",
            "anthropic", "google",
            "qwen", "dashscope", "glm", "zhipu",
        )
        if v not in valid:
            raise ValueError(f"driver must be one of: {', '.join(valid)}")
        return v
```

- [ ] **Step 4: Extend `_DRIVER_BY_PROVIDER`**

Replace the `_DRIVER_BY_PROVIDER` dict:
```python
_DRIVER_BY_PROVIDER = {
    "openai": "openai",
    "ollama": "ollama",
    "anthropic": "anthropic",
    "gemini": "google",
    "google": "google",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "dashscope": "dashscope",
    "glm": "glm",
    "zhipu": "zhipu",
}
```

- [ ] **Step 5: Run to verify pass + full config suite**

Run: `.venv/bin/python3 -m pytest tests/core/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/core/config.py tests/core/test_config.py
git commit -m "feat(config): accept deepseek/qwen/glm driver names + aliases"
```

---

## Task 5: CLI entry-point error handling

**Files:**
- Modify: `src/ayder_cli/cli_runner.py` (`CommandRunner.run`, ~line 120-127)
- Modify: `src/ayder_cli/cli.py` (around `run_tui(permissions=granted)`, ~line 353-355)
- Test: `tests/providers/test_orchestrator_capabilities.py` (append a CLI-level test)

- [ ] **Step 1: Write the failing test**

Append to `tests/providers/test_orchestrator_capabilities.py`:
```python
def test_command_runner_prints_provider_error_without_double_prefix(monkeypatch, capsys):
    from ayder_cli import cli_runner
    from ayder_cli.providers import ProviderUnavailableError

    def boom(*a, **k):
        raise ProviderUnavailableError(
            "anthropic", "anthropic",
            {"openai": True, "ollama": True, "deepseek": True,
             "anthropic": False, "google": False, "qwen": False, "glm": False},
        )
    monkeypatch.setattr(cli_runner, "_run_loop", boom)

    runner = cli_runner.CommandRunner(prompt="hi", permissions=set())
    rc = runner.run()
    err = capsys.readouterr().err
    assert rc == 1
    assert "pip install ayder-cli[anthropic]" in err
    assert "Error: Error:" not in err  # no double prefix
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python3 -m pytest tests/providers/test_orchestrator_capabilities.py::test_command_runner_prints_provider_error_without_double_prefix -v`
Expected: FAIL — output contains `Error: Error:` (generic handler re-prefixes).

- [ ] **Step 3: Add the specific catch in `cli_runner.py`**

At the top of `src/ayder_cli/cli_runner.py` add the import:
```python
from ayder_cli.providers import ProviderUnavailableError
```
Then in `CommandRunner.run`, insert the specific handler **before** the generic one:
```python
        try:
            return _run_loop(
                self.prompt,
                permissions=self.permissions,
            )
        except ProviderUnavailableError as e:
            print(str(e), file=sys.stderr)   # message already starts with "Error:"
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
```

- [ ] **Step 4: Wrap the interactive TUI launch in `cli.py`**

In `src/ayder_cli/cli.py`, replace:
```python
        from ayder_cli.tui import run_tui
        run_tui(permissions=granted)
```
with:
```python
        from ayder_cli.tui import run_tui
        from ayder_cli.providers import ProviderUnavailableError
        try:
            run_tui(permissions=granted)
        except ProviderUnavailableError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
```
(`sys` is already imported in `cli.py`.)

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python3 -m pytest tests/providers/test_orchestrator_capabilities.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/cli_runner.py src/ayder_cli/cli.py tests/providers/test_orchestrator_capabilities.py
git commit -m "feat(cli): surface ProviderUnavailableError cleanly at entry points"
```

---

## Task 6: TUI in-session provider switch (create-then-assign)

**Files:**
- Modify: `src/ayder_cli/tui/commands.py` (`_apply_provider_switch`, lines 86-121)
- Test: `tests/ui/test_provider_switch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_provider_switch.py`:
```python
from types import SimpleNamespace

from ayder_cli.tui import commands
from ayder_cli.providers import ProviderUnavailableError


def test_switch_to_unavailable_provider_keeps_current_state(monkeypatch):
    sentinel_llm = object()
    old_config = SimpleNamespace(model="old-model")
    app = SimpleNamespace(
        config=old_config,
        llm=sentinel_llm,
        chat_loop=SimpleNamespace(llm=sentinel_llm, config=SimpleNamespace(model="old-model", num_ctx=1)),
    )
    messages = []
    chat_view = SimpleNamespace(add_system_message=messages.append)

    monkeypatch.setattr(commands, "load_config_for_provider", lambda p: SimpleNamespace(model="new", num_ctx=2), raising=False)

    def boom(_cfg):
        raise ProviderUnavailableError(
            "anthropic", "anthropic",
            {"openai": True, "ollama": True, "deepseek": True,
             "anthropic": False, "google": False, "qwen": False, "glm": False},
        )
    monkeypatch.setattr(commands.provider_orchestrator, "create", boom, raising=False)

    commands._apply_provider_switch(app, "anthropic", chat_view)

    assert app.config is old_config          # not mutated
    assert app.llm is sentinel_llm           # not swapped
    assert messages and "pip install ayder-cli[anthropic]" in messages[0]
```
> Note: this test requires `load_config_for_provider` and `provider_orchestrator` to be **module-level importable names** in `tui/commands.py` (Step 3 moves them to module scope).

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python3 -m pytest tests/ui/test_provider_switch.py -v`
Expected: FAIL (current code does function-local imports / mutates `app.config` before create).

- [ ] **Step 3: Rewrite `_apply_provider_switch`**

At module top of `src/ayder_cli/tui/commands.py`, add the imports (so they are patchable and not re-imported per call):
```python
from ayder_cli.core.config import load_config_for_provider
from ayder_cli.providers import provider_orchestrator, ProviderUnavailableError
```
Replace the body of `_apply_provider_switch` (remove the old function-local imports and the save/rollback):
```python
def _apply_provider_switch(
    app: "AyderApp", provider: str, chat_view: ChatView
) -> None:
    """Switch provider: build config, create provider, then commit on success."""
    new_config = load_config_for_provider(provider)

    # Create FIRST — only mutate app state after a successful build.
    try:
        new_llm = provider_orchestrator.create(new_config)
    except ProviderUnavailableError as e:
        chat_view.add_system_message(str(e))   # already actionable; keep current provider
        return
    except (ModuleNotFoundError, ImportError, ValueError) as e:
        chat_view.add_system_message(f"Cannot switch to {provider}: {e}")
        return

    app.config = new_config
    app.llm = new_llm
    app.chat_loop.llm = app.llm
    app.model = new_config.model
    app.chat_loop.config.model = new_config.model
    app.chat_loop.config.num_ctx = new_config.num_ctx
    app.update_system_prompt_model()

    status_bar = app.query_one("#status-bar", StatusBar)
    status_bar.set_model(new_config.model)

    chat_view.add_system_message(
        f"Switched to provider: {provider} (model: {new_config.model})"
    )
```
> If `AyderApp` is only available under `TYPE_CHECKING`, keep the existing type-hint style already used in this file (quoted string is fine).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python3 -m pytest tests/ui/test_provider_switch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tui/commands.py tests/ui/test_provider_switch.py
git commit -m "feat(tui): provider switch creates-then-assigns; clean unavailable error"
```

---

## Task 7: Agent isolation (test-only — behavior already correct)

**Files:**
- Test: `tests/agents/test_runner_provider_unavailable.py`

- [ ] **Step 1: Write the test**

Create `tests/agents/test_runner_provider_unavailable.py`:
```python
import asyncio
from types import SimpleNamespace

from ayder_cli.agents import runner as runner_mod
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.providers import ProviderUnavailableError


def test_agent_with_missing_provider_returns_error_summary(monkeypatch):
    def boom(*a, **k):
        raise ProviderUnavailableError(
            "anthropic", "anthropic",
            {"openai": True, "ollama": True, "deepseek": True,
             "anthropic": False, "google": False, "qwen": False, "glm": False},
        )
    monkeypatch.setattr(runner_mod, "create_agent_runtime", boom)

    agent_config = SimpleNamespace(name="researcher", model=None)
    r = AgentRunner(
        agent_config=agent_config,
        parent_config=SimpleNamespace(),
        project_ctx=SimpleNamespace(),
        process_manager=SimpleNamespace(),
        permissions=set(),
    )

    summary = asyncio.run(r.run("investigate something"))

    assert summary.status == "error"
    assert "pip install ayder-cli[anthropic]" in summary.error
    assert r.status == "error"  # agent failed in isolation; caller decides what to do
```

- [ ] **Step 2: Run to verify it passes (no production change needed)**

Run: `.venv/bin/python3 -m pytest tests/agents/test_runner_provider_unavailable.py -v`
Expected: PASS — `AgentRunner.run`'s existing `except Exception` converts the error into an `AgentSummary(status="error", error=...)`.
> If it fails because `create_agent_runtime` is imported into `runner` under a different name/path, adjust the monkeypatch target to the actual binding in `src/ayder_cli/agents/runner.py` (currently `from ayder_cli.application.runtime_factory import create_agent_runtime`).

- [ ] **Step 3: Commit**

```bash
git add tests/agents/test_runner_provider_unavailable.py
git commit -m "test(agents): missing optional provider yields error AgentSummary in isolation"
```

---

## Task 8: Documentation

**Files:**
- Modify: `README.md`, `docs/config.toml.example`
- Create/Modify: `CHANGELOG.md`

- [ ] **Step 1: README install section**

Add/replace an install section in `README.md`:
```markdown
## Installation

Core install (OpenAI + Ollama, plus DeepSeek which reuses the OpenAI SDK):

    pip install ayder-cli

Optional providers (install only what you use):

    pip install ayder-cli[anthropic]   # Claude
    pip install ayder-cli[google]      # Gemini
    pip install ayder-cli[qwen]        # Qwen (dashscope)
    pip install ayder-cli[glm]         # GLM (zhipuai)
    pip install ayder-cli[all]         # everything

If you select a driver whose package isn't installed, ayder prints the exact
install command and lists the drivers available in your install.
```

- [ ] **Step 2: CHANGELOG entry (2.0.0)**

Prepend to `CHANGELOG.md` (create if absent):
```markdown
## 2.0.0

### Breaking
- `anthropic` and `google-genai` are no longer installed by default. Install the
  corresponding extra: `pip install ayder-cli[anthropic]` / `[google]`.
- Default install now ships OpenAI + Ollama (+ DeepSeek, which reuses the OpenAI SDK).

### Added
- Optional extras: `[anthropic]`, `[google]`, `[qwen]`, `[glm]`, `[all]`.
- Driver names `deepseek`, `qwen`/`dashscope`, `glm`/`zhipu` are now selectable.
- Selecting an uninstalled driver fails fast with the exact `pip install` command
  and a list of available drivers.
```

- [ ] **Step 3: `docs/config.toml.example` driver note**

Near the `[llm.<provider>]` examples, add a comment:
```toml
# driver may be: openai, ollama, deepseek (core, always available),
#                anthropic, google, qwen (or dashscope), glm (or zhipu)
#                — non-core drivers require their extra:
#                  pip install ayder-cli[anthropic]   (etc.)
```

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md docs/config.toml.example
git commit -m "docs: document optional provider extras and 2.0.0 migration"
```

---

## Final verification

- [ ] **Full suite + lint**

Run:
```bash
/opt/homebrew/bin/uv pip install -e ".[all]" >/dev/null
.venv/bin/python3 -m pytest tests/ -q --timeout=10
.venv/bin/ruff check src/ tests/
```
Expected: all tests pass (new + existing), ruff clean.

- [ ] **Manual smoke (optional)**

```bash
# With all extras present, listing availability should show everything installed:
.venv/bin/python3 -c "from ayder_cli.providers import provider_orchestrator as o; print(o.available_drivers())"
```
Expected: every driver `True`.

---

## Notes for the implementer
- **TDD order matters:** Task 2 must land before Task 3 (orchestrator imports `ProviderUnavailableError`), and Task 3 before Tasks 5-7 (they import the orchestrator/exception).
- `config.driver` is **never** rewritten — aliases are resolved only inside `create()`. Tests assert verbatim preservation (Task 4 Step 1).
- The error message is the single source of user-facing text; entry points print `str(e)` verbatim (it already starts with `Error:`).
- Do not add `[llm.qwen]`/`[llm.glm]`/`[llm.deepseek]` to the generated default config — they are documented in `config.toml.example` only.
