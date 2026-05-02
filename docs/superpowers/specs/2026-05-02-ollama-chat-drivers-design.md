# Ollama Chat Drivers — Design Spec

**Date:** 2026-05-02
**Status:** Approved (pending implementation plan)
**Owner:** sinan alyuruk
**Tracks issues:** ollama/ollama#14834, ollama/ollama#14570
**Supersedes:** the `_MODEL_REQUIRES_XML_FALLBACK_PATTERNS` regex routing in `src/ayder_cli/providers/impl/ollama.py`

---

## 1. Problem Statement

The current `OllamaProvider` conflates three concerns into a single 700-line module:

1. **Wire protocol** — speaking Ollama's `/api/chat` over HTTP.
2. **Model-specific prompt engineering** — a universal `XML_INSTRUCTION` string injected as a system prompt to coax models into a custom `<function=>` tool format.
3. **Routing logic** — a hardcoded regex (`_MODEL_REQUIRES_XML_FALLBACK_PATTERNS`) that decides which models bypass Ollama's native tool calling.

This produces three observable failure modes:

- **Qwen3 / qwen3.6 crash mid-stream** with `XML syntax error on line 43: unexpected EOF (status code: -1)` because Ollama's server-side tool extractor (Go) crashes on truncated qwen3 output. This is upstream Ollama bug [#14834](https://github.com/ollama/ollama/issues/14834), unfixed.
- **Models drift away from injected XML format** the longer a session runs. Each follow-up turn weakens adherence to the custom format and the model eventually emits plain narration ("I'll read the file...") with no tool call markup. Confirmed by debug logs from qwen3.6: 80 chars of content, 156 chars of reasoning, zero tool calls extracted.
- **Adding a new model family requires editing core provider code** and updating a regex list, with no isolated test surface.

The user's explicit constraints, captured during brainstorm:

- "We cannot force the model with XML_INSTRUCTIONS all the time."
- "We should be compatible via ollama or openai protocol each time."
- "Model will eventually forget the toolcall."
- "Each LLM requires special attention. Maintain them as separate chat drivers with each test of its own."
- "Use open for extension, closed to edit approach."
- "Keep a small matrix builtin for resolution. We may find a better way in the future."

## 2. Goals

- **Trust Ollama's native protocol** as the default path. Send `tools=[...]`, read `msg.tool_calls`. Stop fighting models that already work.
- **Per-family chat drivers** for the cases where the native path fails. Each driver matches its model's *training* format (qwen3 sees `<tools>...</tools>`, deepseek sees `<function_calls>`), not a custom universal format the model has to be coerced into.
- **Open-closed compliance.** Adding a model family, a minor version, or a custom-trained variant requires creating a new file plus its paired test. No edits to existing drivers, the registry, or the provider.
- **Single source of truth for tested mappings.** A small, explicit data table (`matrix.py`) declares which driver handles which family. Iterating on routing rules touches data, not logic.
- **Reactive fallback safety net.** If the native path crashes mid-stream with a known Ollama server bug signature *before any content was committed*, the same turn is transparently retried via the driver's declared fallback. Committed streams are never silently re-run.
- **Independently testable per-driver behavior.** Each driver ships with its own test file. Touching `qwen3.py` runs `test_qwen3.py` in isolation; no other driver's tests can break.

## 3. Non-Goals

- **Solving Ollama's upstream tool-extraction bug.** That is a separate concern, optionally addressed by an upstream PR. The client-side workaround in this spec ships independently and remains useful regardless of upstream timeline.
- **Rewriting the project in Go.** Considered and rejected as scope expansion. The chat-driver pattern is implementable in Python at ~10% of a rewrite's cost.
- **Replacing `XML_INSTRUCTION` everywhere.** The universal XML instruction survives as the *content* of `GenericXMLDriver` — used only as a last-resort fallback for unknown families that aren't tools-capable. It is no longer the primary or default path for any known family.
- **Touching non-Ollama providers** (OpenAI, Claude, Gemini, DashScope/Qwen, GLM, DeepSeek HTTP). Their wire-level tool calling already works. This redesign is scoped to `OllamaProvider`.
- **Eliminating `chat_protocol="xml"` user override.** The configuration knob remains as a manual escape hatch.

## 4. Decisions Locked During Brainstorm

| # | Question | Decision |
|---|---|---|
| Q1 | Native vs in-content vs hybrid for the wire-level approach | **Hybrid** (D): native first by default, fall back to a per-family chat script when the server is buggy or the model emits tool calls in `msg.content`. |
| Q2 | What is a "proper chat script"? | **B + per-family snippet**: trust Ollama's Modelfile chat template for input rendering when possible; for the fallback path, use per-family system-message snippets that match each model's *training* format. |
| Q3 | How is the native path's brokenness detected? | **A as default + B as safety net**: pre-flight via `OllamaInspector` (`/api/show`) for tested families; reactive error catching as the runtime safety net for unknown breakages. |
| Q4 | Tool description format on the fallback path | **Per-family** snippets that mimic the model's training format. No universal XML instruction as the primary fallback. |
| Q5 | Implementation cost vs ideal | **Practical hybrid (B)**: per-family system-message snippets and per-family parsers, selected via `OllamaInspector.family`. ~95% of an ideal Go-template-rendering solution at ~10% of the cost. |
| extra | Driver registration mechanism | Auto-discovery from `ollama_drivers/` package; new file dropped in is auto-registered. |
| extra | Resolution mechanism | **Two-tier**: a small declarative matrix (data file) for tested mappings, with `ChatDriver.supports()` self-claim as the open-extension hook for custom-trained variants. |
| extra | Upstream Ollama PR | Out-of-scope optional follow-up, not on this spec's critical path. |

## 5. Architecture

Three orthogonal layers, each with one responsibility.

```
┌──────────────────────────────────────────────────────────────────┐
│ OllamaProvider          (wire protocol — /api/chat over HTTP)    │
│ stream_with_tools / chat / list_models                           │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ uses
              ┌───────────────────▼──────────────────┐
              │ ChatDriver                           │ resolved once per
              │ - render_tools_into_messages()       │ session, cached on
              │ - parse_tool_calls()                 │ provider instance
              │ - display_filter()    (optional)     │
              │ - mode: NATIVE | IN_CONTENT          │
              │ - fallback_driver: str | None        │
              └───────────────────┬──────────────────┘
                                  │ resolved by
              ┌───────────────────▼──────────────────┐
              │ DriverRegistry                       │
              │ 1. user override → driver            │
              │ 2. matrix lookup → driver            │
              │ 3. supports() self-claim → driver    │
              │ 4. generic_native default            │
              └─────────┬───────────────────┬────────┘
                        │                   │
        ┌───────────────▼──────┐  ┌─────────▼──────────────┐
        │ matrix.py            │  │ OllamaInspector        │
        │ RESOLUTION_MATRIX    │  │ /api/show → ModelInfo  │
        │ (declarative data)   │  │ family, capabilities,  │
        │                      │  │ name, max_ctx_length   │
        └──────────────────────┘  └────────────────────────┘
```

**What is closed:**

- `OllamaProvider` (only changes if the wire protocol changes)
- `DriverRegistry` (only changes if the resolution algorithm changes)
- `ChatDriver` ABC (only changes if the driver contract changes)

**What is extended:**

- New driver files in `ollama_drivers/` (auto-discovered)
- New rows in `RESOLUTION_MATRIX` (data only)
- Subclassed drivers for minor versions / custom-trained forks (no edits to base drivers)

## 6. Components

### 6.1 `ChatDriver` interface

`src/ayder_cli/providers/impl/ollama_drivers/base.py`

```python
class DriverMode(Enum):
    NATIVE = "native"          # trust Ollama's tools=[...] server-side path
    IN_CONTENT = "in_content"  # model emits tool calls in msg.content


class ChatDriver(ABC):
    """Per-family driver for Ollama tool-calling quirks.

    Each subclass owns one model family's prompt format AND parser AND
    detection. Drivers are independent — adding, modifying, or removing
    one MUST NOT require edits to other drivers, the registry, or the
    provider.
    """

    name: ClassVar[str]                              # unique identifier
    mode: ClassVar[DriverMode]
    priority: ClassVar[int] = 100                    # lower = more specific
    abstract: ClassVar[bool] = False                 # auto-discovery skips abstract bases
    supports_families: ClassVar[tuple[str, ...]] = ()
    fallback_driver: ClassVar[str | None] = None

    @classmethod
    def supports(cls, model_info: ModelInfo) -> bool:
        """Default: case-insensitive substring match on family.
        Subclasses may override for custom logic (name patterns, version
        gating, capability checks)."""
        family = (model_info.family or "").lower()
        return any(f in family for f in cls.supports_families)

    def render_tools_into_messages(
        self, messages: list[dict], tools: list[dict]
    ) -> list[dict]:
        """IN_CONTENT only. Inject tool schemas into the system message in
        the model's training format. NATIVE drivers leave this as the no-op."""
        return messages

    def parse_tool_calls(
        self, content: str, reasoning: str
    ) -> list[ToolCallDef]:
        """IN_CONTENT only. Extract tool calls from raw model output.
        NATIVE drivers leave this as the no-op."""
        return []

    def display_filter(self) -> ToolStreamParser | None:
        """Optional state machine that strips this driver's tool-call markup
        from streaming chunks before they reach the UI. NATIVE drivers
        return None (no filtering needed; tool calls arrive in
        msg.tool_calls, never in content)."""
        return None
```

Class-level metadata is *pure data*. No decorators, no registration side effects, no metaclass magic. The registry reads these attributes via introspection.

### 6.2 Concrete drivers shipped on day one

```
src/ayder_cli/providers/impl/ollama_drivers/
    __init__.py
    base.py              # ChatDriver, DriverMode
    matrix.py            # RESOLUTION_MATRIX (data)
    registry.py          # DriverRegistry
    _errors.py           # OllamaServerToolBug, classify_ollama_error
    generic_native.py    # GenericNativeDriver  (mode=NATIVE)
    generic_xml.py       # GenericXMLDriver     (mode=IN_CONTENT, last-resort fallback)
    qwen3.py             # Qwen3Driver          (qwen2, qwen3 families)
    deepseek.py          # DeepSeekDriver       (deepseek2, deepseek3, deepseek-coder)
    minimax.py           # MiniMaxDriver        (minimax family)
```

Each file is roughly 80-150 lines: class body, family-specific regex constants, render and parse methods.

### 6.3 The resolution matrix

`src/ayder_cli/providers/impl/ollama_drivers/matrix.py` — full module-level docstring documenting WHEN to add rows, WHEN not to, WHEN to remove rows, and migration thresholds.

```python
@dataclass(frozen=True)
class ResolutionRule:
    family_substring: str | None = None
    name_substring: str | None = None
    requires_capability: str | None = None
    driver: str = "generic_native"
    note: str = ""

    def __post_init__(self) -> None:
        if not any([self.family_substring, self.name_substring, self.requires_capability]):
            raise ValueError("ResolutionRule needs at least one matcher dimension")

    def matches(self, info: ModelInfo) -> bool:
        family = (info.family or "").lower()
        name = (info.name or "").lower()
        if self.family_substring and self.family_substring.lower() not in family:
            return False
        if self.name_substring and self.name_substring.lower() not in name:
            return False
        if self.requires_capability and self.requires_capability not in info.capabilities:
            return False
        return True


RESOLUTION_MATRIX: tuple[ResolutionRule, ...] = (
    # ── IN_CONTENT families: known to fight the native path ──
    ResolutionRule(family_substring="qwen3",     driver="qwen3",
                   note="Ollama #14834: native tools=[...] crashes on truncated XML output"),
    ResolutionRule(family_substring="qwen2",     driver="qwen3",
                   note="Same training format as qwen3; reuses qwen3 driver"),
    ResolutionRule(family_substring="deepseek",  driver="deepseek",
                   note="Emits <function_calls><invoke> in msg.content, never msg.tool_calls"),
    ResolutionRule(family_substring="minimax",   driver="minimax",
                   note="Emits <minimax:tool_call> in msg.content"),

    # ── NATIVE families: server-side tool extraction is reliable ──
    ResolutionRule(family_substring="llama",     driver="generic_native"),
    ResolutionRule(family_substring="mistral",   driver="generic_native"),
    ResolutionRule(family_substring="gemma",     driver="generic_native"),
    ResolutionRule(family_substring="phi",       driver="generic_native"),
    ResolutionRule(family_substring="granite",   driver="generic_native"),

    # ── Capability catch-all ──
    ResolutionRule(requires_capability="tools",  driver="generic_native",
                   note="Trust Ollama's native tool extraction for unknown tools-capable families"),
)
```

**Matrix rules** (full text in `matrix.py` module docstring):

- **WHEN to add a row**: model observed in the wild, behaves differently from generic_native, paired test exists, `note` field captures rationale.
- **WHEN NOT to add a row**: custom-trained forks belong in their own driver file via `supports()` self-claim, not in the matrix.
- **WHEN to remove a row**: upstream fix obsoletes the routing decision, family is retired, or row is duplicated by an earlier rule.
- **Order discipline**: most-specific to least-specific, in four tiers (family+name+capability → IN_CONTENT family-only → NATIVE family-only → capability catch-all).
- **Migration thresholds**: if matrix grows past ~30 rows, escalate to (a) YAML/TOML config file, (b) capability scoring, or (c) pure `supports()` self-claim. These are non-goals today.

### 6.4 `DriverRegistry`

`src/ayder_cli/providers/impl/ollama_drivers/registry.py`

```python
class DriverRegistry:
    def __init__(self, inspector: OllamaInspector):
        self._inspector = inspector
        self._drivers = self._auto_discover()
        self._drivers.sort(key=lambda d: d.priority)
        self._by_name = {d.name: d for d in self._drivers}
        self._cache: dict[str, ChatDriver] = {}

    def _auto_discover(self) -> list[ChatDriver]:
        """Import every module in ollama_drivers/, instantiate every concrete
        ChatDriver subclass. Drop a new file in the directory → auto-registered.
        No edits to existing modules."""
        drivers = []
        pkg = import_module("ayder_cli.providers.impl.ollama_drivers")
        for _, modname, _ in iter_modules(pkg.__path__):
            if modname in {"base", "registry", "matrix", "_errors"}:
                continue
            mod = import_module(f"{pkg.__name__}.{modname}")
            for attr in vars(mod).values():
                if (isinstance(attr, type)
                    and issubclass(attr, ChatDriver)
                    and attr is not ChatDriver
                    and not getattr(attr, "abstract", False)):
                    drivers.append(attr())
        return drivers

    async def resolve(self, model: str, override: str | None = None) -> ChatDriver:
        if override and override in self._by_name:
            return self._by_name[override]
        if model in self._cache:
            return self._cache[model]

        try:
            info = await self._inspector.get_model_info(model)
        except Exception as e:
            logger.warning(f"/api/show failed for {model}: {e}; using generic_native")
            return self._by_name["generic_native"]

        # Step 1 — built-in matrix: tested combinations win.
        for rule in RESOLUTION_MATRIX:
            if rule.matches(info) and rule.driver in self._by_name:
                driver = self._by_name[rule.driver]
                logger.debug(f"Matrix matched {model} → {driver.name} ({rule.note or 'no note'})")
                self._cache[model] = driver
                return driver

        # Step 2 — open-extension hook: drivers self-claim.
        for driver in self._drivers:
            if driver.supports(info):
                logger.debug(f"Driver {driver.name} self-claimed {model}")
                self._cache[model] = driver
                return driver

        # Step 3 — safe default.
        return self._by_name["generic_native"]

    def get(self, name: str) -> ChatDriver:
        return self._by_name[name]
```

### 6.5 `ModelInfo` extension

`src/ayder_cli/providers/impl/ollama_inspector.py` adds one field to support name-based custom-trained detection:

```python
@dataclass
class ModelInfo:
    name: str = ""              # NEW — full model name (e.g. "acme/qwen3:7b")
    family: str = ""
    capabilities: list[str] = field(default_factory=list)
    quantization: str = ""
    max_context_length: int = 0
```

`OllamaInspector.get_model_info(model)` populates `name` from its argument. Backward-compatible.

### 6.6 `OllamaProvider` integration

The current `stream_with_tools` (lines 462-543) and `_stream_xml_fallback` (lines 545-625) are replaced by:

```python
async def stream_with_tools(self, messages, model, tools=None, options=None, verbose=False):
    driver = await self._registry.resolve(model, override=self.config.chat_protocol)
    logger.debug(f"Ollama using driver={driver.name} mode={driver.mode.value}")

    committed = False
    try:
        async for chunk in self._stream_with_driver(driver, messages, model, tools, options):
            if chunk.content or chunk.reasoning or chunk.tool_calls:
                committed = True
            yield chunk
    except OllamaServerToolBug as exc:
        if committed or not driver.fallback_driver:
            raise
        fallback = self._registry.get(driver.fallback_driver)
        logger.info(
            f"{driver.name} ({driver.mode.value}) failed mid-stream: {exc!r}; "
            f"transparently retrying with {fallback.name} ({fallback.mode.value})"
        )
        async for chunk in self._stream_with_driver(fallback, messages, model, tools, options):
            yield chunk

async def _stream_with_driver(self, driver, messages, model, tools, options):
    try:
        if driver.mode is DriverMode.NATIVE:
            async for chunk in self._stream_native(messages, model, tools, options):
                yield chunk
        else:
            async for chunk in self._stream_in_content(driver, messages, model, tools, options):
                yield chunk
    except BaseException as exc:
        raise classify_ollama_error(exc) from exc
```

Two helpers (`_stream_native`, `_stream_in_content`) carry today's logic, generalized to take a driver. Total `OllamaProvider` size drops from 700 lines to roughly 350.

## 7. Data Flow (per turn)

### 7.1 Resolution (once per session, cached)

1. First call to `stream_with_tools()` invokes `registry.resolve(model, override=config.chat_protocol)`.
2. Resolver checks override → cache → `/api/show` lookup → matrix walk → `supports()` walk → default.
3. Result cached on the registry instance. Subsequent turns hit the cache.
4. `/api/show` failures are non-fatal: warning logged, `generic_native` returned.

### 7.2 NATIVE-mode turn

1. Provider sends `chat(model, messages, tools=[...])` to Ollama.
2. Ollama's Modelfile template renders the tool list per the model's training format.
3. Stream chunks arrive. `chunk.message.tool_calls` is populated by Ollama's server-side extractor.
4. Provider yields `NormalizedStreamChunk` values verbatim. No driver method calls.

### 7.3 IN_CONTENT-mode turn

1. `driver.render_tools_into_messages(messages, tools)` injects family-native tool description into the system message.
2. Provider sends `chat(model, formatted_messages, tools=None)`. Ollama applies the chat template *without* triggering the broken server-side extractor (since `{{ if .Tools }}` is skipped).
3. Stream chunks arrive. Raw `msg.content` and `msg.thinking` are accumulated.
4. Display layer optionally filters via `driver.display_filter()` to hide tool-call markup from the UI in real time.
5. After stream ends, `driver.parse_tool_calls(raw_content, raw_thinking)` extracts tool calls. Yielded as a final `NormalizedStreamChunk(tool_calls=[...])`.

### 7.4 Fallback path

If a NATIVE-mode stream raises a classified `OllamaServerToolBug` *and* `committed` is `False` *and* the driver declares a `fallback_driver`, the same turn is run again through the fallback driver. The user sees one INFO log line. Original `messages`, `tools`, `model` are reused — no state mutation.

If `committed` is `True`, the bug is re-raised. The chat loop's existing error handler decides UX.

## 8. Error Handling

### 8.1 Fault categories

| Category | Symptom | New handling |
|---|---|---|
| Ollama server tool-extraction bug | `XMLSyntaxError`, `unexpected EOF`, status -1 mid-stream | classified as `OllamaServerToolBug`, triggers reactive fallback if uncommitted |
| Ollama server hard error | HTTP 5xx, connection refused, timeout, OOM | re-raised; retry layer decides; no driver fallback |
| Driver-level parse miss | IN_CONTENT stream completes cleanly but `parse_tool_calls()` returns empty when one was expected | logged at WARNING with raw content; fallback NOT auto-invoked (next turn re-prompts) |

### 8.2 `OllamaServerToolBug` classification

```python
# ollama_drivers/_errors.py
class OllamaServerToolBug(Exception):
    """Server-side tool extractor crashed mid-stream. Distinguished from
    HTTP/network failures so reactive fallback can be triggered."""

_BUG_SIGNATURES: tuple[str, ...] = (
    "xml syntax error",                                  # Ollama #14834
    "unexpected eof",                                    # Ollama #14834
    "failed to parse json: unexpected end of json input",  # Ollama #14570
)

def classify_ollama_error(exc: BaseException) -> Exception:
    if not isinstance(exc, ResponseError):
        return exc
    msg = str(exc).lower()
    if any(sig in msg for sig in _BUG_SIGNATURES):
        return OllamaServerToolBug(str(exc))
    return exc
```

Adding a signature requires linking the upstream Ollama issue in a comment. The list is intentionally short and conservative.

### 8.3 Fallback wiring

| Driver | `fallback_driver` |
|---|---|
| `qwen3` | `"generic_xml"` |
| `deepseek` | `"generic_xml"` |
| `minimax` | `"generic_xml"` |
| `generic_native` | `"generic_xml"` |
| `generic_xml` | `None` (last resort) |

Custom drivers can chain (e.g. `AcmeQwen3Driver.fallback_driver = "qwen3"`) for two-step degrade.

### 8.4 What we never do

- Inject `XML_INSTRUCTION` on the NATIVE path even when extraction returns empty (today's qwen3 problem the user explicitly rejected).
- Silently retry a committed stream — visible stutter is worse than a visible error.
- Auto-fallback on connection / 5xx errors. Those are retry-layer territory.
- Run primary and fallback in parallel.

## 9. Testing Strategy

### 9.1 Per-driver test file

Each driver ships with its own `tests/providers/ollama_drivers/test_<driver>.py`. Each suite imports only the driver under test and `base.py`. Touching `qwen3.py` runs `test_qwen3.py` in isolation; no other suite breaks.

Each driver test covers:

1. **`supports()` matrix** — positive and negative `ModelInfo` fixtures asserting which models the driver claims.
2. **`render_tools_into_messages` golden** — given a known tools list and base messages, the rendered system message matches a fixture string. Catches accidental prompt drift on revision.
3. **`parse_tool_calls` fixtures** — real captured `msg.content` from that family parsed correctly. New model release that changes output format → add a fixture, fail loud, fix in one file.
4. **Round-trip** — render tools → simulate model emitting expected format → parse → assert tool calls equal the input.
5. **`display_filter` (if implemented)** — streaming-time tag stripping correctness.

### 9.2 Matrix tests

`tests/providers/ollama_drivers/test_matrix.py` parametrizes one row per matrix entry:

```python
@pytest.mark.parametrize("model_info, expected_driver", [
    (ModelInfo(name="qwen3.6:latest",  family="qwen3"),    "qwen3"),
    (ModelInfo(name="qwen2.5:7b",      family="qwen2"),    "qwen3"),
    (ModelInfo(name="deepseek-r1:32b", family="deepseek2"), "deepseek"),
    (ModelInfo(name="llama3.1:8b",     family="llama"),    "generic_native"),
    (ModelInfo(name="phi4",            family="phi3"),     "generic_native"),
    (ModelInfo(name="rare-model",      family="unknown",
               capabilities=["tools"]),                    "generic_native"),
    (ModelInfo(name="totally-unknown", family="",
               capabilities=[]),                           "generic_native"),
])
async def test_matrix_resolution(model_info, expected_driver):
    registry = DriverRegistry(stub_inspector(model_info))
    driver = await registry.resolve(model_info.name)
    assert driver.name == expected_driver
```

Changing a matrix row produces a precise diff in this single file.

### 9.3 Registry tests

`tests/providers/ollama_drivers/test_registry.py`:

- Auto-discovery picks up every concrete driver in the package.
- Auto-discovery skips abstract bases (`abstract = True`).
- `override` parameter forces a specific driver regardless of matrix.
- Cache hit returns the same instance on repeated calls for the same model.
- Inspector failure falls back to `generic_native` with a warning.
- `supports()` self-claim path is reached only when matrix produces no match.

### 9.4 Fallback tests

`tests/providers/ollama_drivers/test_fallback.py`:

- Each `_BUG_SIGNATURES` entry → asserted to classify as `OllamaServerToolBug`.
- 5xx, connection, timeout errors → asserted NOT to classify as the tool bug.
- Reactive fallback fires when stream raises before any chunk yielded.
- Reactive fallback does NOT fire when stream raises after content yielded (`committed=True`).
- Reactive fallback does NOT fire on non-tool-bug exceptions.
- Driver with `fallback_driver=None` raises the bug verbatim.
- Two-step fallback (custom → vanilla → generic_xml) walks correctly.

### 9.5 Integration tests

`tests/providers/test_ollama_provider_integration.py`:

- End-to-end: provider construction → first turn triggers `/api/show` → driver resolved → stream completes.
- `chat_protocol="xml"` override forces `GenericXMLDriver` regardless of model.
- `chat_protocol="ollama"` (default) goes through full resolution.
- Multiple turns within a session reuse the cached driver (no extra `/api/show` calls).

## 10. Migration Plan

This is a **non-breaking refactor**. Default behavior for already-tested models (deepseek, llama, etc.) is preserved.

1. **Phase 1 — Scaffolding** (single PR)
   - Add `ollama_drivers/` package with `base.py`, `_errors.py`, `matrix.py`, `registry.py`.
   - Add `GenericNativeDriver` and `GenericXMLDriver` (move existing logic verbatim into these).
   - Wire `OllamaProvider.__init__` to construct `DriverRegistry`.
   - Wire `stream_with_tools` to use the registry. Keep the old code paths intact behind a feature flag (`config.use_chat_drivers = False` default).
   - Tests: `test_base.py`, `test_registry.py`, `test_matrix.py`, `test_fallback.py`, `test_generic_native.py`, `test_generic_xml.py`.

2. **Phase 2 — Family drivers** (one PR per family)
   - `qwen3.py` + `test_qwen3.py`. Includes render template (qwen3-trained `<tools>...</tools>` format) and parser for `<tool_call>{json}</tool_call>` and `<tool_call><function=...>` variants.
   - `deepseek.py` + `test_deepseek.py`. Migrate today's `<function_calls><invoke>` parsing.
   - `minimax.py` + `test_minimax.py`. Migrate today's `<minimax:tool_call>` handling.

3. **Phase 3 — Cutover**
   - Flip `config.use_chat_drivers = True` default.
   - Delete `_MODEL_REQUIRES_XML_FALLBACK_PATTERNS` / `_MODEL_REQUIRES_XML_FALLBACK_RE` / `_requires_xml_fallback`.
   - Delete `_stream_xml_fallback` (logic now lives in `IN_CONTENT` drivers).
   - Delete the old global `XML_INSTRUCTION` from `ollama.py` (lives in `generic_xml.py` now).
   - Update `tests/providers/test_ollama_xml_autoroute.py` to assert via the matrix instead of the regex.

4. **Phase 4 — Cleanup**
   - Remove the feature flag.
   - Update `docs/PROJECT_STRUCTURE.md` with the new module layout.

Backward compatibility:

- `chat_protocol="xml"` user override continues to work — forces `GenericXMLDriver`.
- `chat_protocol="ollama"` default continues to work — same routing decisions for already-tested models.
- All existing model configurations (in user `config.toml` files) work unchanged.

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Driver auto-discovery imports a broken module at startup | Discovery wrapped in try/except per module; broken driver logged at WARNING and skipped, registry still functional. |
| `/api/show` is slow on first turn (extra round-trip) | Resolution cached per model; one extra round-trip per (model, session). Acceptable for the correctness gain. Inspector calls are async and concurrent with stream warmup. |
| Matrix row added speculatively without observation drifts the codebase | Module docstring explicitly forbids speculative entries; each row requires a paired test. Code review catches violations. |
| Custom-trained driver with overly broad `supports()` shadows a tested driver | Matrix tier runs *first*; `supports()` self-claim only runs when no matrix row matches. Step 2 cannot override Step 1. |
| Fallback loops indefinitely | Fallback runs once per turn (no recursive fallback); `generic_xml.fallback_driver = None` is the terminal state; classification is one-shot. |
| Reactive fallback masks a genuine model failure | Logged at INFO (not DEBUG). Persistent fallback firing is observable in operator logs. |

## 12. Future Work

- **Upstream Ollama PR** for issue #14834 — addresses the root cause of the qwen3 native-path crash. Independent timeline; reduces our maintenance burden once shipped and propagated to user-installed Ollama versions.
- **Server-version-gated matrix rules** — when an Ollama fix lands, gate the qwen3 matrix row on `ollama_server_version < "0.X.Y"`. Requires a small `OllamaInspector.server_version()` helper. Out of scope for v1.
- **Capability-scoring resolver** — replace hard `matches()` with a graded `score(info)` per driver. Useful when multiple drivers could plausibly handle the same model. Migration trigger: matrix grows to ~30 rows OR a row needs OR/regex semantics.
- **YAML/TOML matrix loading** — externalize the matrix to a config file so ops can ship hotfixes without code changes. Migration trigger: first ops-driven hotfix request.
- **Pure self-claim resolution** — drop the matrix entirely once driver `supports()` methods cover the field. Migration trigger: matrix entries fully duplicated by `supports()` overrides.

## 13. References

- Ollama issue [#14834](https://github.com/ollama/ollama/issues/14834): "qwen tool call parsing failed XML syntax error".
- Ollama issue [#14570](https://github.com/ollama/ollama/issues/14570): "qwen3 tool call parser returns 500 when output truncated".
- Current implementation: `src/ayder_cli/providers/impl/ollama.py` (700 lines, slated for ~350-line reduction).
- Inspector: `src/ayder_cli/providers/impl/ollama_inspector.py`.
- Existing tests: `tests/providers/test_ollama_xml_autoroute.py` (will be re-targeted at matrix).
- Brainstorm conversation: 2026-05-02 session, Q1–Q5 + matrix refinement.

## 14. Open Questions for Implementation Plan

These are deferred to the writing-plans phase, not blockers for spec approval:

- Exact text of qwen3 system-message snippet — to be authored in `Qwen3Driver` from observed Ollama Modelfile templates and qwen3 training docs.
- Exact text of deepseek system-message snippet — likewise.
- Whether `display_filter()` returns a fresh state machine per turn or a stateless function — implementation detail of `ToolStreamParser`.
- Whether the feature flag is a config key or a `chat_protocol` value (`"drivers"`) during the transition — decided when migration plan is sequenced.
