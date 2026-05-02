# Ollama Chat Drivers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `OllamaProvider`'s universal `XML_INSTRUCTION` prompt + regex-based routing with per-family `ChatDriver` classes, a declarative resolution matrix, and reactive fallback on classified Ollama server bugs.

**Architecture:** Three orthogonal layers — `OllamaProvider` (wire protocol), `ChatDriver` (per-family render/parse), `DriverRegistry` (resolution via matrix lookup → `supports()` self-claim → safe default). Drivers live in their own package and are auto-discovered. Adding a new family requires one new file plus its paired test, with no edits to existing modules.

**Tech Stack:** Python 3.12+, `ollama.AsyncClient`, `pytest` + `pytest-asyncio`, `loguru` for logging, `pydantic` for config. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-05-02-ollama-chat-drivers-design.md`](../specs/2026-05-02-ollama-chat-drivers-design.md) (commit `b0e4d73`).

**Migration model:** Non-breaking. A new boolean config field `use_chat_drivers` (default `False` during Phases 1-2) gates the new path. Phase 3 flips the default to `True` and removes the old code. Phase 4 removes the flag.

**Verify after every task:**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

The full suite must stay green at every commit. The current baseline is `1052 passed, 18 skipped` (commit `b0e4d73`).

---

## Phase 1 — Scaffolding (Tasks 1-9)

Builds the new package, the resolution machinery, the two generic drivers, and wires the provider behind a feature flag. After Phase 1 the suite passes with `use_chat_drivers=False` and all old behavior is preserved.

---

### Task 1: Package skeleton + `ChatDriver` base + `DriverMode`

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/__init__.py`
- Create: `src/ayder_cli/providers/impl/ollama_drivers/base.py`
- Create: `tests/providers/ollama_drivers/__init__.py`
- Create: `tests/providers/ollama_drivers/test_base.py`

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_base.py`

```python
"""Tests for the ChatDriver ABC contract."""
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


class _StubDriver(ChatDriver):
    name = "stub"
    mode = DriverMode.NATIVE
    supports_families = ("stub_family",)


def test_drivermode_has_two_values():
    assert {m.value for m in DriverMode} == {"native", "in_content"}


def test_default_supports_matches_family_substring():
    info = ModelInfo(family="STUB_FAMILY", capabilities=["tools"])
    assert _StubDriver.supports(info) is True


def test_default_supports_rejects_when_family_does_not_match():
    info = ModelInfo(family="other", capabilities=["tools"])
    assert _StubDriver.supports(info) is False


def test_default_supports_rejects_when_family_is_empty():
    info = ModelInfo(family="", capabilities=[])
    assert _StubDriver.supports(info) is False


def test_default_render_returns_messages_unchanged():
    driver = _StubDriver()
    messages = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(messages, []) == messages


def test_default_parse_returns_empty_list():
    driver = _StubDriver()
    assert driver.parse_tool_calls("any content", "any reasoning") == []


def test_default_display_filter_returns_none():
    driver = _StubDriver()
    assert driver.display_filter() is None


def test_class_metadata_required():
    """Subclasses MUST set name and mode. The ABC has no defaults."""
    assert _StubDriver.name == "stub"
    assert _StubDriver.mode is DriverMode.NATIVE
    assert _StubDriver.priority == 100
    assert _StubDriver.abstract is False
    assert _StubDriver.fallback_driver is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'ayder_cli.providers.impl.ollama_drivers'`.

- [ ] **Step 3: Create the package files**

`src/ayder_cli/providers/impl/ollama_drivers/__init__.py` — empty file.

`src/ayder_cli/providers/impl/ollama_drivers/base.py`:

```python
"""Base interface for per-family Ollama chat drivers.

Each driver owns one model family's prompt template AND parser AND detection.
Drivers are independent — adding, modifying, or removing one MUST NOT require
edits to other drivers, the registry, or the provider.

See docs/superpowers/specs/2026-05-02-ollama-chat-drivers-design.md §6.1.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Iterator

from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


class DriverMode(Enum):
    NATIVE = "native"          # trust Ollama's tools=[...] server-side path
    IN_CONTENT = "in_content"  # model emits tool calls in msg.content


@dataclass
class StreamEvent:
    """Optional driver display-filter output. Mirrors ollama.py's existing
    StreamEvent so display_filter() can drive the same UI path."""
    type: str  # "content" | "think"
    text: str = ""


class ChatDriver(ABC):
    """Per-family driver for Ollama tool-calling quirks."""

    name: ClassVar[str]
    mode: ClassVar[DriverMode]
    priority: ClassVar[int] = 100         # lower = more specific, runs first
    abstract: ClassVar[bool] = False      # auto-discovery skips abstract bases
    supports_families: ClassVar[tuple[str, ...]] = ()
    fallback_driver: ClassVar[str | None] = None

    @classmethod
    def supports(cls, model_info: ModelInfo) -> bool:
        """Default: case-insensitive substring match on family.
        Subclasses may override for custom logic (name patterns, version
        gating, capability checks)."""
        family = (model_info.family or "").lower()
        return any(f.lower() in family for f in cls.supports_families)

    def render_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """IN_CONTENT only. Inject tool schemas into the system message in
        the model's training format. NATIVE drivers leave this as the no-op."""
        return messages

    def parse_tool_calls(
        self, content: str, reasoning: str
    ) -> list[ToolCallDef]:
        """IN_CONTENT only. Extract tool calls from raw model output.
        NATIVE drivers leave this as the no-op."""
        return []

    def display_filter(self) -> Any:
        """Optional state machine that strips this driver's tool-call markup
        from streaming chunks before they reach the UI. Returns None for
        drivers that don't need filtering (NATIVE drivers always; some
        IN_CONTENT drivers if their tags don't appear in displayed content).
        Drivers that need filtering return a fresh stateful object per turn."""
        return None
```

`tests/providers/ollama_drivers/__init__.py` — empty file.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_base.py -v
```

Expected: `8 passed`.

- [ ] **Step 5: Run full suite (no regression check)**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: `1060 passed, 18 skipped` (was 1052 + 8 new).

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/ tests/providers/ollama_drivers/
git commit -m "feat(ollama): add ChatDriver ABC and DriverMode enum"
```

---

### Task 2: Add `name` field to `ModelInfo`

**Files:**
- Modify: `src/ayder_cli/providers/impl/ollama_inspector.py:14-21`
- Modify: `src/ayder_cli/providers/impl/ollama_inspector.py:38-60` (populate `name`)
- Test: `tests/providers/test_ollama_inspector.py`

- [ ] **Step 1: Write the failing test** — append to `tests/providers/test_ollama_inspector.py`

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from ayder_cli.providers.impl.ollama_inspector import ModelInfo, OllamaInspector


def test_model_info_has_name_field_with_empty_default():
    info = ModelInfo()
    assert info.name == ""


@pytest.mark.asyncio
async def test_get_model_info_populates_name_from_argument(monkeypatch):
    inspector = OllamaInspector()
    fake_response = MagicMock(
        modelinfo={"qwen3.context_length": 32768},
        capabilities=["tools"],
        details=MagicMock(family="qwen3", quantization_level="Q4_K_M"),
    )
    inspector._client.show = AsyncMock(return_value=fake_response)

    info = await inspector.get_model_info("qwen3.6:latest")

    assert info.name == "qwen3.6:latest"
    assert info.family == "qwen3"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/test_ollama_inspector.py -v
```

Expected: `AttributeError` (or assertion failure on `info.name`).

- [ ] **Step 3: Add `name` field + populate it**

In `src/ayder_cli/providers/impl/ollama_inspector.py`, update the `ModelInfo` dataclass (lines 14-21):

```python
@dataclass
class ModelInfo:
    """Model metadata from /api/show."""
    name: str = ""
    max_context_length: int = 0
    capabilities: list[str] = field(default_factory=list)
    quantization: str = ""
    family: str = ""
```

In the same file, update `get_model_info()` to populate `name` (return statement around line 55-60):

```python
return ModelInfo(
    name=model,
    max_context_length=max_ctx,
    capabilities=capabilities,
    quantization=quantization,
    family=family,
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/test_ollama_inspector.py -v
```

Expected: all tests pass, including the two new ones.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_inspector.py tests/providers/test_ollama_inspector.py
git commit -m "feat(ollama): add name field to ModelInfo"
```

---

### Task 3: `ResolutionRule` + `RESOLUTION_MATRIX`

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/matrix.py`
- Create: `tests/providers/ollama_drivers/test_matrix.py`

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_matrix.py`

```python
"""Tests for the resolution matrix (data) and ResolutionRule (logic)."""
import pytest

from ayder_cli.providers.impl.ollama_drivers.matrix import (
    RESOLUTION_MATRIX,
    ResolutionRule,
)
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_rule_requires_at_least_one_matcher():
    with pytest.raises(ValueError, match="at least one matcher"):
        ResolutionRule(driver="generic_native")


def test_rule_family_substring_case_insensitive():
    rule = ResolutionRule(family_substring="qwen3", driver="qwen3")
    assert rule.matches(ModelInfo(family="QWEN3"))
    assert rule.matches(ModelInfo(family="qwen3"))
    assert not rule.matches(ModelInfo(family="qwen2"))


def test_rule_name_substring_case_insensitive():
    rule = ResolutionRule(name_substring="acme/qwen", driver="acme")
    assert rule.matches(ModelInfo(name="ACME/Qwen3:7b"))
    assert not rule.matches(ModelInfo(name="other/qwen3"))


def test_rule_capability_exact_match():
    rule = ResolutionRule(requires_capability="tools", driver="generic_native")
    assert rule.matches(ModelInfo(capabilities=["tools", "vision"]))
    assert not rule.matches(ModelInfo(capabilities=["vision"]))


def test_rule_all_dimensions_anded():
    rule = ResolutionRule(
        family_substring="qwen3",
        requires_capability="tools",
        driver="qwen3",
    )
    assert rule.matches(ModelInfo(family="qwen3", capabilities=["tools"]))
    assert not rule.matches(ModelInfo(family="qwen3", capabilities=[]))
    assert not rule.matches(ModelInfo(family="llama", capabilities=["tools"]))


@pytest.mark.parametrize("model_info, expected_driver", [
    # IN_CONTENT families
    (ModelInfo(name="qwen3.6:latest",  family="qwen3"),    "qwen3"),
    (ModelInfo(name="qwen2.5:7b",      family="qwen2"),    "qwen3"),
    (ModelInfo(name="deepseek-r1:32b", family="deepseek2"), "deepseek"),
    (ModelInfo(name="minimax-m1",      family="minimax"),  "minimax"),
    # NATIVE families
    (ModelInfo(name="llama3.1:8b",     family="llama"),    "generic_native"),
    (ModelInfo(name="mistral-nemo",    family="mistral"),  "generic_native"),
    (ModelInfo(name="gemma2:27b",      family="gemma"),    "generic_native"),
    (ModelInfo(name="phi4",            family="phi3"),     "generic_native"),
    (ModelInfo(name="granite-code",    family="granite"),  "generic_native"),
    # Capability catch-all
    (ModelInfo(name="rare-model",  family="unknown",
               capabilities=["tools"]),                    "generic_native"),
])
def test_matrix_routes_known_combinations(model_info, expected_driver):
    """Walk the matrix in order — first match wins."""
    matched = next(
        (r for r in RESOLUTION_MATRIX if r.matches(model_info)),
        None,
    )
    assert matched is not None, f"No matrix entry matched {model_info}"
    assert matched.driver == expected_driver


def test_matrix_returns_no_match_for_truly_unknown_model():
    info = ModelInfo(name="totally-unknown", family="", capabilities=[])
    matched = next(
        (r for r in RESOLUTION_MATRIX if r.matches(info)),
        None,
    )
    assert matched is None  # Registry handles default elsewhere


def test_matrix_rows_are_frozen_dataclasses():
    for rule in RESOLUTION_MATRIX:
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            rule.driver = "mutated"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_matrix.py -v
```

Expected: `ModuleNotFoundError: No module named '...matrix'`.

- [ ] **Step 3: Implement `matrix.py`** — `src/ayder_cli/providers/impl/ollama_drivers/matrix.py`

```python
"""
Resolution matrix for Ollama chat drivers.

WHAT THIS FILE IS
─────────────────
A single, ordered list of (matcher → driver) mappings. The DriverRegistry
walks this list top-to-bottom and the first row whose matcher returns True
wins. This is data, not logic: edits here are intentionally separated from
edits to driver implementations, the registry, or the provider.

WHEN TO ADD A ROW
─────────────────
Add a row when ALL of the following are true:
  1. We have OBSERVED the model in the wild (real /api/show output, real
     chat sessions). Speculative entries belong as comments, not rows.
  2. The model behaves DIFFERENTLY from what generic_native or the existing
     family rule would do — i.e. the row actually changes routing.
  3. There is a paired test in tests/providers/ollama_drivers/test_matrix.py
     asserting the resolution.
  4. The `note` field captures the rationale (which Ollama issue, which
     model quirk, which training format) so future readers don't have to
     re-derive it from git blame.

WHEN NOT TO ADD A ROW
─────────────────────
Custom-trained forks, fine-tunes, and one-off variants do NOT belong here.
Use the open-extension hook instead: subclass an existing driver, override
ChatDriver.supports() with the specific name match, and drop the file in
ollama_drivers/. The registry's Step 2 (self-claim) picks it up.

WHEN TO REMOVE A ROW
────────────────────
Remove a row when:
  • An upstream Ollama fix lands that obsoletes the routing decision.
  • A model family that previously needed special handling is retired.
  • The row is duplicated by an earlier rule (audit periodically).

ROW ORDER
─────────
First match wins. Order rows from most specific to least specific:
  1. Family + name + capability rules (custom-precise)
  2. Family-only rules for known IN_CONTENT families (qwen3, deepseek, ...)
  3. Family-only rules for known NATIVE families (llama, mistral, ...)
  4. Capability catch-alls (requires_capability="tools")

The default fallback (generic_native) lives in the registry, not the matrix.
"""
from __future__ import annotations

from dataclasses import dataclass

from ayder_cli.providers.impl.ollama_inspector import ModelInfo


@dataclass(frozen=True)
class ResolutionRule:
    """One row in the built-in resolution matrix.

    Matchers are AND-combined. None means 'don't check this dimension'.
    At least one matcher must be specified."""
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


# ─── Matrix entries ──────────────────────────────────────────────────────
# (See module docstring for the rules of this list.)
RESOLUTION_MATRIX: tuple[ResolutionRule, ...] = (
    # ── IN_CONTENT families: known to fight the native path ──
    ResolutionRule(
        family_substring="qwen3",
        driver="qwen3",
        note="Ollama #14834: native tools=[...] crashes on truncated XML output",
    ),
    ResolutionRule(
        family_substring="qwen2",
        driver="qwen3",
        note="Same training format as qwen3; reuses qwen3 driver",
    ),
    ResolutionRule(
        family_substring="deepseek",
        driver="deepseek",
        note="Emits <function_calls><invoke> in msg.content, never msg.tool_calls",
    ),
    ResolutionRule(
        family_substring="minimax",
        driver="minimax",
        note="Emits <minimax:tool_call> in msg.content (namespaced)",
    ),

    # ── NATIVE families: server-side tool extraction is reliable ──
    ResolutionRule(family_substring="llama",   driver="generic_native"),
    ResolutionRule(family_substring="mistral", driver="generic_native"),
    ResolutionRule(family_substring="gemma",   driver="generic_native"),
    ResolutionRule(family_substring="phi",     driver="generic_native"),
    ResolutionRule(family_substring="granite", driver="generic_native"),

    # ── Capability catch-all ──
    ResolutionRule(
        requires_capability="tools",
        driver="generic_native",
        note="Trust Ollama's native tool extraction for unknown tools-capable families",
    ),
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_matrix.py -v
```

Expected: all parametrized cases + dimension tests pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/matrix.py tests/providers/ollama_drivers/test_matrix.py
git commit -m "feat(ollama): add ResolutionRule and RESOLUTION_MATRIX"
```

---

### Task 4: `OllamaServerToolBug` + `classify_ollama_error`

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/_errors.py`
- Create: `tests/providers/ollama_drivers/test_errors.py`

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_errors.py`

```python
"""Tests for OllamaServerToolBug classification."""
import pytest
from ollama import ResponseError

from ayder_cli.providers.impl.ollama_drivers._errors import (
    OllamaServerToolBug,
    classify_ollama_error,
)


@pytest.mark.parametrize("message", [
    "XML syntax error on line 43: unexpected EOF",
    "xml syntax error: unexpected eof",
    "failed to parse JSON: unexpected end of JSON input",
    "Failed to parse JSON: unexpected end of JSON input at line 5",
])
def test_known_bug_signatures_classify_as_tool_bug(message):
    err = ResponseError(message)
    out = classify_ollama_error(err)
    assert isinstance(out, OllamaServerToolBug)
    assert message.lower() in str(out).lower()


@pytest.mark.parametrize("message", [
    "model not found",
    "context length exceeded",
    "connection refused",
    "rate limit exceeded",
    "internal server error",
])
def test_unrelated_response_errors_pass_through_unchanged(message):
    err = ResponseError(message)
    out = classify_ollama_error(err)
    assert out is err
    assert not isinstance(out, OllamaServerToolBug)


def test_non_response_errors_pass_through_unchanged():
    err = TimeoutError("connection timed out")
    out = classify_ollama_error(err)
    assert out is err


def test_classify_does_not_match_when_signature_only_in_args_repr_not_message():
    """Don't false-positive on errors that mention the bug words tangentially."""
    err = ResponseError("model called 'xml-syntax-checker' is not installed")
    # "xml syntax" is a substring; document this is the conservative behavior:
    # we DO match here. Keep the signature list strict.
    out = classify_ollama_error(err)
    assert isinstance(out, OllamaServerToolBug)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_errors.py -v
```

Expected: `ModuleNotFoundError: No module named '..._errors'`.

- [ ] **Step 3: Implement `_errors.py`** — `src/ayder_cli/providers/impl/ollama_drivers/_errors.py`

```python
"""Error classification for Ollama server-side tool-extraction bugs."""
from __future__ import annotations

from ollama import ResponseError


class OllamaServerToolBug(Exception):
    """Server-side tool extractor crashed mid-stream. Distinguished from
    HTTP/network failures so reactive driver fallback can be triggered.
    Emitted by classify_ollama_error() when the response error message
    matches one of _BUG_SIGNATURES."""


# Each entry must reference the upstream Ollama issue it corresponds to.
# Adding a signature without an issue number is forbidden — the list is
# intentionally short and conservative to avoid false positives.
_BUG_SIGNATURES: tuple[str, ...] = (
    "xml syntax error",                                    # Ollama #14834
    "unexpected eof",                                      # Ollama #14834
    "failed to parse json: unexpected end of json input",  # Ollama #14570
)


def classify_ollama_error(exc: BaseException) -> Exception:
    """Inspect an ollama.ResponseError and decide if it is the known
    server-side tool-extraction bug. Returns OllamaServerToolBug if so;
    otherwise returns `exc` unchanged.

    Non-ResponseError exceptions are passed through. The classifier never
    swallows or wraps anything else."""
    if not isinstance(exc, ResponseError):
        return exc
    msg = str(exc).lower()
    if any(sig in msg for sig in _BUG_SIGNATURES):
        return OllamaServerToolBug(str(exc))
    return exc
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_errors.py -v
```

Expected: all 11 test cases pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/_errors.py tests/providers/ollama_drivers/test_errors.py
git commit -m "feat(ollama): add OllamaServerToolBug error classifier"
```

---

### Task 5: `DriverRegistry` with auto-discovery

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/registry.py`
- Create: `tests/providers/ollama_drivers/test_registry.py`

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_registry.py`

```python
"""Tests for DriverRegistry auto-discovery and resolve()."""
import pytest
from unittest.mock import AsyncMock

from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode
from ayder_cli.providers.impl.ollama_drivers.registry import DriverRegistry
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def _stub_inspector(info_or_exc):
    inspector = AsyncMock()
    if isinstance(info_or_exc, Exception):
        inspector.get_model_info.side_effect = info_or_exc
    else:
        inspector.get_model_info.return_value = info_or_exc
    return inspector


@pytest.mark.asyncio
async def test_auto_discovery_finds_concrete_driver_subclasses():
    """Any concrete ChatDriver in ollama_drivers/ MUST be auto-registered.
    At minimum, generic_native and generic_xml will exist after later tasks;
    this test asserts the discovery mechanism, not the specific drivers."""
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)
    # Auto-discovery must find at least the registry can be constructed
    # without exploding even before any drivers exist. The placeholder
    # generic_native driver gets added in Task 6.
    assert registry is not None
    assert hasattr(registry, "_drivers")


@pytest.mark.asyncio
async def test_auto_discovery_skips_abstract_bases():
    """ChatDriver.abstract = True must be skipped by auto-discovery."""
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)
    # ChatDriver itself must NOT appear in _by_name
    assert "ChatDriver" not in (d.__class__.__name__ for d in registry._drivers)


@pytest.mark.asyncio
async def test_resolve_uses_user_override_first():
    """Override forces a specific driver regardless of model family."""
    # Register a fake driver into _by_name to confirm override path
    inspector = _stub_inspector(ModelInfo(family="qwen3"))
    registry = DriverRegistry(inspector)

    class _FakeOverride(ChatDriver):
        name = "fake_override"
        mode = DriverMode.NATIVE

    registry._by_name["fake_override"] = _FakeOverride()
    registry._drivers.append(_FakeOverride())

    driver = await registry.resolve("any-model", override="fake_override")
    assert driver.name == "fake_override"
    inspector.get_model_info.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_caches_on_repeat_call():
    inspector = _stub_inspector(ModelInfo(family="llama", name="llama3.1:8b",
                                          capabilities=["tools"]))
    registry = DriverRegistry(inspector)

    a = await registry.resolve("llama3.1:8b")
    b = await registry.resolve("llama3.1:8b")
    assert a is b
    inspector.get_model_info.assert_called_once_with("llama3.1:8b")


@pytest.mark.asyncio
async def test_resolve_falls_back_to_generic_native_when_inspector_fails(caplog):
    inspector = _stub_inspector(RuntimeError("boom"))
    registry = DriverRegistry(inspector)

    driver = await registry.resolve("any-model")
    # generic_native must exist by Task 6; this test runs in Task 5 only after
    # generic_native is added, so split: see assert_resolves_to_known_default.
    # For Task 5, replace the assertion with: when inspector fails, return
    # whatever is registered as "generic_native" if present, else any default.
    # See implementation note in the docstring.


@pytest.mark.asyncio
async def test_get_returns_driver_by_name():
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)

    class _FakeDriver(ChatDriver):
        name = "fake_x"
        mode = DriverMode.NATIVE

    registry._by_name["fake_x"] = _FakeDriver()
    assert registry.get("fake_x").name == "fake_x"


@pytest.mark.asyncio
async def test_get_raises_keyerror_on_unknown_name():
    inspector = _stub_inspector(ModelInfo(family="llama"))
    registry = DriverRegistry(inspector)
    with pytest.raises(KeyError):
        registry.get("not_registered")
```

NOTE: `test_resolve_falls_back_to_generic_native_when_inspector_fails` is intentionally a no-op assertion in Task 5 — it gets concrete in Task 6 once `generic_native` exists. Leave the docstring; the real assertion is added in Task 6.

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_registry.py -v
```

Expected: `ModuleNotFoundError: No module named '...registry'`.

- [ ] **Step 3: Implement `registry.py`** — `src/ayder_cli/providers/impl/ollama_drivers/registry.py`

```python
"""Driver registry with auto-discovery and matrix-first resolution.

Resolution order:
  1. User override (`config.chat_protocol` or explicit driver name)
  2. Cache hit (same model resolved earlier this session)
  3. Built-in matrix lookup (RESOLUTION_MATRIX in matrix.py)
  4. Driver self-claim via supports() — open-extension hook for custom-trained
  5. Safe default: generic_native

Auto-discovery walks every module in ollama_drivers/ at construction time
and instantiates every concrete ChatDriver subclass found. Modules whose
basename appears in _SKIP_MODULES are skipped (infrastructure, not drivers).
"""
from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules
from typing import Any

from loguru import logger

from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver
from ayder_cli.providers.impl.ollama_drivers.matrix import RESOLUTION_MATRIX

_SKIP_MODULES: frozenset[str] = frozenset({"base", "registry", "matrix", "_errors"})


class DriverRegistry:
    def __init__(self, inspector: Any):
        self._inspector = inspector
        self._drivers: list[ChatDriver] = self._auto_discover()
        self._drivers.sort(key=lambda d: d.priority)
        self._by_name: dict[str, ChatDriver] = {d.name: d for d in self._drivers}
        self._cache: dict[str, ChatDriver] = {}

    def _auto_discover(self) -> list[ChatDriver]:
        drivers: list[ChatDriver] = []
        pkg = import_module("ayder_cli.providers.impl.ollama_drivers")
        for _, modname, _ in iter_modules(pkg.__path__):
            if modname in _SKIP_MODULES:
                continue
            try:
                mod = import_module(f"{pkg.__name__}.{modname}")
            except Exception as e:
                logger.warning(f"Skipping driver module '{modname}': {e}")
                continue
            for attr in vars(mod).values():
                if (isinstance(attr, type)
                    and issubclass(attr, ChatDriver)
                    and attr is not ChatDriver
                    and not getattr(attr, "abstract", False)):
                    drivers.append(attr())
        return drivers

    async def resolve(self, model: str, override: str | None = None) -> ChatDriver:
        # Step 1 — explicit override wins
        if override and override in self._by_name:
            return self._by_name[override]

        # Step 2 — session cache
        if model in self._cache:
            return self._cache[model]

        # Step 3 — inspector lookup
        try:
            info = await self._inspector.get_model_info(model)
        except Exception as e:
            logger.warning(f"/api/show failed for {model!r}: {e}; using generic_native")
            return self._by_name.get("generic_native", self._drivers[0])

        # Step 4 — matrix lookup
        for rule in RESOLUTION_MATRIX:
            if rule.matches(info) and rule.driver in self._by_name:
                driver = self._by_name[rule.driver]
                logger.debug(
                    f"Matrix matched {model!r} → {driver.name} "
                    f"({rule.note or 'no note'})"
                )
                self._cache[model] = driver
                return driver

        # Step 5 — driver self-claim (open-extension hook)
        for driver in self._drivers:
            if driver.supports(info):
                logger.debug(f"Driver {driver.name} self-claimed {model!r}")
                self._cache[model] = driver
                return driver

        # Step 6 — safe default
        return self._by_name.get("generic_native", self._drivers[0])

    def get(self, name: str) -> ChatDriver:
        return self._by_name[name]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_registry.py -v
```

Expected: all tests pass except the inspector-fail test which is a placeholder until Task 6.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/registry.py tests/providers/ollama_drivers/test_registry.py
git commit -m "feat(ollama): add DriverRegistry with auto-discovery"
```

---

### Task 6: `GenericNativeDriver`

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/generic_native.py`
- Create: `tests/providers/ollama_drivers/test_generic_native.py`
- Modify: `tests/providers/ollama_drivers/test_registry.py` — concrete assertion in `test_resolve_falls_back_to_generic_native_when_inspector_fails`

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_generic_native.py`

```python
"""GenericNativeDriver smoke tests — it has no behavior, only metadata."""
from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.generic_native import GenericNativeDriver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_generic_native_metadata():
    assert GenericNativeDriver.name == "generic_native"
    assert GenericNativeDriver.mode is DriverMode.NATIVE
    assert GenericNativeDriver.fallback_driver == "generic_xml"
    assert GenericNativeDriver.priority >= 100  # generic, not specific


def test_generic_native_default_supports_does_not_self_claim():
    """generic_native is matrix-routed, not self-claimed."""
    driver = GenericNativeDriver()
    assert driver.supports(ModelInfo(family="anything")) is False


def test_generic_native_render_is_passthrough():
    driver = GenericNativeDriver()
    msgs = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(msgs, [{"type": "function"}]) == msgs


def test_generic_native_parse_returns_empty():
    driver = GenericNativeDriver()
    assert driver.parse_tool_calls("any", "any") == []


def test_generic_native_display_filter_is_none():
    driver = GenericNativeDriver()
    assert driver.display_filter() is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_generic_native.py -v
```

Expected: `ModuleNotFoundError: No module named '...generic_native'`.

- [ ] **Step 3: Implement `generic_native.py`** — `src/ayder_cli/providers/impl/ollama_drivers/generic_native.py`

```python
"""GenericNativeDriver — trusts Ollama's server-side tool extraction.

Used for model families whose Ollama Modelfile chat template correctly
renders tools=[...] AND whose extracted tool calls populate msg.tool_calls
natively. Matched via the matrix's family-only rules (llama, mistral,
gemma, phi, granite) and the capability catch-all.

This driver has no IN_CONTENT behavior. The provider's NATIVE-mode path
yields chunks verbatim from msg.tool_calls. render_*/parse_* are intentional
no-ops.
"""
from __future__ import annotations

from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode


class GenericNativeDriver(ChatDriver):
    name = "generic_native"
    mode = DriverMode.NATIVE
    priority = 900       # routed via matrix, never via self-claim
    fallback_driver = "generic_xml"
    # Empty supports_families means default supports() always returns False.
    # generic_native is reached via matrix rule, not self-claim.
    supports_families = ()
```

- [ ] **Step 4: Update the registry test that was a placeholder in Task 5**

In `tests/providers/ollama_drivers/test_registry.py`, replace the body of `test_resolve_falls_back_to_generic_native_when_inspector_fails`:

```python
@pytest.mark.asyncio
async def test_resolve_falls_back_to_generic_native_when_inspector_fails(caplog):
    inspector = _stub_inspector(RuntimeError("boom"))
    registry = DriverRegistry(inspector)

    driver = await registry.resolve("any-model")
    assert driver.name == "generic_native"
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_generic_native.py tests/providers/ollama_drivers/test_registry.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/generic_native.py tests/providers/ollama_drivers/test_generic_native.py tests/providers/ollama_drivers/test_registry.py
git commit -m "feat(ollama): add GenericNativeDriver"
```

---

### Task 7: `GenericXMLDriver` (port today's `XML_INSTRUCTION` + parser)

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/generic_xml.py`
- Create: `tests/providers/ollama_drivers/test_generic_xml.py`

This is a port — the prompt text and parsing logic come verbatim from today's `ollama.py:57-101` (`XML_INSTRUCTION` + `inject_xml_prompt`) and from `XMLParserAdapter` (lines 393-420). The old code stays in place during Phase 1; we are duplicating it into the new package so the new path is self-contained. The old code is deleted in Phase 3.

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_generic_xml.py`

```python
"""Tests for GenericXMLDriver — the universal IN_CONTENT fallback."""
from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.generic_xml import GenericXMLDriver


def test_generic_xml_metadata():
    assert GenericXMLDriver.name == "generic_xml"
    assert GenericXMLDriver.mode is DriverMode.IN_CONTENT
    assert GenericXMLDriver.fallback_driver is None  # last resort
    assert GenericXMLDriver.priority >= 900


def test_render_injects_instruction_into_existing_system_message():
    driver = GenericXMLDriver()
    messages = [
        {"role": "system", "content": "base system"},
        {"role": "user", "content": "hi"},
    ]
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    out = driver.render_tools_into_messages(messages, tools)
    assert out[0]["role"] == "system"
    assert "base system" in out[0]["content"]
    assert "TOOL PROTOCOL:" in out[0]["content"]
    assert "read_file" in out[0]["content"]
    # Tail messages preserved
    assert out[1] == messages[1]


def test_render_creates_system_message_when_missing():
    driver = GenericXMLDriver()
    messages = [{"role": "user", "content": "hi"}]
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    out = driver.render_tools_into_messages(messages, tools)
    assert out[0]["role"] == "system"
    assert "TOOL PROTOCOL:" in out[0]["content"]


def test_render_with_no_tools_is_passthrough():
    driver = GenericXMLDriver()
    messages = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(messages, []) == messages


def test_parse_extracts_function_xml_format():
    driver = GenericXMLDriver()
    content = (
        '<function=read_file>'
        '<parameter=path>/tmp/x.txt</parameter>'
        '</function>'
    )
    calls = driver.parse_tool_calls(content, "")
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert '"path"' in calls[0].arguments
    assert "/tmp/x.txt" in calls[0].arguments


def test_parse_returns_empty_when_no_tool_call_present():
    driver = GenericXMLDriver()
    assert driver.parse_tool_calls("just narration", "just thinking") == []


def test_parse_falls_back_to_reasoning_payload():
    """Some models (deepseek-v3.2 in earlier tests) put the XML into the
    reasoning channel. The driver must check both."""
    driver = GenericXMLDriver()
    content = ""
    reasoning = '<function=run_shell><parameter=command>ls</parameter></function>'
    calls = driver.parse_tool_calls(content, reasoning)
    assert len(calls) == 1
    assert calls[0].name == "run_shell"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_generic_xml.py -v
```

Expected: `ModuleNotFoundError: No module named '...generic_xml'`.

- [ ] **Step 3: Implement `generic_xml.py`** — `src/ayder_cli/providers/impl/ollama_drivers/generic_xml.py`

```python
"""GenericXMLDriver — universal IN_CONTENT fallback.

Used as last-resort fallback for unknown families that don't have a tools
capability and don't match any matrix rule. Also used as fallback_driver
for the family-specific drivers when their primary path fails.

Prompt and parser are ported verbatim from ollama.py's XML_INSTRUCTION /
inject_xml_prompt / XMLParserAdapter (lines 57-101 and 393-420 in the
pre-Phase-1 codebase). Old code is deleted in Phase 3 once the new path
is the default.
"""
from __future__ import annotations

import json

from loguru import logger

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode


_XML_INSTRUCTION = """
### TOOL PROTOCOL:
You MUST use the specialized XML format for all tool calls. Failure to use this format will result in a parsing error.
Format:
<tool_call>
<function=tool_name>
<parameter=key1>value1</parameter>
</function>
</tool_call>

Available tools:
{tool_schemas}

The system will execute your tool calls and return the results within `<tool_results>` tags. Do NOT generate `<tool_results>` yourself. Wait for the system to provide the result before taking your next action.

CRITICAL RULES:
1. DO NOT use these XML tags (like <function=> or <parameter=>) in your prose, descriptions, or summaries. Only use them when you intend to call a tool.
2. If you have completed the task and output "Perfect!", you MUST NOT include any tool calls in the same response. "Perfect!" signifies the absolute end of your activity for that task.
3. Use only one tool call at a time unless the task clearly requires parallel execution of independent tools.
"""


class GenericXMLDriver(ChatDriver):
    name = "generic_xml"
    mode = DriverMode.IN_CONTENT
    priority = 950             # generic, never self-claims
    fallback_driver = None     # last resort — no further fallback
    supports_families = ()

    def render_tools_into_messages(self, messages, tools):
        if not tools:
            return messages

        try:
            tool_schemas_str = json.dumps(tools, indent=2)
        except Exception as e:
            logger.warning(f"Failed to serialize tool schemas: {e}; using str()")
            tool_schemas_str = str(tools)

        instruction = _XML_INSTRUCTION.format(tool_schemas=tool_schemas_str)
        out = list(messages)
        sys_idx = next(
            (i for i, m in enumerate(out) if m.get("role") == "system"),
            None,
        )
        if sys_idx is not None:
            new = dict(out[sys_idx])
            new["content"] = str(new.get("content", "")) + "\n" + instruction
            out[sys_idx] = new
        else:
            out.insert(0, {"role": "system", "content": instruction})
        return out

    def parse_tool_calls(self, content: str, reasoning: str) -> list[ToolCallDef]:
        """Reuse the project-wide content_processor. Tries content first,
        falls back to reasoning payload — same logic as the legacy
        XMLParserAdapter.get_tool_calls()."""
        calls = []
        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
        elif reasoning and content_processor.has_tool_calls(reasoning):
            calls = content_processor.parse_tool_calls(reasoning)
        elif json_calls := content_processor.parse_json_tool_calls(content):
            calls = json_calls

        return [
            ToolCallDef(
                id=f"call_{i}",
                name=c.get("name", "unknown"),
                arguments=json.dumps(c.get("arguments", {})),
            )
            for i, c in enumerate(calls)
        ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_generic_xml.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/generic_xml.py tests/providers/ollama_drivers/test_generic_xml.py
git commit -m "feat(ollama): add GenericXMLDriver as last-resort IN_CONTENT fallback"
```

---

### Task 8: `use_chat_drivers` config field

**Files:**
- Modify: `src/ayder_cli/core/config.py:278` (add new field next to `chat_protocol`)
- Test: `tests/core/test_config.py` (or create if absent)

- [ ] **Step 1: Write the failing test**

First, locate the existing config test file:

```bash
ls tests/core/ 2>/dev/null || ls tests/ | grep -i config
```

Append to `tests/core/test_config.py` (create if it doesn't exist):

```python
"""Tests for new config fields."""
from ayder_cli.core.config import Config


def test_use_chat_drivers_defaults_to_false():
    """During Phase 1-2 the new path is opt-in. Phase 3 flips this to True."""
    cfg = Config(driver="ollama", base_url="http://localhost:11434", model="x")
    assert cfg.use_chat_drivers is False


def test_use_chat_drivers_can_be_enabled():
    cfg = Config(
        driver="ollama",
        base_url="http://localhost:11434",
        model="x",
        use_chat_drivers=True,
    )
    assert cfg.use_chat_drivers is True
```

(If `Config` requires different mandatory fields, adjust the constructor call to match the existing pattern in the codebase. Check `tests/core/test_config.py` if present, or any test that constructs `Config`.)

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/core/test_config.py::test_use_chat_drivers_defaults_to_false -v
```

Expected: `pydantic.ValidationError` (extra field not permitted) OR `AttributeError`.

- [ ] **Step 3: Add the field to `Config`**

Open `src/ayder_cli/core/config.py`. Find line 278 (the existing `chat_protocol` declaration). Add immediately after it:

```python
    use_chat_drivers: bool = Field(
        default=False,
        description=(
            "When True, OllamaProvider routes through the per-family "
            "ChatDriver registry instead of the legacy regex-based XML "
            "fallback. Default False during Phase 1-2 of the chat-drivers "
            "migration; flipped True in Phase 3 and removed in Phase 4. "
            "See docs/superpowers/specs/2026-05-02-ollama-chat-drivers-design.md."
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/core/test_config.py -v
```

Expected: pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/core/config.py tests/core/test_config.py
git commit -m "feat(config): add use_chat_drivers feature flag"
```

---

### Task 9: Wire `OllamaProvider._stream_with_driver` behind the flag

**Files:**
- Modify: `src/ayder_cli/providers/impl/ollama.py:432-466` (constructor — add registry)
- Modify: `src/ayder_cli/providers/impl/ollama.py:468-543` (`stream_with_tools` — branch on flag)
- Test: `tests/providers/ollama_drivers/test_provider_integration.py`

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_provider_integration.py`

```python
"""Integration tests: OllamaProvider routes through DriverRegistry when
use_chat_drivers=True."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ayder_cli.providers.impl.ollama import OllamaProvider


def _config(model: str, use_chat_drivers: bool, chat_protocol: str = "ollama"):
    cfg = MagicMock()
    cfg.base_url = "http://localhost:11434"
    cfg.api_key = ""
    cfg.model = model
    cfg.chat_protocol = chat_protocol
    cfg.use_chat_drivers = use_chat_drivers
    return cfg


def _mock_chunk(content="", thinking="", done=False, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.thinking = thinking
    msg.tool_calls = tool_calls or []
    resp = MagicMock()
    resp.message = msg
    resp.done = done
    resp.prompt_eval_count = 5 if done else None
    resp.prompt_eval_duration = 100 if done else None
    resp.eval_count = 3 if done else None
    resp.eval_duration = 50 if done else None
    resp.load_duration = 0 if done else None
    return resp


@pytest.mark.asyncio
async def test_provider_uses_legacy_path_when_flag_is_false():
    """use_chat_drivers=False keeps the existing XML autoroute behavior."""
    cfg = _config("qwen3.6:latest", use_chat_drivers=False)

    captured_kwargs: dict = {}

    async def fake_stream():
        yield _mock_chunk(content="ok", done=True)

    async def fake_chat(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_stream()

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.side_effect = fake_chat
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        async for _ in provider.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            model="qwen3.6:latest",
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        ):
            pass

    # Legacy path: tools=None (XML fallback for qwen3 via regex)
    assert captured_kwargs.get("tools") is None


@pytest.mark.asyncio
async def test_provider_uses_driver_path_when_flag_is_true():
    """use_chat_drivers=True routes through DriverRegistry. For llama family
    (NATIVE), tools=[...] is forwarded to Ollama."""
    cfg = _config("llama3.1:8b", use_chat_drivers=True)

    captured_kwargs: dict = {}

    async def fake_stream():
        yield _mock_chunk(content="ok", done=True)

    async def fake_chat(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_stream()

    fake_show = MagicMock(
        modelinfo={"llama.context_length": 32768},
        capabilities=["tools"],
        details=MagicMock(family="llama", quantization_level="Q4_K_M"),
    )

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.side_effect = fake_chat
        instance.show = AsyncMock(return_value=fake_show)
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        async for _ in provider.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            model="llama3.1:8b",
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        ):
            pass

    assert captured_kwargs.get("tools") is not None  # NATIVE path forwards tools
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_provider_integration.py -v
```

Expected: 2nd test fails because the new path doesn't exist yet.

- [ ] **Step 3: Modify `OllamaProvider`**

In `src/ayder_cli/providers/impl/ollama.py`:

**3a. Add imports near the top of the file** (after existing imports):

```python
from ayder_cli.providers.impl.ollama_drivers._errors import (
    OllamaServerToolBug,
    classify_ollama_error,
)
from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.registry import DriverRegistry
from ayder_cli.providers.impl.ollama_inspector import OllamaInspector
```

**3b. Modify the constructor** at line ~432 (`def __init__`) — add `_registry` initialization at the end of `__init__`:

```python
    def __init__(self, config: Any, interaction_sink: Any = None) -> None:
        super().__init__(config, interaction_sink)
        self.config = config
        host = getattr(config, "base_url", "http://localhost:11434")
        # Strip /v1 suffix if present (legacy config)
        if host.rstrip("/").endswith("/v1"):
            host = host.rstrip("/")[:-3]
        self._client = AsyncClient(host=host)
        # Lazy DriverRegistry — instantiated on first use when the flag is on.
        self._registry: DriverRegistry | None = None
```

**3c. Replace the body of `stream_with_tools`** (lines 468-549) with:

```python
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        if getattr(self.config, "use_chat_drivers", False):
            async for chunk in self._stream_via_drivers(
                messages, model, tools, options, verbose
            ):
                yield chunk
            return

        # ── LEGACY PATH (deleted in Phase 3) ─────────────────────────────
        async for chunk in self._stream_legacy(
            messages, model, tools, options, verbose
        ):
            yield chunk
```

**3d. Rename the existing body of `stream_with_tools`** to a private helper. Locate the original body (lines 476-549, starting with `opts = options or {}`) and rename it `_stream_legacy`:

```python
    async def _stream_legacy(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        verbose: bool,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        """Pre-Phase-1 implementation. Will be deleted in Phase 3."""
        opts = options or {}
        num_ctx = opts.get("num_ctx", 65536)

        use_xml_fallback = self.config.chat_protocol != "ollama"
        if not use_xml_fallback and _requires_xml_fallback(model):
            use_xml_fallback = True
            logger.info(
                f"Ollama auto-routing to XML fallback for model={model!r} "
                f"(family emits XML tool calls inside msg.content)"
            )

        if use_xml_fallback:
            if self.config.chat_protocol != "ollama":
                logger.info(
                    f"Ollama using XML fallback protocol "
                    f"(chat_protocol={self.config.chat_protocol!r})"
                )
            async for chunk in self._stream_xml_fallback(
                messages, model, tools, opts, verbose
            ):
                yield chunk
            return

        # … (rest of the original body — native path with msg.tool_calls) …
        ollama_tools = self._convert_tools(tools) if tools else None
        ollama_messages = self._convert_messages(messages)

        stream = await self._client.chat(
            model=model,
            messages=ollama_messages,
            tools=ollama_tools,
            options={"num_ctx": num_ctx},
            keep_alive=-1,
            think=True,
            stream=True,
        )

        async for chunk in stream:
            msg = chunk.message
            usage = None

            if chunk.done:
                usage = {
                    "total_tokens": (chunk.prompt_eval_count or 0) + (chunk.eval_count or 0),
                    "prompt_tokens": chunk.prompt_eval_count or 0,
                    "completion_tokens": chunk.eval_count or 0,
                    "prompt_eval_ns": chunk.prompt_eval_duration or 0,
                    "eval_ns": chunk.eval_duration or 0,
                    "load_ns": chunk.load_duration or 0,
                }

            tool_calls = []
            if msg.tool_calls:
                for i, tc in enumerate(msg.tool_calls):
                    args = tc.function.arguments
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    tool_calls.append(ToolCallDef(
                        id=f"call_{i}",
                        name=tc.function.name,
                        arguments=args,
                    ))

            yield NormalizedStreamChunk(
                content=msg.content or "",
                reasoning=msg.thinking or "",
                tool_calls=tool_calls,
                raw_chunk=chunk,
                usage=usage,
            )
```

**3e. Add the new driver-routed path**:

```python
    async def _stream_via_drivers(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        verbose: bool,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        if self._registry is None:
            inspector = OllamaInspector(host=self._client._client.base_url.host)
            self._registry = DriverRegistry(inspector)

        override = (
            self.config.chat_protocol
            if self.config.chat_protocol in ("xml",)  # only "xml" forces a driver today
            else None
        )
        driver_override_name = "generic_xml" if override == "xml" else None

        driver = await self._registry.resolve(model, override=driver_override_name)
        logger.debug(
            f"Ollama driver={driver.name} mode={driver.mode.value} for {model!r}"
        )

        committed = False
        try:
            async for chunk in self._stream_with_driver(
                driver, messages, model, tools, options
            ):
                if chunk.content or chunk.reasoning or chunk.tool_calls:
                    committed = True
                yield chunk
        except OllamaServerToolBug as exc:
            if committed or not driver.fallback_driver:
                raise
            fallback = self._registry.get(driver.fallback_driver)
            logger.info(
                f"{driver.name} ({driver.mode.value}) failed mid-stream: {exc!r}; "
                f"transparently retrying with {fallback.name} "
                f"({fallback.mode.value})"
            )
            async for chunk in self._stream_with_driver(
                fallback, messages, model, tools, options
            ):
                yield chunk

    async def _stream_with_driver(
        self,
        driver,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        try:
            if driver.mode is DriverMode.NATIVE:
                async for chunk in self._stream_native(
                    messages, model, tools, options
                ):
                    yield chunk
            else:
                async for chunk in self._stream_in_content(
                    driver, messages, model, tools, options
                ):
                    yield chunk
        except BaseException as exc:
            classified = classify_ollama_error(exc)
            if classified is exc:
                raise
            raise classified from exc

    async def _stream_native(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        opts = options or {}
        num_ctx = opts.get("num_ctx", 65536)
        ollama_tools = self._convert_tools(tools) if tools else None
        ollama_messages = self._convert_messages(messages)

        stream = await self._client.chat(
            model=model,
            messages=ollama_messages,
            tools=ollama_tools,
            options={"num_ctx": num_ctx},
            keep_alive=-1,
            think=True,
            stream=True,
        )

        async for chunk in stream:
            msg = chunk.message
            usage = None
            if chunk.done:
                usage = {
                    "total_tokens": (chunk.prompt_eval_count or 0) + (chunk.eval_count or 0),
                    "prompt_tokens": chunk.prompt_eval_count or 0,
                    "completion_tokens": chunk.eval_count or 0,
                    "prompt_eval_ns": chunk.prompt_eval_duration or 0,
                    "eval_ns": chunk.eval_duration or 0,
                    "load_ns": chunk.load_duration or 0,
                }
            tool_calls = []
            if msg.tool_calls:
                for i, tc in enumerate(msg.tool_calls):
                    args = tc.function.arguments
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    tool_calls.append(ToolCallDef(
                        id=f"call_{i}",
                        name=tc.function.name,
                        arguments=args,
                    ))
            yield NormalizedStreamChunk(
                content=msg.content or "",
                reasoning=msg.thinking or "",
                tool_calls=tool_calls,
                raw_chunk=chunk,
                usage=usage,
            )

    async def _stream_in_content(
        self,
        driver,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        opts = options or {}
        num_ctx = opts.get("num_ctx", 65536)
        formatted = driver.render_tools_into_messages(messages, tools or [])
        ollama_messages = self._convert_messages(formatted)

        stream = await self._client.chat(
            model=model,
            messages=ollama_messages,
            tools=None,
            options={"num_ctx": num_ctx},
            keep_alive=-1,
            think=True,
            stream=True,
        )

        raw_content = ""
        raw_thinking = ""
        display_filter = driver.display_filter()

        async for chunk in stream:
            msg = chunk.message
            content_text = msg.content or ""
            thinking_text = msg.thinking or ""
            raw_content += content_text
            raw_thinking += thinking_text

            usage = None
            if chunk.done:
                usage = {
                    "total_tokens": (chunk.prompt_eval_count or 0) + (chunk.eval_count or 0),
                    "prompt_tokens": chunk.prompt_eval_count or 0,
                    "completion_tokens": chunk.eval_count or 0,
                    "prompt_eval_ns": chunk.prompt_eval_duration or 0,
                    "eval_ns": chunk.eval_duration or 0,
                    "load_ns": chunk.load_duration or 0,
                }

            if content_text or thinking_text or chunk.done:
                if display_filter is not None:
                    visible_content, visible_thinking = display_filter.feed(
                        content_text, thinking_text
                    )
                else:
                    visible_content = content_text
                    visible_thinking = thinking_text

                yield NormalizedStreamChunk(
                    content=visible_content,
                    reasoning=visible_thinking,
                    tool_calls=[],
                    raw_chunk=chunk,
                    usage=usage,
                )

        final_calls = driver.parse_tool_calls(raw_content, raw_thinking)
        if final_calls:
            yield NormalizedStreamChunk(tool_calls=final_calls)
```

- [ ] **Step 4: Run integration tests**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_provider_integration.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green. Legacy path unchanged for `use_chat_drivers=False`.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama.py tests/providers/ollama_drivers/test_provider_integration.py
git commit -m "feat(ollama): wire DriverRegistry behind use_chat_drivers flag"
```

---

## Phase 2 — Family Drivers (Tasks 10-12)

Each family driver lives in its own file with a paired test file. Adding a family is one driver + one test, no edits to the registry or other drivers.

---

### Task 10: `Qwen3Driver`

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/qwen3.py`
- Create: `tests/providers/ollama_drivers/test_qwen3.py`

The qwen3 prompt template uses qwen3's own training format (`<tools>...</tools>` + `<tool_call>{json}</tool_call>`) per the Qwen3 model card. The parser handles both qwen3-trained JSON-in-tool_call AND the generic `<function=>` format (for custom-trained variants that mix formats).

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_qwen3.py`

```python
"""Tests for Qwen3Driver — qwen3-trained prompt + parser."""
from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.qwen3 import Qwen3Driver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_qwen3_metadata():
    assert Qwen3Driver.name == "qwen3"
    assert Qwen3Driver.mode is DriverMode.IN_CONTENT
    assert Qwen3Driver.fallback_driver == "generic_xml"
    assert Qwen3Driver.priority < 100  # specific, runs before generics
    assert "qwen3" in Qwen3Driver.supports_families


def test_qwen3_supports_via_default_family_match():
    assert Qwen3Driver.supports(ModelInfo(family="qwen3"))
    assert Qwen3Driver.supports(ModelInfo(family="qwen2"))  # same training format
    assert not Qwen3Driver.supports(ModelInfo(family="llama"))


def test_qwen3_render_injects_qwen_native_format():
    driver = Qwen3Driver()
    messages = [{"role": "system", "content": "base"}, {"role": "user", "content": "hi"}]
    tools = [{"type": "function", "function": {"name": "read_file",
              "description": "Reads a file", "parameters": {"type": "object"}}}]
    out = driver.render_tools_into_messages(messages, tools)

    sys = out[0]["content"]
    # Qwen3-trained format markers
    assert "<tools>" in sys
    assert "</tools>" in sys
    assert "<tool_call>" in sys
    assert "</tool_call>" in sys
    # Tool schema is included verbatim (JSON)
    assert "read_file" in sys
    # Tail message preserved
    assert out[1] == messages[1]


def test_qwen3_render_with_no_tools_is_passthrough():
    driver = Qwen3Driver()
    messages = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(messages, []) == messages


def test_qwen3_parse_extracts_qwen_json_format():
    """The qwen3-trained format: <tool_call>{"name":..., "arguments":{...}}</tool_call>."""
    driver = Qwen3Driver()
    content = (
        '<tool_call>\n'
        '{"name": "read_file", "arguments": {"path": "/tmp/x.txt"}}\n'
        '</tool_call>'
    )
    calls = driver.parse_tool_calls(content, "")
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    import json as _json
    assert _json.loads(calls[0].arguments) == {"path": "/tmp/x.txt"}


def test_qwen3_parse_handles_string_arguments():
    """Some qwen variants emit `arguments` as a JSON-encoded string."""
    driver = Qwen3Driver()
    content = (
        '<tool_call>'
        '{"name": "shell", "arguments": "{\\"cmd\\": \\"ls\\"}"}'
        '</tool_call>'
    )
    calls = driver.parse_tool_calls(content, "")
    assert len(calls) == 1
    import json as _json
    assert _json.loads(calls[0].arguments) == {"cmd": "ls"}


def test_qwen3_parse_extracts_multiple_calls():
    driver = Qwen3Driver()
    content = (
        '<tool_call>{"name": "a", "arguments": {}}</tool_call>'
        'mid prose '
        '<tool_call>{"name": "b", "arguments": {"k": "v"}}</tool_call>'
    )
    calls = driver.parse_tool_calls(content, "")
    assert [c.name for c in calls] == ["a", "b"]


def test_qwen3_parse_falls_back_to_function_xml_format():
    """If the model emits <function=> format (custom-trained variant),
    we still parse it via the generic XML path."""
    driver = Qwen3Driver()
    content = '<function=read_file><parameter=path>/tmp</parameter></function>'
    calls = driver.parse_tool_calls(content, "")
    assert len(calls) == 1
    assert calls[0].name == "read_file"


def test_qwen3_parse_returns_empty_for_pure_narration():
    driver = Qwen3Driver()
    assert driver.parse_tool_calls("I'll read the file.", "thinking...") == []


def test_qwen3_parse_skips_malformed_json():
    driver = Qwen3Driver()
    content = '<tool_call>{not valid json}</tool_call>'
    assert driver.parse_tool_calls(content, "") == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_qwen3.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `qwen3.py`** — `src/ayder_cli/providers/impl/ollama_drivers/qwen3.py`

```python
"""Qwen3Driver — uses qwen3's trained tool-call format.

Qwen3 is fine-tuned to emit tool calls as:
    <tool_call>
    {"name": "function_name", "arguments": {...}}
    </tool_call>

This driver renders tools using qwen3's training-time system prompt
template (see https://huggingface.co/Qwen/Qwen3-7B-Instruct) so the
model sees the format it was trained on. The parser also accepts the
generic <function=> XML format as a fallback for custom-trained
variants that mix formats.

Why IN_CONTENT not NATIVE: Ollama's server-side tool extractor for
qwen3 crashes mid-stream on truncated XML output (Ollama issue #14834).
This driver bypasses the broken extractor by sending tools=None and
parsing the model's natural output client-side.
"""
from __future__ import annotations

import json
import re

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode


_QWEN3_INSTRUCTION = """

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tool_schemas}
</tools>

For each function call, return a json object with function name and arguments
within <tool_call></tool_call> XML tags:
<tool_call>
{{"name": <function-name>, "arguments": <args-json-object>}}
</tool_call>
"""


class Qwen3Driver(ChatDriver):
    name = "qwen3"
    mode = DriverMode.IN_CONTENT
    priority = 50              # specific, beats generics
    fallback_driver = "generic_xml"
    supports_families = ("qwen2", "qwen3")

    _RE_TOOL_CALL_JSON = re.compile(
        r"<(?:\w+:)?tool_call>\s*(\{.*?\})\s*</(?:\w+:)?tool_call>",
        re.DOTALL,
    )

    def render_tools_into_messages(self, messages, tools):
        if not tools:
            return messages
        # Schemas one-per-line per qwen3 training convention.
        schemas = "\n".join(json.dumps(t, ensure_ascii=False) for t in tools)
        instruction = _QWEN3_INSTRUCTION.format(tool_schemas=schemas)
        out = list(messages)
        sys_idx = next(
            (i for i, m in enumerate(out) if m.get("role") == "system"),
            None,
        )
        if sys_idx is not None:
            new = dict(out[sys_idx])
            new["content"] = str(new.get("content", "")) + instruction
            out[sys_idx] = new
        else:
            out.insert(0, {"role": "system", "content": instruction.lstrip()})
        return out

    def parse_tool_calls(self, content: str, reasoning: str) -> list[ToolCallDef]:
        # 1. Try qwen3-trained JSON-in-tool_call format
        calls = self._parse_json_in_tool_call(content)
        if not calls:
            calls = self._parse_json_in_tool_call(reasoning)

        # 2. Fall back to generic <function=> XML (custom-trained variants)
        if not calls and content and content_processor.has_tool_calls(content):
            generic = content_processor.parse_tool_calls(content)
            calls = [
                {"name": c.get("name", "unknown"),
                 "arguments": c.get("arguments", {})}
                for c in generic if c.get("name")
            ]

        if not calls and reasoning and content_processor.has_tool_calls(reasoning):
            generic = content_processor.parse_tool_calls(reasoning)
            calls = [
                {"name": c.get("name", "unknown"),
                 "arguments": c.get("arguments", {})}
                for c in generic if c.get("name")
            ]

        return [
            ToolCallDef(
                id=f"call_{i}",
                name=c["name"],
                arguments=json.dumps(c["arguments"], ensure_ascii=False),
            )
            for i, c in enumerate(calls)
        ]

    def _parse_json_in_tool_call(self, text: str) -> list[dict]:
        if not text:
            return []
        results = []
        for match in self._RE_TOOL_CALL_JSON.finditer(text):
            raw = match.group(1)
            try:
                obj = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            name = obj.get("name")
            if not name:
                continue
            args = obj.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {}
            if not isinstance(args, dict):
                args = {}
            results.append({"name": name, "arguments": args})
        return results
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_qwen3.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Verify auto-discovery picked up the new driver**

```bash
.venv/bin/python3 -c "
from ayder_cli.providers.impl.ollama_drivers.registry import DriverRegistry
from unittest.mock import AsyncMock
r = DriverRegistry(AsyncMock())
print(sorted(r._by_name.keys()))
"
```

Expected output includes `'qwen3'`, `'generic_native'`, `'generic_xml'`.

- [ ] **Step 6: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/qwen3.py tests/providers/ollama_drivers/test_qwen3.py
git commit -m "feat(ollama): add Qwen3Driver with qwen3-trained format"
```

---

### Task 11: `DeepSeekDriver`

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/deepseek.py`
- Create: `tests/providers/ollama_drivers/test_deepseek.py`

DeepSeek emits `<function_calls><invoke name="...">...</invoke></function_calls>` in `msg.content`. The existing `content_processor` already handles this format (`_RE_INVOKE`, `_RE_DS_PARAM`, `_convert_deepseek`). The driver wraps that machinery.

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_deepseek.py`

```python
"""Tests for DeepSeekDriver."""
from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.deepseek import DeepSeekDriver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_deepseek_metadata():
    assert DeepSeekDriver.name == "deepseek"
    assert DeepSeekDriver.mode is DriverMode.IN_CONTENT
    assert DeepSeekDriver.fallback_driver == "generic_xml"
    assert DeepSeekDriver.priority < 100


def test_deepseek_supports_v2_and_v3_families():
    assert DeepSeekDriver.supports(ModelInfo(family="deepseek2"))
    assert DeepSeekDriver.supports(ModelInfo(family="deepseek3"))
    assert DeepSeekDriver.supports(ModelInfo(family="deepseek-coder"))
    assert not DeepSeekDriver.supports(ModelInfo(family="llama"))


def test_deepseek_render_injects_function_calls_format():
    driver = DeepSeekDriver()
    messages = [{"role": "system", "content": "base"}]
    tools = [{"type": "function", "function": {"name": "read_file",
              "description": "Read", "parameters": {}}}]
    out = driver.render_tools_into_messages(messages, tools)
    sys = out[0]["content"]
    assert "<function_calls>" in sys
    assert "<invoke" in sys
    assert "<parameter" in sys
    assert "read_file" in sys


def test_deepseek_parse_extracts_invoke_format():
    driver = DeepSeekDriver()
    content = (
        '<function_calls>'
        '<invoke name="read_file">'
        '<parameter name="path">/tmp/x</parameter>'
        '</invoke>'
        '</function_calls>'
    )
    calls = driver.parse_tool_calls(content, "")
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    import json as _json
    assert _json.loads(calls[0].arguments) == {"path": "/tmp/x"}


def test_deepseek_parse_falls_back_to_reasoning():
    """deepseek-v3.2 sometimes emits the XML in the reasoning channel."""
    driver = DeepSeekDriver()
    content = ""
    reasoning = (
        '<function_calls>'
        '<invoke name="run_shell">'
        '<parameter name="command">ls</parameter>'
        '</invoke>'
        '</function_calls>'
    )
    calls = driver.parse_tool_calls(content, reasoning)
    assert len(calls) == 1
    assert calls[0].name == "run_shell"


def test_deepseek_parse_returns_empty_when_absent():
    driver = DeepSeekDriver()
    assert driver.parse_tool_calls("plain text", "thinking") == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_deepseek.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `deepseek.py`** — `src/ayder_cli/providers/impl/ollama_drivers/deepseek.py`

```python
"""DeepSeekDriver — handles deepseek-r1, deepseek-v3, deepseek-coder.

DeepSeek models (r1, v3, coder) emit tool calls inside msg.content using
the format:
    <function_calls>
    <invoke name="tool_name">
    <parameter name="key">value</parameter>
    </invoke>
    </function_calls>

Their msg.tool_calls is always empty regardless of Ollama's tools=[...]
parameter — this is a model behavior, not an Ollama bug. The existing
content_processor already handles this format; this driver wraps it.
"""
from __future__ import annotations

import json

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode


_DEEPSEEK_INSTRUCTION = """

# Tools

You can call the following tools to help with the user's request.

Available tools:
<tools>
{tool_schemas}
</tools>

To invoke a tool, output a function_calls block:
<function_calls>
<invoke name="tool_name">
<parameter name="key">value</parameter>
</invoke>
</function_calls>

The system will execute the call and return the result. Wait for the result
before continuing.
"""


class DeepSeekDriver(ChatDriver):
    name = "deepseek"
    mode = DriverMode.IN_CONTENT
    priority = 50
    fallback_driver = "generic_xml"
    supports_families = ("deepseek",)

    def render_tools_into_messages(self, messages, tools):
        if not tools:
            return messages
        schemas = json.dumps(tools, indent=2, ensure_ascii=False)
        instruction = _DEEPSEEK_INSTRUCTION.format(tool_schemas=schemas)
        out = list(messages)
        sys_idx = next(
            (i for i, m in enumerate(out) if m.get("role") == "system"),
            None,
        )
        if sys_idx is not None:
            new = dict(out[sys_idx])
            new["content"] = str(new.get("content", "")) + instruction
            out[sys_idx] = new
        else:
            out.insert(0, {"role": "system", "content": instruction.lstrip()})
        return out

    def parse_tool_calls(self, content: str, reasoning: str) -> list[ToolCallDef]:
        calls = []
        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
        elif reasoning and content_processor.has_tool_calls(reasoning):
            calls = content_processor.parse_tool_calls(reasoning)

        return [
            ToolCallDef(
                id=f"call_{i}",
                name=c.get("name", "unknown"),
                arguments=json.dumps(c.get("arguments", {}), ensure_ascii=False),
            )
            for i, c in enumerate(calls)
            if c.get("name")
        ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_deepseek.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/deepseek.py tests/providers/ollama_drivers/test_deepseek.py
git commit -m "feat(ollama): add DeepSeekDriver"
```

---

### Task 12: `MiniMaxDriver`

**Files:**
- Create: `src/ayder_cli/providers/impl/ollama_drivers/minimax.py`
- Create: `tests/providers/ollama_drivers/test_minimax.py`

MiniMax-M1 uses namespaced `<minimax:tool_call>` tags. The existing parser supports this via `_RE_TOOL_CALL_WRAPPER` and the namespace-aware regexes.

- [ ] **Step 1: Write the failing test** — `tests/providers/ollama_drivers/test_minimax.py`

```python
"""Tests for MiniMaxDriver."""
from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.minimax import MiniMaxDriver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_minimax_metadata():
    assert MiniMaxDriver.name == "minimax"
    assert MiniMaxDriver.mode is DriverMode.IN_CONTENT
    assert MiniMaxDriver.fallback_driver == "generic_xml"
    assert MiniMaxDriver.priority < 100


def test_minimax_supports_minimax_family():
    assert MiniMaxDriver.supports(ModelInfo(family="minimax"))
    assert MiniMaxDriver.supports(ModelInfo(family="minimax-m1"))
    assert not MiniMaxDriver.supports(ModelInfo(family="qwen3"))


def test_minimax_render_injects_namespaced_format():
    driver = MiniMaxDriver()
    messages = [{"role": "system", "content": "base"}]
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    out = driver.render_tools_into_messages(messages, tools)
    sys = out[0]["content"]
    assert "<minimax:tool_call>" in sys
    assert "read_file" in sys


def test_minimax_parse_extracts_namespaced_format():
    driver = MiniMaxDriver()
    content = (
        '<minimax:tool_call>'
        '<function=read_file><parameter=path>/tmp</parameter></function>'
        '</minimax:tool_call>'
    )
    calls = driver.parse_tool_calls(content, "")
    assert len(calls) == 1
    assert calls[0].name == "read_file"


def test_minimax_parse_returns_empty_when_absent():
    driver = MiniMaxDriver()
    assert driver.parse_tool_calls("plain text", "") == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_minimax.py -v
```

- [ ] **Step 3: Implement `minimax.py`** — `src/ayder_cli/providers/impl/ollama_drivers/minimax.py`

```python
"""MiniMaxDriver — handles MiniMax-M1 with namespaced <minimax:tool_call> tags."""
from __future__ import annotations

import json

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode


_MINIMAX_INSTRUCTION = """

# Tools

Available tools:
<tools>
{tool_schemas}
</tools>

To call a tool, wrap the call in <minimax:tool_call> tags using the
function/parameter format:
<minimax:tool_call>
<function=tool_name>
<parameter=key>value</parameter>
</function>
</minimax:tool_call>
"""


class MiniMaxDriver(ChatDriver):
    name = "minimax"
    mode = DriverMode.IN_CONTENT
    priority = 50
    fallback_driver = "generic_xml"
    supports_families = ("minimax",)

    def render_tools_into_messages(self, messages, tools):
        if not tools:
            return messages
        schemas = json.dumps(tools, indent=2, ensure_ascii=False)
        instruction = _MINIMAX_INSTRUCTION.format(tool_schemas=schemas)
        out = list(messages)
        sys_idx = next(
            (i for i, m in enumerate(out) if m.get("role") == "system"),
            None,
        )
        if sys_idx is not None:
            new = dict(out[sys_idx])
            new["content"] = str(new.get("content", "")) + instruction
            out[sys_idx] = new
        else:
            out.insert(0, {"role": "system", "content": instruction.lstrip()})
        return out

    def parse_tool_calls(self, content: str, reasoning: str) -> list[ToolCallDef]:
        calls = []
        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
        elif reasoning and content_processor.has_tool_calls(reasoning):
            calls = content_processor.parse_tool_calls(reasoning)

        return [
            ToolCallDef(
                id=f"call_{i}",
                name=c.get("name", "unknown"),
                arguments=json.dumps(c.get("arguments", {}), ensure_ascii=False),
            )
            for i, c in enumerate(calls)
            if c.get("name")
        ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_minimax.py -v
```

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama_drivers/minimax.py tests/providers/ollama_drivers/test_minimax.py
git commit -m "feat(ollama): add MiniMaxDriver"
```

---

### Task 12.5: Reactive fallback test

**Files:**
- Create: `tests/providers/ollama_drivers/test_fallback.py`

Validates that the fallback path engages on `OllamaServerToolBug` only when uncommitted.

- [ ] **Step 1: Write the test**

```python
"""Tests for reactive fallback when a driver raises OllamaServerToolBug."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ollama import ResponseError

from ayder_cli.providers.impl.ollama import OllamaProvider


def _config():
    cfg = MagicMock()
    cfg.base_url = "http://localhost:11434"
    cfg.api_key = ""
    cfg.chat_protocol = "ollama"
    cfg.use_chat_drivers = True
    return cfg


def _mock_chunk(content="", done=False, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.thinking = ""
    msg.tool_calls = tool_calls or []
    resp = MagicMock()
    resp.message = msg
    resp.done = done
    resp.prompt_eval_count = 0
    resp.prompt_eval_duration = 0
    resp.eval_count = 0
    resp.eval_duration = 0
    resp.load_duration = 0
    return resp


def _show(family: str = "qwen3"):
    return MagicMock(
        modelinfo={"qwen3.context_length": 32768},
        capabilities=["tools"],
        details=MagicMock(family=family, quantization_level="Q4"),
    )


@pytest.mark.asyncio
async def test_fallback_engages_when_uncommitted_xml_error():
    """Server emits the bug error before any chunk → fallback runs."""
    cfg = _config()
    call_count = {"chat": 0}

    async def _fail_then_succeed(*args, **kwargs):
        call_count["chat"] += 1
        if call_count["chat"] == 1:
            async def boom():
                raise ResponseError("XML syntax error on line 43: unexpected EOF")
                yield  # unreachable, makes this an async generator
            return boom()

        async def ok():
            yield _mock_chunk(content="recovered", done=True)
        return ok()

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.side_effect = _fail_then_succeed
        instance.show = AsyncMock(return_value=_show())
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        chunks = []
        async for chunk in provider.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            model="qwen3.6:latest",
            tools=[{"type": "function", "function": {"name": "x"}}],
        ):
            chunks.append(chunk)

    assert call_count["chat"] == 2  # primary + fallback
    assert any("recovered" in c.content for c in chunks)


@pytest.mark.asyncio
async def test_fallback_does_not_engage_after_committed_chunk():
    """Once content has streamed, the bug propagates."""
    cfg = _config()

    async def stream_then_fail(*args, **kwargs):
        async def gen():
            yield _mock_chunk(content="committed text")
            raise ResponseError("XML syntax error: unexpected EOF")
        return gen()

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.side_effect = stream_then_fail
        instance.show = AsyncMock(return_value=_show())
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        chunks = []
        with pytest.raises(Exception):  # OllamaServerToolBug propagates
            async for chunk in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3.6:latest",
                tools=[{"type": "function", "function": {"name": "x"}}],
            ):
                chunks.append(chunk)

    assert any("committed" in c.content for c in chunks)


@pytest.mark.asyncio
async def test_fallback_does_not_engage_on_non_tool_bug_error():
    """A 5xx / connection error is NOT classified as the tool bug;
    the retry layer above OllamaProvider handles those."""
    cfg = _config()

    async def boom(*args, **kwargs):
        async def g():
            raise ResponseError("internal server error")
            yield
        return g()

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.side_effect = boom
        instance.show = AsyncMock(return_value=_show())
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        with pytest.raises(ResponseError):
            async for _ in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3.6:latest",
                tools=[{"type": "function", "function": {"name": "x"}}],
            ):
                pass
```

- [ ] **Step 2: Run test**

```bash
.venv/bin/python3 -m pytest tests/providers/ollama_drivers/test_fallback.py -v
```

Expected: all 3 tests pass against the implementation from Task 9.

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 4: Commit**

```bash
git add tests/providers/ollama_drivers/test_fallback.py
git commit -m "test(ollama): reactive fallback on classified tool bug"
```

---

## Phase 3 — Cutover (Tasks 13-16)

Flip the default, retarget the legacy autoroute test, then delete the legacy code paths.

---

### Task 13: Flip `use_chat_drivers` default to `True` + retarget autoroute test

**Files:**
- Modify: `src/ayder_cli/core/config.py` (the `use_chat_drivers` field)
- Modify: `tests/providers/test_ollama_xml_autoroute.py`
- Modify: `tests/core/test_config.py`

- [ ] **Step 1: Update config field default**

In `src/ayder_cli/core/config.py`, change `use_chat_drivers` default to `True`:

```python
    use_chat_drivers: bool = Field(
        default=True,
        description=(
            "Routes OllamaProvider through the per-family ChatDriver "
            "registry. Disable to fall back to the legacy regex-based XML "
            "fallback (slated for removal). "
            "See docs/superpowers/specs/2026-05-02-ollama-chat-drivers-design.md."
        ),
    )
```

- [ ] **Step 2: Update the config test**

In `tests/core/test_config.py`:

```python
def test_use_chat_drivers_defaults_to_true():
    cfg = Config(driver="ollama", base_url="http://localhost:11434", model="x")
    assert cfg.use_chat_drivers is True
```

(Replace the previous `defaults_to_false` test.)

- [ ] **Step 3: Retarget the legacy autoroute test**

The current `tests/providers/test_ollama_xml_autoroute.py` asserts that `_requires_xml_fallback("qwen3.6")` returns `True`. After cutover the regex no longer exists; the assertion moves to the matrix.

Replace the file body with:

```python
"""Routing assertions for the ChatDriver-based path. The legacy regex
function _requires_xml_fallback is removed in this phase; routing is now
verified via the matrix tests."""
import pytest

from ayder_cli.providers.impl.ollama_drivers.matrix import RESOLUTION_MATRIX
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


@pytest.mark.parametrize("model_info, expected_driver", [
    (ModelInfo(name="deepseek-r1:32b", family="deepseek2"), "deepseek"),
    (ModelInfo(name="deepseek-v3.2",   family="deepseek3"), "deepseek"),
    (ModelInfo(name="qwen3.6:latest",  family="qwen3"),     "qwen3"),
    (ModelInfo(name="qwen2.5:7b",      family="qwen2"),     "qwen3"),
    (ModelInfo(name="minimax-m1",      family="minimax"),   "minimax"),
    (ModelInfo(name="llama3.1:8b",     family="llama"),     "generic_native"),
])
def test_legacy_autoroute_models_now_route_via_matrix(model_info, expected_driver):
    rule = next(
        (r for r in RESOLUTION_MATRIX if r.matches(model_info)),
        None,
    )
    assert rule is not None
    assert rule.driver == expected_driver
```

- [ ] **Step 4: Run tests to verify**

```bash
.venv/bin/python3 -m pytest tests/core/test_config.py tests/providers/test_ollama_xml_autoroute.py -v
```

Expected: all green.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green. Legacy path is now disabled by default but still callable when `use_chat_drivers=False` is explicitly set.

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/core/config.py tests/core/test_config.py tests/providers/test_ollama_xml_autoroute.py
git commit -m "feat(ollama): flip use_chat_drivers default to True"
```

---

### Task 14: Delete `_MODEL_REQUIRES_XML_FALLBACK_*` and `_requires_xml_fallback`

**Files:**
- Modify: `src/ayder_cli/providers/impl/ollama.py` (remove lines 20-55)

- [ ] **Step 1: Remove the regex routing block**

Open `src/ayder_cli/providers/impl/ollama.py`. Delete lines 20-55 (the entire regex routing block: `_MODEL_REQUIRES_XML_FALLBACK_PATTERNS`, `_MODEL_REQUIRES_XML_FALLBACK_RE`, `_requires_xml_fallback`):

Locate this block and delete it entirely:

```python
# Model families whose Ollama integration emits tool calls as XML text inside
# msg.content rather than through the native msg.tool_calls channel. For these
# models, stream_with_tools routes through _stream_xml_fallback even when the
# user has the default chat_protocol="ollama".
#
# ... (full comment block) ...
_MODEL_REQUIRES_XML_FALLBACK_PATTERNS: tuple[str, ...] = (
    r"deepseek-r1",
    ...
)

_MODEL_REQUIRES_XML_FALLBACK_RE = _re.compile(
    "|".join(_MODEL_REQUIRES_XML_FALLBACK_PATTERNS),
    _re.IGNORECASE,
)


def _requires_xml_fallback(model: str) -> bool:
    ...
```

- [ ] **Step 2: Update `_stream_legacy` to drop the regex check**

The legacy method still uses `_requires_xml_fallback`. Since `_stream_legacy` is a deprecated path only triggered when `use_chat_drivers=False`, simplify it to always use `chat_protocol="xml"` to engage the XML path:

In `_stream_legacy`, replace:

```python
        use_xml_fallback = self.config.chat_protocol != "ollama"
        if not use_xml_fallback and _requires_xml_fallback(model):
            use_xml_fallback = True
            logger.info(...)
```

With:

```python
        # Legacy path: only "xml" forces fallback. Family auto-routing now
        # lives in DriverRegistry (use_chat_drivers=True).
        use_xml_fallback = self.config.chat_protocol == "xml"
```

- [ ] **Step 3: Drop the `_re` import if unused**

Check whether `import re as _re` is still used:

```bash
grep -n "_re\." src/ayder_cli/providers/impl/ollama.py
```

If no matches, remove `import re as _re` from the top of the file.

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green. (Legacy callers — none in production code — would now skip auto-routing in legacy mode.)

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama.py
git commit -m "refactor(ollama): remove _MODEL_REQUIRES_XML_FALLBACK regex routing"
```

---

### Task 15: Delete `_stream_xml_fallback`, `XML_INSTRUCTION`, `inject_xml_prompt`, and the legacy parser classes

**Files:**
- Modify: `src/ayder_cli/providers/impl/ollama.py`

The new path uses `GenericXMLDriver` for the `chat_protocol="xml"` override. The legacy `_stream_xml_fallback` and its dependencies are dead code.

- [ ] **Step 1: Find current line numbers of the dead symbols**

```bash
grep -n "^XML_INSTRUCTION\|^def inject_xml_prompt\|^class ToolStreamParser\|^class XMLParserAdapter\|async def _stream_xml_fallback" src/ayder_cli/providers/impl/ollama.py
```

- [ ] **Step 2: Replace `_stream_legacy` with a thin redirect**

Now that the legacy in-content path can use the new `GenericXMLDriver`, replace the entire `_stream_legacy` method with a simple delegate:

```python
    async def _stream_legacy(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        verbose: bool,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        """Legacy path. Now delegates to the same code as use_chat_drivers=True
        but always forces generic_xml when chat_protocol == 'xml'.
        Kept temporarily so a user with use_chat_drivers=False set explicitly
        in their config doesn't break. Removed in Task 17."""
        async for chunk in self._stream_via_drivers(
            messages, model, tools, options, verbose
        ):
            yield chunk
```

- [ ] **Step 3: Delete `_stream_xml_fallback`, `XML_INSTRUCTION`, `inject_xml_prompt`, `ToolStreamParser`, `XMLParserAdapter`, and `StreamEvent`**

Delete the following from `src/ayder_cli/providers/impl/ollama.py`:

- Lines 57-101: `XML_INSTRUCTION` constant + `inject_xml_prompt` function
- Lines 104-112: `@dataclass StreamEvent` (only used by deleted parsers)
- Lines 115-390: `class ToolStreamParser` (entire class)
- Lines 393-420: `class XMLParserAdapter` (entire class)
- Lines 545-631: `async def _stream_xml_fallback` (entire method)

(Use the line numbers reported in Step 1; the file shrinks by roughly 350 lines.)

After deletion, the file imports may have unused names. Clean up:

```bash
grep -n "^from \|^import " src/ayder_cli/providers/impl/ollama.py
```

Remove any imports that are no longer referenced (likely `from dataclasses`, `Iterator`, `Literal`, etc.). Verify by running:

```bash
.venv/bin/python3 -c "import ayder_cli.providers.impl.ollama"
```

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green. The 18 skipped tests should remain skipped (not become failures).

If any test fails because it imported `inject_xml_prompt`, `XML_INSTRUCTION`, `ToolStreamParser`, or `XMLParserAdapter` directly, update those tests to import from the new location:

- `XML_INSTRUCTION` → no longer accessible as module-level constant (it lives inside `generic_xml.py` as `_XML_INSTRUCTION`). Tests referencing it must be rewritten to assert on the rendered output via `GenericXMLDriver().render_tools_into_messages(...)`.
- `inject_xml_prompt` → replaced by `GenericXMLDriver().render_tools_into_messages(messages, tools)`.

Locate any such test references with:

```bash
grep -rn "inject_xml_prompt\|XML_INSTRUCTION\|XMLParserAdapter\|ToolStreamParser" tests/
```

For each match, update the test to use the new driver-based equivalent.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama.py tests/
git commit -m "refactor(ollama): delete legacy XML_INSTRUCTION and _stream_xml_fallback"
```

---

### Task 16: Delete `_stream_legacy` and the `use_chat_drivers` flag check

**Files:**
- Modify: `src/ayder_cli/providers/impl/ollama.py`

Now that the legacy path is a thin redirect to the new path, `_stream_legacy` and the flag check are unnecessary.

- [ ] **Step 1: Inline `_stream_via_drivers` into `stream_with_tools`**

Replace `stream_with_tools` body:

```python
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        if self._registry is None:
            inspector = OllamaInspector(host=self._client._client.base_url.host)
            self._registry = DriverRegistry(inspector)

        driver_override_name = (
            "generic_xml" if self.config.chat_protocol == "xml" else None
        )
        driver = await self._registry.resolve(model, override=driver_override_name)
        logger.debug(
            f"Ollama driver={driver.name} mode={driver.mode.value} for {model!r}"
        )

        committed = False
        try:
            async for chunk in self._stream_with_driver(
                driver, messages, model, tools, options
            ):
                if chunk.content or chunk.reasoning or chunk.tool_calls:
                    committed = True
                yield chunk
        except OllamaServerToolBug as exc:
            if committed or not driver.fallback_driver:
                raise
            fallback = self._registry.get(driver.fallback_driver)
            logger.info(
                f"{driver.name} ({driver.mode.value}) failed mid-stream: {exc!r}; "
                f"transparently retrying with {fallback.name} "
                f"({fallback.mode.value})"
            )
            async for chunk in self._stream_with_driver(
                fallback, messages, model, tools, options
            ):
                yield chunk
```

- [ ] **Step 2: Delete `_stream_via_drivers` and `_stream_legacy` methods**

Both are dead code now. Delete them.

- [ ] **Step 3: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add src/ayder_cli/providers/impl/ollama.py
git commit -m "refactor(ollama): inline driver routing into stream_with_tools"
```

---

## Phase 4 — Cleanup (Tasks 17-18)

---

### Task 17: Remove `use_chat_drivers` config flag

**Files:**
- Modify: `src/ayder_cli/core/config.py` (delete the flag)
- Modify: `tests/core/test_config.py` (remove flag-related tests)
- Modify: `tests/providers/ollama_drivers/test_provider_integration.py` (drop the flag from configs)

- [ ] **Step 1: Remove the field from Config**

In `src/ayder_cli/core/config.py`, delete the `use_chat_drivers` field declaration entirely.

- [ ] **Step 2: Remove flag-related tests**

In `tests/core/test_config.py`, delete:
- `test_use_chat_drivers_defaults_to_true`
- `test_use_chat_drivers_can_be_enabled`

- [ ] **Step 3: Drop the flag from integration test configs**

In `tests/providers/ollama_drivers/test_provider_integration.py`:
- Delete `test_provider_uses_legacy_path_when_flag_is_false` entirely.
- In `_config()` helper, remove the `use_chat_drivers` parameter.
- Remove `cfg.use_chat_drivers = ...` line.
- The remaining `test_provider_uses_driver_path_when_flag_is_true` should be renamed to `test_provider_routes_through_drivers` and have its `use_chat_drivers` argument dropped.

In `tests/providers/ollama_drivers/test_fallback.py`, remove `cfg.use_chat_drivers = True` from `_config()`.

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/core/config.py tests/
git commit -m "refactor(config): remove use_chat_drivers transition flag"
```

---

### Task 18: Update `docs/PROJECT_STRUCTURE.md`

**Files:**
- Modify: `docs/PROJECT_STRUCTURE.md`

- [ ] **Step 1: Locate the providers section**

```bash
grep -n "providers\|impl/" docs/PROJECT_STRUCTURE.md | head -20
```

- [ ] **Step 2: Update the module map**

Add a new subsection under the providers section describing `ollama_drivers/`:

```markdown
##### `providers/impl/ollama_drivers/` — Per-family Ollama chat drivers

Each driver is one file owning a model family's prompt template, parser,
and detection. Adding a new family is one file plus its paired test in
`tests/providers/ollama_drivers/test_<family>.py`. No edits to existing
drivers, the registry, or `OllamaProvider` are required.

| File | Purpose |
|---|---|
| `base.py` | `ChatDriver` ABC, `DriverMode` enum |
| `matrix.py` | `RESOLUTION_MATRIX` data table — see module docstring for add/remove rules |
| `registry.py` | `DriverRegistry` with auto-discovery + matrix-first resolve |
| `_errors.py` | `OllamaServerToolBug` + `classify_ollama_error` |
| `generic_native.py` | Trusts Ollama's native `tools=[...]` extraction |
| `generic_xml.py` | Universal IN_CONTENT fallback (XML format) |
| `qwen3.py` | qwen2/qwen3 trained format |
| `deepseek.py` | deepseek-r1/v3/coder `<function_calls><invoke>` format |
| `minimax.py` | MiniMax-M1 namespaced `<minimax:tool_call>` format |

See [docs/superpowers/specs/2026-05-02-ollama-chat-drivers-design.md](superpowers/specs/2026-05-02-ollama-chat-drivers-design.md)
for the design rationale.
```

- [ ] **Step 3: Update any line references that are now stale**

Search for references to the old structure:

```bash
grep -nE "_stream_xml_fallback|XML_INSTRUCTION|_MODEL_REQUIRES_XML_FALLBACK|inject_xml_prompt|XMLParserAdapter|_requires_xml_fallback" docs/
```

For each match, either delete the reference (if obsolete) or update it to point to the new location.

- [ ] **Step 4: Run full suite (sanity)**

```bash
.venv/bin/python3 -m pytest tests/ --timeout=10 -q
```

- [ ] **Step 5: Commit**

```bash
git add docs/PROJECT_STRUCTURE.md
git commit -m "docs: update PROJECT_STRUCTURE for ollama_drivers package"
```

---

## Done Criteria

After Task 18:

- `src/ayder_cli/providers/impl/ollama.py` is roughly 350 lines (down from 700).
- `src/ayder_cli/providers/impl/ollama_drivers/` exists with `base.py`, `matrix.py`, `registry.py`, `_errors.py`, and 5 driver files.
- `tests/providers/ollama_drivers/` has paired test files for every driver plus `test_matrix.py`, `test_registry.py`, `test_errors.py`, `test_fallback.py`, `test_provider_integration.py`.
- The full test suite is green: roughly `1110 passed, 18 skipped` (1052 baseline + ~60 new).
- `chat_protocol="xml"` user override still works (forces `GenericXMLDriver`).
- qwen3.6 + Ollama 0.22+ no longer triggers `XML syntax error: unexpected EOF`. Verified by running the app interactively against a local Ollama with qwen3.6 and reading at least one tool call from the assistant.

---

## Spec Coverage Audit

| Spec section | Implementation task |
|---|---|
| §1 Problem statement | Tasks 13-16 (deletes the source of qwen3 crash) |
| §5 Architecture (3 layers) | Tasks 1, 5, 9 |
| §6.1 `ChatDriver` interface | Task 1 |
| §6.2 Driver modules (one per file) | Tasks 6, 7, 10, 11, 12 |
| §6.3 Resolution matrix | Task 3 |
| §6.4 `DriverRegistry` | Task 5 |
| §6.5 `ModelInfo.name` field | Task 2 |
| §6.6 `OllamaProvider` integration | Task 9 |
| §7 Data flow per turn | Tasks 9 (NATIVE + IN_CONTENT helpers), 12.5 |
| §8 Error handling + classification | Tasks 4, 12.5 |
| §9 Testing strategy | All test files in tasks 1-12.5 |
| §10 Migration plan | Phase ordering 1→2→3→4 |
| §11 Risks (auto-discovery skip on broken module) | Task 5 (try/except in `_auto_discover`) |

All spec sections have at least one task. No gaps.

## Future Work (out of scope for this plan)

The spec deliberately omits a Future Work section. Anything beyond Phase 4 is a separate brainstorming session.
