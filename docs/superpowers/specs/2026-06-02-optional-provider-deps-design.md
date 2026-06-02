# Optional Provider Dependencies — Design Spec

**Date:** 2026-06-02
**Status:** Draft for review
**Target version:** 2.0.0 (breaking)
**Origin:** Cleanup audit item 2.1 — `impl/{qwen,glm,deepseek}.py` were registered but unreachable. Scope expanded by request: make `anthropic` and `google-genai` optional too. OpenAI and Ollama are the primary drivers and stay core.

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
| D2 | **Fail-fast** at provider creation with an actionable error that names the exact `pip install` command **and** lists the ✓/✗ availability of all drivers. |
| D3 | **DeepSeek is core**, always available (no extra) — it uses the already-core OpenAI SDK. Just unblock it in `validate_driver`. |
| D4 | **Clean break at v2.0.0.** Document in CHANGELOG/README. No phased deprecation. |
| D5 | **Dev group installs `[all]`** so the existing provider suite runs; add simulate-absence unit tests for the missing-dependency path. |
| D6 | **Architecture = central capability map** in the orchestrator, using `importlib.util.find_spec` to probe availability without importing heavy SDKs. |

---

## 3. Design

### 3.1 Packaging (`pyproject.toml`)

Remove `anthropic` and `google-genai` from `[project.dependencies]`. Core becomes:
```toml
dependencies = [
    "openai",
    "ollama>=0.6.2",
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
- The `all` extra uses self-referential syntax (supported by modern pip/hatchling), keeping it DRY.
- **Dev**: the `[dependency-groups].dev` group adds the optional SDKs (`anthropic`, `google-genai`, `dashscope`, `zhipuai`) so the full test suite runs as today. (Equivalent to installing `[all]` in dev.)
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
- Others → `importlib.util.find_spec(sdk_module) is not None` (no heavy import).
- Aliases collapse to their canonical name in the displayed list (show `qwen`, `glm`, not both spellings).

`create(config, interaction_sink)`:
1. Look up `cap = _CAPABILITIES[config.driver]` (KeyError → existing "unsupported driver" `ValueError`, listing valid names).
2. If `cap.sdk_module` is set and `find_spec(cap.sdk_module) is None` → raise `ProviderUnavailableError(driver, cap.extra_name, available_drivers())`.
3. Otherwise `importlib.import_module(...)` the provider class and instantiate (unchanged).

`register()` extension hook is retained; new registrations may pass a `DriverCapability` (default core).

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
**Message format (D2):**
```
Error: the 'anthropic' driver is not installed.
  Install it with:  pip install ayder-cli[anthropic]

Drivers available in this install:
  ✓ openai   ✓ ollama   ✓ deepseek
  ✗ anthropic   ✗ google   ✗ qwen   ✗ glm
```

### 3.4 Config validation (`core/config.py`)

- Widen `validate_driver` accepted set to:
  `{openai, ollama, deepseek, anthropic, google, qwen, dashscope, glm, zhipu}`.
- Add entries to `_DRIVER_BY_PROVIDER` so a `[llm.<profile>]` whose name matches a provider infers the right default driver (e.g. `qwen → qwen`, `glm → glm`, `deepseek → deepseek`).
- Note: `validate_driver` stays a pure name check; **availability** is enforced later by the orchestrator (a name can be valid yet not installed). This separation keeps config parsing free of import side-effects.

### 3.5 Error surfacing (entry points)

`provider_orchestrator.create()` is called at **three** sites (verified):
1. `application/runtime_factory.py:62` and `:168` — startup provider construction (CLI + TUI launch).
2. `tui/commands.py:102` — the **in-session provider/model switch** (`app.llm = provider_orchestrator.create(new_config)`).

All three must handle `ProviderUnavailableError`:
- **CLI startup**: print the message to stderr (no traceback), exit non-zero.
- **TUI startup**: show as a startup error message rather than crashing.
- **In-session switch** (`tui/commands.py`): catch it, show the message in the chat view, and **keep the current provider** (do not swap `app.llm` / do not mutate config). The switch simply fails gracefully.

The error's `str()` already contains the full actionable text, so each site just renders `str(e)`.

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
  - Simulate a missing SDK by monkeypatching `importlib.util.find_spec` (or hiding the module in `sys.modules`) and assert `create()` raises `ProviderUnavailableError` whose message contains `pip install ayder-cli[anthropic]` and the ✓/✗ list.
  - Explicitly cover the dotted-module probe `find_spec("google.genai")` (the `google` namespace is shared with other Google packages, so probing the submodule, not `google`, matters).
  - Core drivers (`openai`/`ollama`/`deepseek`) never raise even with all optional SDKs hidden.
  - Aliases: `driver="dashscope"` and `driver="qwen"` resolve to the same provider; same for `zhipu`/`glm`.
- **In-session switch** (`tui/commands.py`): with the SDK hidden, switching to that driver raises `ProviderUnavailableError`, the handler keeps the previous `app.llm`, and surfaces the message (assert `app.llm` unchanged).
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
| `src/ayder_cli/application/runtime_factory.py` (+ `cli.py`, `tui/app.py` launch) | catch `ProviderUnavailableError` at startup creation (`:62`, `:168`), print cleanly / exit |
| `src/ayder_cli/tui/commands.py` (`:102`) | catch `ProviderUnavailableError` on in-session switch; show message, keep current provider |
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
