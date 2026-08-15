"""Correlation-id threading: `session_id` (C11b) and `run_id` (R-3).

No event is emitted in this step. These tests prove only that the two
correlation ids actually reach every consumer — the loop config, both context
managers, and the registry -> runner -> loop-config chain — and that the *live*
construction sites pass them. Signature-only checks would pass while a caller
silently omitted the keyword, so the construction sites are asserted against
the parsed source.
"""

import ast
import inspect
from pathlib import Path
from unittest.mock import MagicMock

from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

SRC = Path(__file__).resolve().parents[2] / "src" / "ayder_cli"


# -- construction harnesses (R-12: reuse the existing test shapes) ------------


def _make_cm_config(max_context_tokens: int = 8192):
    """The config shape `tests/core/test_default_context_manager.py` uses."""
    cfg = MagicMock()
    cfg.context_manager.max_context_tokens = max_context_tokens
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    cfg.context_manager.tool_result_compress_age = 5
    cfg.context_manager.max_tool_result_length = 2048
    cfg.context_manager.compress_tool_results = True
    cfg.context_manager.enabled = True
    cfg.provider = "openai"
    cfg.model = "gpt-4o"
    return cfg


def _default_manager():
    from ayder_cli.core.default_context_manager import DefaultContextManager

    return DefaultContextManager.from_config(_make_cm_config())


def _ollama_manager():
    """The construction `tests/core/test_ollama_context_manager.py` uses."""
    from ayder_cli.core.ollama_context_manager import OllamaContextManager

    return OllamaContextManager(
        provisional_context_length=65536,
        reserve_ratio=0.3,
        compaction_threshold=0.7,
    )


def _build_loop(manager, **config_kwargs) -> ChatLoop:
    return ChatLoop(
        llm=MagicMock(),
        registry=MagicMock(),
        messages=[],
        config=ChatLoopConfig(**config_kwargs),
        callbacks=MagicMock(),
        context_manager=manager,
    )


# -- AST helpers (precedent: tests/core/test_exception_hooks.py::_ast_of) -----


def _ast_of(rel: str) -> ast.Module:
    return ast.parse((SRC / rel).read_text())


def _calls_named(tree: ast.Module, name: str) -> list[ast.Call]:
    """EVERY call of `name` in the module, nested ones included.

    `ast.walk` on purpose here: unlike the reachability guards in
    test_exception_hooks, the claim under test is "no construction site is
    missing the keyword", so a site nested in a method or an `if` must count.
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            getattr(node.func, "id", None) == name
            or getattr(node.func, "attr", None) == name
        )
    ]


def _kwarg(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _kwarg_src(call: ast.Call, name: str) -> str | None:
    value = _kwarg(call, name)
    return None if value is None else ast.unparse(value)


def _real_kwarg_src(call: ast.Call, name: str, where: str) -> str:
    """The keyword's source text, asserting it exists and is not `None`."""
    value = _kwarg(call, name)
    assert value is not None, f"{where}: missing {name}= keyword"
    assert not (
        isinstance(value, ast.Constant) and value.value is None
    ), f"{where}: {name}=None defeats correlation"
    return ast.unparse(value)


# -- the config fields -------------------------------------------------------


def test_config_has_session_id_defaulting_to_none():
    cfg = ChatLoopConfig()
    assert cfg.session_id is None


def test_config_accepts_a_session_id():
    cfg = ChatLoopConfig(session_id="abc123def456")
    assert cfg.session_id == "abc123def456"


def test_config_has_run_id_defaulting_to_none():
    """R-3: agent-loop events carry a run id; parent loops leave it unset."""
    assert ChatLoopConfig().run_id is None
    assert ChatLoopConfig(run_id=7).run_id == 7


def test_session_id_and_run_id_are_appended_last():
    """R-17: appended after `pre_iteration_hook`, nothing reordered."""
    fields = list(inspect.signature(ChatLoopConfig).parameters)
    assert fields[-3:] == ["pre_iteration_hook", "session_id", "run_id"], fields


def test_new_session_id_is_short_and_unique():
    from ayder_cli.loops.chat_loop import new_session_id

    a, b = new_session_id(), new_session_id()
    assert a != b
    assert len(a) == 12
    assert a.isalnum()


def test_event_generator_is_not_the_persisted_session_generator():
    """R-6: `core.session.new_session_id` is a different, 9-char generator.

    Resumed TUI sessions legitimately carry that form, so the two must not be
    confused for one another.
    """
    from ayder_cli.core import session as session_mod
    from ayder_cli.loops.chat_loop import new_session_id

    assert session_mod.new_session_id is not new_session_id


# -- context managers get the ids by assignment, not by constructor ----------


def test_default_context_manager_declares_both_ids():
    mgr = _default_manager()
    assert mgr.session_id is None
    assert mgr.run_id is None


def test_ollama_context_manager_also_declares_session_id():
    """Ollama sessions must emit context_trim too."""
    mgr = _ollama_manager()
    assert mgr.session_id is None
    assert mgr.run_id is None


def test_chat_loop_assigns_its_session_id_to_the_context_manager():
    """Agent-shaped config: both ids land on the manager by assignment."""
    mgr = _default_manager()
    assert mgr.session_id is None  # declared default
    assert mgr.run_id is None
    _build_loop(mgr, session_id="feedfacecafe", run_id=7)
    assert mgr.session_id == "feedfacecafe"
    assert mgr.run_id == 7


def test_chat_loop_assigns_parent_shaped_ids():
    """Parent CLI/TUI loop: a real session id, and `run_id` stays None."""
    mgr = _default_manager()
    _build_loop(mgr, session_id="0123456789ab")
    assert mgr.session_id == "0123456789ab"
    assert mgr.run_id is None


def test_chat_loop_assigns_ids_to_the_ollama_manager_too():
    mgr = _ollama_manager()
    _build_loop(mgr, session_id="feedfacecafe", run_id=3)
    assert mgr.session_id == "feedfacecafe"
    assert mgr.run_id == 3


def test_chat_loop_assigns_ids_on_the_legacy_manager_path():
    """`context_manager=None` builds one internally; it is assigned too."""
    loop = ChatLoop(
        llm=MagicMock(),
        registry=MagicMock(),
        messages=[],
        config=ChatLoopConfig(session_id="cafebabe1234"),
        callbacks=MagicMock(),
    )
    assert loop.context_manager.session_id == "cafebabe1234"
    assert loop.context_manager.run_id is None


# -- live construction sites (R-9) -------------------------------------------


def test_agent_runner_inherits_rather_than_generates():
    """parent_config is the app Config, not ChatLoopConfig — the id is explicit."""
    from ayder_cli.agents.registry import AgentRegistry
    from ayder_cli.agents.runner import AgentRunner

    assert "session_id" in inspect.signature(AgentRunner.__init__).parameters
    assert "session_id" in inspect.signature(AgentRegistry.__init__).parameters


def test_agents_never_generate_a_session_id():
    """Neither module may call either `new_session_id`; agents inherit."""
    for rel in ("agents/registry.py", "agents/runner.py"):
        source = (SRC / rel).read_text()
        assert "new_session_id" not in source, rel


def test_every_agent_registry_construction_passes_a_session_id():
    for rel in ("cli_runner.py", "tui/app.py"):
        calls = _calls_named(_ast_of(rel), "AgentRegistry")
        assert calls, f"{rel}: no AgentRegistry construction found"
        for call in calls:
            _real_kwarg_src(call, "session_id", f"{rel} AgentRegistry(")


def test_parent_chat_loop_configs_pass_a_session_id():
    for rel in ("cli_runner.py", "tui/app.py"):
        calls = _calls_named(_ast_of(rel), "ChatLoopConfig")
        assert calls, f"{rel}: no ChatLoopConfig construction found"
        for call in calls:
            _real_kwarg_src(call, "session_id", f"{rel} ChatLoopConfig(")


def test_registry_and_loop_share_one_id_per_caller():
    """The registry and the loop must be handed the SAME name, not two ids."""
    for rel in ("cli_runner.py", "tui/app.py"):
        tree = _ast_of(rel)
        registry_ids = {
            _real_kwarg_src(c, "session_id", rel)
            for c in _calls_named(tree, "AgentRegistry")
        }
        config_ids = {
            _real_kwarg_src(c, "session_id", rel)
            for c in _calls_named(tree, "ChatLoopConfig")
        }
        assert registry_ids == config_ids, (rel, registry_ids, config_ids)


def test_registry_forwards_its_stored_session_id_to_the_runner():
    calls = _calls_named(_ast_of("agents/registry.py"), "AgentRunner")
    assert calls, "no AgentRunner construction found"
    for call in calls:
        src = _real_kwarg_src(call, "session_id", "registry AgentRunner(")
        assert src.startswith("self."), src
        assert "_parent_config" not in src, "parent_config is the app Config"


def test_runner_loop_config_carries_both_correlation_ids():
    tree = _ast_of("agents/runner.py")
    calls = _calls_named(tree, "ChatLoopConfig")
    assert calls, "no ChatLoopConfig construction found in agents/runner.py"
    for call in calls:
        session_src = _real_kwarg_src(call, "session_id", "runner ChatLoopConfig(")
        assert session_src.startswith("self."), session_src

        run_value = _kwarg(call, "run_id")
        assert run_value is not None, "runner ChatLoopConfig(: missing run_id="
        assert (
            isinstance(run_value, ast.Attribute)
            and isinstance(run_value.value, ast.Name)
            and run_value.value.id == "self"
            and run_value.attr == "run_id"
        ), ast.unparse(run_value)

    # ...and `self.run_id` really is the runner's own stored run id.
    stored = [
        target.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    ]
    assert "run_id" in stored
