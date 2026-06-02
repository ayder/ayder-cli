# Optional Provider Dependencies — Design Spec

**Date:** 2026-06-02
**Status:** Draft for review
**Target version:** 2.0.0 (breaking)
**Origin:** Cleanup audit item 2.1 — `impl/{qwen,glm,deepseek}.py` were registered but unreachable. Scope expanded by request: make `anthropic` and `google-genai` optional too. OpenAI and Ollama are the primary drivers and stay core.

**Revisions:** R2 (2026-06-02) — consistency fixes: D5 wording matches §3.1 (explicit SDK list, no self-`[all]`); `create()` uses `_installed()` not raw `find_spec(...) is None`; CLI catches `ProviderUnavailableError` before generic `Exception` to avoid double `Error:` prefix (`cli_runner.py:125`).
R1 (2026-06-02) — resolved 10 review ambiguities: core deps keep loguru/httpx (#3); dev group lists SDKs explicitly, no self-`[all]` (#4); concrete `register()` signature (#5); alias canonicalization is lookup-only, `config.driver` preserved (#6); `find_spec` exceptions → unavailable (#8); no new default `[llm.*]` sections (#9); ASCII-only error message (#10); error-catch ownership fixed — composition propagates, entry points catch, agent path already handled, TUI switch create-then-assign (#1/#2/#7).

---

## 1. Problem

Today `anthropic` and `google-genai` are **hard dependencies** in `pyproject.toml`, so every install pulls heavy SDKs that most users never touch. Meanwhile `dashscope` (Qwen) and `zhipuai` (GLM) are **not declared at all**, so those drivers fail at runtime, and `validate_driver` rejects the `dashscope`/`zhipu`/`deepseek` driver names outright (cleanup audit item 2.1) — making them unreachable even if the SDK were present.

We want:
- **Core install** (`pip install ayder-cli`) = `openai` + `ollama` (+ `deepseek`, which reuses the OpenAI SDK).
- **Optional, per-provider extras** for `anthropic`, `google`, `qwen`, `glm`.
- A **clear, actionable error** when a user selects a driver whose optional package isn't installed.
- All listed drivers **reachable** (fix `validate_driver`).

### Current state (verified)
- The orchestrator (`providers/orchestrator.py`) already resolves provider classes **lazily** via `importlib.import_module` on a class-path string — only the selected driver's module is imported.
- Each rarely-used provider already imports its SDK **lazily** inside `__init__`/methods, not at module top:
  - `impl/claude.py` → `from anthropic import AsyncAnthropic`
  - `impl/gemini.py` → `from google import genai`
  - `impl/qwen.py` → `from dashscope import Generation`
  - `impl/glm.py` → `from zhipuai import ZhipuAI`
  - `impl/deepseek.py` → wraps `OpenAIProvider`; **no extra SDK** (only sets `MAX_TOKENS_PARAM = "max_tokens"`).
- `core/config.py::validate_driver` currently accepts only `{openai, ollama, anthropic, google}`.

This means the work is **packaging + UX + reachability**, not a code restructure of the providers.

---

## 2. Decisions (locked during brainstorming)

| # | Decision |
|---|----------|
| D1 | **Per-provider extras + `all`.** Default install = openai + ollama (+ deepseek). |
| D2 | **Fail-fast** at provider creation with an actionable error that names the exact `pip install` command **and** lists each driver's availability (installed vs not, ASCII — see §3.3). |
| D3 | **DeepSeek is core**, always available (no extra) — it uses the already-core OpenAI SDK. Just unblock it in `validate_driver`. |
| D4 | **Clean break at v2.0.0.** Document in CHANGELOG/README. No phased deprecation. |
| D5 | **Dev group lists the four optional SDKs explicitly** (not a self-reference to `[all]`) so the existing provider suite runs; add simulate-absence unit tests for the missing-dependency path. (See §3.1.) |
| D6 | **Architecture = central capability map** in the orchestrator, using `importlib.util.find_spec` to probe availability without importing heavy SDKs. |

---

## 3. Design

### 3.1 Packaging (`pyproject.toml`)

Remove **only** `anthropic` and `google-genai` from `[project.dependencies]`. All other current core deps stay (including `loguru` and `httpx`, which are unrelated to provider SDKs). Core becomes:
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

[project.optional-dependencies]
anthropic = ["anthropic"]
google    = ["google-genai"]
qwen      = ["dashscope"]
glm       = ["zhipuai"]
all       = ["ayder-cli[anthropic,google,qwen,glm]"]
```
- The `all` *extra* uses self-referential syntax (supported by modern pip/hatchling), keeping it DRY for end users.
- **Dev group (concrete):** `[dependency-groups].dev` lists the four optional SDKs **explicitly** alongside the existing test tooling — `"anthropic"`, `"google-genai"`, `"dashscope"`, `"zhipuai"`. We do **not** self-reference `ayder-cli[all]` from a PEP 735 dependency-group (self-referencing the project in its own group is fragile across resolvers). The explicit list is the single source of truth for dev; the `[all]` extra is for end users.
- **Version**: `1.8.3 → 2.0.0`.

### 3.2 Capability map + availability (`providers/orchestrator.py`)

A single source of truth maps each driver to its requirement:
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DriverCapability:
    provider_path: str           # importlib class path
    sdk_module: str | None       # module to probe; None => core (no extra)
    extra_name: str | None       # pip extra; None => core

_CAPABILITIES: dict[str, DriverCapability] = {
    "openai":    DriverCapability("...impl.openai.OpenAIProvider",      None,           None),
    "ollama":    DriverCapability("...impl.ollama.OllamaProvider",      None,           None),
    "deepseek":  DriverCapability("...impl.deepseek.DeepSeekProvider",  None,           None),
    "anthropic": DriverCapability("...impl.claude.ClaudeProvider",      "anthropic",    "anthropic"),
    "google":    DriverCapability("...impl.gemini.GeminiProvider",      "google.genai", "google"),
    "qwen":      DriverCapability("...impl.qwen.QwenNativeProvider",    "dashscope",    "qwen"),
    "dashscope": DriverCapability("...impl.qwen.QwenNativeProvider",    "dashscope",    "qwen"),  # alias
    "glm":       DriverCapability("...impl.glm.GLMNativeProvider",      "zhipuai",      "glm"),
    "zhipu":     DriverCapability("...impl.glm.GLMNativeProvider",      "zhipuai",      "glm"),    # alias
}
```

`available_drivers() -> dict[str, bool]`:
- Core drivers (`sdk_module is None`) → always `True`.
- Others → probe `importlib.util.find_spec(sdk_module)` (no heavy import). **`find_spec` can raise** (e.g. `ModuleNotFoundError`/`ValueError` for partially-present namespace packages), so wrap it:
  ```python
  def _installed(sdk_module: str | None) -> bool:
      if sdk_module is None:
          return True
      try:
          return importlib.util.find_spec(sdk_module) is not None
      except (ImportError, ValueError, AttributeError):
          return False   # treat any probe failure as "not available"
  ```
- The returned dict is keyed by **canonical** driver name (one entry per provider). Aliases (`dashscope`, `zhipu`) are not separate rows — show `qwen`, `glm` once each.

**Alias canonicalization scope (resolves review #6):** aliasing is applied **only** for the capability lookup inside the orchestrator. `config.driver` is **preserved verbatim** — if a user writes `driver = "dashscope"`, it stays `"dashscope"` in config, logs, and status output; the orchestrator simply maps both `dashscope` and `qwen` to the same `DriverCapability`. Verified there is no downstream coupling on the exact spelling: `providers/retry.py` is not keyed on driver name, and `context_manager_factory` only special-cases `"ollama"` (every other driver, regardless of spelling, gets `DefaultContextManager`). So no normalization of stored state is needed.

`create(config, interaction_sink)`:
1. Look up `cap = _CAPABILITIES[config.driver]` (KeyError → existing "unsupported driver" `ValueError`, listing valid names).
2. If `not _installed(cap.sdk_module)` (the helper from above, which treats `find_spec` exceptions as unavailable) → raise `ProviderUnavailableError(driver, cap.extra_name, available_drivers())`. Use `_installed(...)`, **not** a raw `find_spec(...) is None`, so the exception-handling path isn't bypassed.
3. Otherwise `importlib.import_module(...)` the provider class and instantiate (unchanged).

**`register()` (resolves review #5):** keep backward compatibility — the current signature is `register(driver_name, provider_path)`. Extend with keyword-only optional fields:
```python
def register(self, driver_name: str, provider_path: str, *,
             sdk_module: str | None = None, extra_name: str | None = None) -> None:
    self._capabilities[driver_name] = DriverCapability(provider_path, sdk_module, extra_name)
```
Existing 2-arg callers keep working and register a **core** driver (`sdk_module=None`). Internally `_CAPABILITIES` replaces the old `_providers` dict; `register()` writes into it.

### 3.3 New exception (`providers/base.py`)

```python
class ProviderUnavailableError(RuntimeError):
    """Raised when a driver's optional dependency is not installed."""
    def __init__(self, driver: str, extra: str, available: dict[str, bool]):
        self.driver = driver
        self.extra = extra
        self.available = available
        super().__init__(self._format())
```
**Message format (D2) — ASCII only (resolves review #10):** no Unicode glyphs, since this prints to CLI stderr and CI logs where encoding is not guaranteed. Group by availability rather than per-line check marks:
```
Error: the 'anthropic' driver is not installed.
  Install it with:  pip install ayder-cli[anthropic]

Drivers in this install:
  available:      openai, ollama, deepseek
  not installed:  anthropic, google, qwen, glm
```
(The `available_drivers()` dict drives both rows; canonical names only.)

### 3.4 Config validation (`core/config.py`)

- Widen `validate_driver` accepted set to:
  `{openai, ollama, deepseek, anthropic, google, qwen, dashscope, glm, zhipu}`.
- Add entries to `_DRIVER_BY_PROVIDER` so a `[llm.<profile>]` whose name matches a provider infers the right default driver (e.g. `qwen → qwen`, `glm → glm`, `deepseek → deepseek`).
- Note: `validate_driver` stays a pure name check; **availability** is enforced later by the orchestrator (a name can be valid yet not installed). This separation keeps config parsing free of import side-effects.

**Default config sections (resolves review #9):** Do **not** add `[llm.qwen]`, `[llm.glm]`, or `[llm.deepseek]` to the generated `_DEFAULT_TOML`. The generated config keeps its current profiles (`[llm.openai]`, `[llm.anthropic]`, `[llm.gemini]`) — rarely-used providers are documented as **user-created** profiles in `docs/config.toml.example`, not auto-generated (consistent with their "rarely used" status). The new `_DRIVER_BY_PROVIDER` entries exist so that *if* a user adds e.g. `[llm.qwen]`, the default driver is inferred correctly.

**Profile name vs driver name:** note the existing indirection — a profile named `gemini` maps to driver `google` (`_DRIVER_BY_PROVIDER`). `list_provider_profiles()` / the `/provider` command list **config profile names**, not driver capabilities. This spec does not change that listing; availability is enforced at switch/startup time (§3.5). Annotating `/provider` output with availability is a possible future enhancement, explicitly **out of scope** here.

### 3.5 Error surfacing — ownership (resolves reviews #1, #2, #7)

`provider_orchestrator.create()` is reached from three places. **Composition functions do not catch — they propagate. Entry points catch.**

**(a) `create_runtime()` (`runtime_factory.py:62`) — shared composition.**
Used by CLI, TUI, `cli_runner`, and tests. It must **not** print or exit. It simply lets `ProviderUnavailableError` propagate. Ownership of the catch lives at the actual process entry points:
- **CLI** (`cli.py` `main` and/or `cli_runner.py`): `CommandRunner.run()` (`cli_runner.py:125`) currently has a broad `except Exception: print(f"Error: {e}")`. Since `ProviderUnavailableError`'s message **already starts with `Error:`**, add a **specific `except ProviderUnavailableError as e:` _before_ the generic `Exception`** that prints **`str(e)` as-is** (no `Error: ` prefix) to stderr and returns non-zero. This avoids the double `Error: Error: …` prefix. Apply the same ordering at any other CLI catch site in `cli.py`.
- **TUI launch** (`tui/__init__.py` / wherever the app is constructed before `app.run()`): catch and present `str(e)` as a clean startup error instead of a crash.
- Tests: assert the exception propagates from `create_runtime()` unchanged.

**(b) `create_agent_runtime()` (`runtime_factory.py:168`) — agent path. Already handled.**
Called inside `AgentRunner.run()` (`agents/runner.py:82`), which is wrapped in `try/except Exception` that sets `status="error"` and returns a failed `AgentSummary` (runner.py:174-177). A `ProviderUnavailableError` (a `RuntimeError`) is therefore **already** caught there: the **agent fails in isolation** with the friendly message in its summary, and the **main chat session continues**. No new code; we add a test asserting the summary carries the install hint. (Rationale: one agent's missing optional SDK should not kill the whole session.)

**(c) In-session switch `_apply_provider_switch()` (`tui/commands.py:86-107`).**
The current code already does mutate-then-rollback and catches `(ModuleNotFoundError, ImportError, ValueError)`. Two required changes:
1. `ProviderUnavailableError` is a `RuntimeError`, so it would **escape** the current `except` — add it to the caught set.
2. Prefer the cleaner shape: **create first, assign after success** (no rollback dance):
   ```python
   new_config = load_config_for_provider(provider)
   try:
       new_llm = provider_orchestrator.create(new_config)
   except (ProviderUnavailableError, ModuleNotFoundError, ImportError, ValueError) as e:
       chat_view.add_system_message(str(e))   # keep current provider; nothing mutated
       return
   app.config = new_config
   app.llm = new_llm
   app.chat_loop.llm = app.llm
   # ... model/UI updates ...
   ```
   This removes the need to save/restore `old_config` because `app.config` is only assigned after `create()` succeeds.

The error's `str()` carries the full actionable text, so every site just renders `str(e)`.

### 3.6 Driver names & aliases (UX)

Accepted `driver` values in config:
- `openai`, `ollama`, `deepseek` — core.
- `anthropic` → Claude · `google` → Gemini.
- `qwen` **or** `dashscope` → Qwen · `glm` **or** `zhipu` → GLM.

Rationale: users think in model-family terms (`qwen`, `glm`) but the codebase/vendor APIs use `dashscope`/`zhipu`. Accepting both removes a footgun. Extras are named after the family (`[qwen]`, `[glm]`).

---

## 4. Testing (D5)

- **Dev env** includes all optional SDKs, so existing `tests/providers/test_qwen_async.py`, `test_glm_async.py`, and the claude/gemini tests keep running unchanged.
- **New** `tests/providers/test_optional_providers.py`:
  - `available_drivers()` reports core drivers `True` always.
  - Simulate a missing SDK by monkeypatching `importlib.util.find_spec` (or hiding the module in `sys.modules`) and assert `create()` raises `ProviderUnavailableError` whose message contains `pip install ayder-cli[anthropic]` and **both ASCII rows** (`available:` includes openai/ollama/deepseek; `not installed:` includes anthropic). No Unicode glyphs in the message.
  - `find_spec` raising (not just returning `None`) is treated as unavailable (test the `try/except` in `_installed`).
  - Explicitly cover the dotted-module probe `find_spec("google.genai")` (the `google` namespace is shared with other Google packages, so probing the submodule, not `google`, matters).
  - Core drivers (`openai`/`ollama`/`deepseek`) never raise even with all optional SDKs hidden.
  - Aliases: `driver="dashscope"` and `driver="qwen"` resolve to the same provider; same for `zhipu`/`glm`. Assert `config.driver` is **preserved verbatim** (not normalized).
- **Propagation**: `create_runtime()` re-raises `ProviderUnavailableError` (does not print/exit).
- **Agent path**: with a missing SDK, an agent configured for that driver returns an `AgentSummary` with `status="error"` carrying the install hint; assert the surrounding session is unaffected.
- **In-session switch** (`tui/commands.py`): with the SDK hidden, switching raises/handles `ProviderUnavailableError`, `app.config` and `app.llm` are **unchanged** (create-then-assign), and the message is surfaced.
- **Update** `tests/core/test_config.py` (and coverage variants) for the widened `validate_driver` accepted set + alias names.

**Acceptance:** full suite green with `[all]` installed; the new tests pass; `ruff check src/ tests/` clean.

---

## 5. Documentation (D4)

- **README** install section: core vs. extras —
  `pip install ayder-cli` (core), `pip install ayder-cli[anthropic]`, `[google]`, `[qwen]`, `[glm]`, `[all]`.
- **CHANGELOG / migration note (2.0.0):** "anthropic and google are now optional; install the corresponding extra. Default install ships openai + ollama (+ deepseek)."
- **`docs/config.toml.example`:** note the accepted `driver` values and that non-core drivers require their extra.

---

## 6. File-by-file change list

| File | Change |
|------|--------|
| `pyproject.toml` | move anthropic/google-genai → `[project.optional-dependencies]`; add `qwen`/`glm`/`all`; dev group adds all SDKs; bump to 2.0.0 |
| `src/ayder_cli/providers/base.py` | add `ProviderUnavailableError` |
| `src/ayder_cli/providers/orchestrator.py` | add `DriverCapability`, `_CAPABILITIES`, `available_drivers()`; `find_spec` gate + aliases in `create()` |
| `src/ayder_cli/core/config.py` | widen `validate_driver`; extend `_DRIVER_BY_PROVIDER` |
| `src/ayder_cli/application/runtime_factory.py` | **no catch** — `create_runtime`/`create_agent_runtime` propagate `ProviderUnavailableError` |
| `src/ayder_cli/cli.py` + `cli_runner.py` | add `except ProviderUnavailableError` **before** the existing broad `except Exception` (`cli_runner.py:125`); print `str(e)` as-is (avoid double `Error:` prefix), exit non-zero |
| `src/ayder_cli/tui/__init__.py` (app launch) | catch at TUI startup: clean error message, no crash |
| `src/ayder_cli/agents/runner.py` | **no code change** — existing `except Exception` returns failed `AgentSummary`; add a test |
| `src/ayder_cli/tui/commands.py` (`_apply_provider_switch`) | add `ProviderUnavailableError` to caught set; restructure to create-then-assign (no rollback) |
| `pyproject.toml` | (see §3.1) keep loguru/httpx core; dev group lists 4 SDKs explicitly |
| `tests/providers/test_optional_providers.py` | new |
| `tests/core/test_config.py` (+ coverage) | update for new driver names/aliases |
| `README.md`, `CHANGELOG`, `docs/config.toml.example` | docs |

---

## 7. Out of scope
- Cleanup audit item **2.2** (`DefaultContextManager` `else` branch) — handled separately.
- Refactoring provider internals — they already lazy-import their SDKs.
- Removing any provider — all listed drivers are kept and made reachable.

---

## 8. Risks & notes
- **Breaking change**: existing users relying on anthropic/google by default must add the extra after upgrading. Mitigated by the fail-fast message and the 2.0.0 CHANGELOG note (D4).
- **`find_spec` on dotted modules**: `find_spec("google.genai")` imports parent packages to locate the submodule; acceptable and covered by a dedicated test.
- **Branch note**: this feature is being developed on `feat/optional-provider-deps` off `main`; the separate `cleanup/tier1-dead-code` branch is independent and merges on its own.
