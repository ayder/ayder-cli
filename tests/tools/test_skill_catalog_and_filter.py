"""The skills filter, the generated catalog and hiding the skill tool (spec 4.4, 4.10).

Kind: new interface (the parent has no filter, no catalog and no exclusion).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ayder_cli.agents.config import AgentConfig
from ayder_cli.application import runtime_factory
from ayder_cli.core import skills as sk
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.core.skills import build_scope, format_catalog, resolve_enabled
from ayder_cli.tools.registry import create_default_registry


def _packaged(name="engineering", text="---\ndescription: Build\n---\nRules v1"):
    skill_dir = sk.PACKAGED_SKILLS_DIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")


def _project_skill(root, name, description):
    skill_dir = Path(root) / ".ayder" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\ndescription: {description}\n---\nBody", encoding="utf-8")


def test_default_enables_builtins_only(tmp_path):
    _packaged()
    _project_skill(tmp_path, "local", "Project only")
    scope = build_scope(tmp_path, None)
    assert [info.name for info in scope.enabled_skills()] == ["engineering"]


def test_customized_builtin_stays_enabled_by_default(tmp_path):
    _packaged()
    _project_skill(tmp_path, "engineering", "My version")
    [info] = build_scope(tmp_path, None).enabled_skills()
    assert (info.layer, info.description) == ("project", "My version")


def test_strict_list_and_unknown_name_warning(tmp_path, loguru_caplog):
    _packaged()
    _project_skill(tmp_path, "local", "Project only")
    scope = build_scope(tmp_path, ["local", "ghost"])
    assert [info.name for info in scope.enabled_skills()] == ["local"]
    assert "'ghost'" in loguru_caplog.text


def test_none_enables_nothing():
    assert resolve_enabled("none") == frozenset()


def test_catalog_format():
    _packaged()
    catalog = format_catalog(build_scope(Path("/nonexistent"), None).enabled_skills())
    assert catalog == "\n\n### Skills\n- engineering: Build\n"
    assert format_catalog([]) == ""


def test_registry_appends_the_catalog_after_the_tool_prompts(tmp_path):
    _packaged()
    registry = create_default_registry(ProjectContext(str(tmp_path)))
    registry.skill_scope = build_scope(tmp_path, None)
    prompts = registry.get_system_prompts(tags=frozenset({"core"}))
    assert prompts.endswith("\n\n### Skills\n- engineering: Build\n")
    assert prompts.index("### Skill Tool") < prompts.index("### Skills\n")


def _runtime(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    return runtime_factory.create_runtime(config=cfg, project_root=str(tmp_path))


def test_none_hides_the_tool_and_the_catalog(tmp_path, monkeypatch):
    _packaged()
    rt = _runtime(tmp_path, monkeypatch, Config(skills="none"))
    names = [s["function"]["name"] for s in rt.tool_registry.get_schemas(tags=frozenset(rt.config.tool_tags))]
    assert "skill" not in names
    assert "### Skill Tool" not in rt.system_prompt
    assert "### Skills" not in rt.system_prompt
    result = rt.tool_registry.execute("skill", {"action": "list"})
    assert isinstance(result, ToolError)


def test_default_runtime_prompt_has_the_catalog(tmp_path, monkeypatch):
    _packaged()
    rt = _runtime(tmp_path, monkeypatch, Config())
    assert "### Skills\n- engineering: Build\n" in rt.system_prompt


def test_override_prompt_still_gets_the_catalog(tmp_path, monkeypatch):
    _packaged()
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    rt = runtime_factory.create_runtime(
        config=Config(), project_root=str(tmp_path), system_prompt_override="Custom base."
    )
    assert rt.system_prompt.startswith("Custom base.")
    assert "### Skills\n- engineering: Build\n" in rt.system_prompt


def _agent_runtime(tmp_path, agent, parent):
    return runtime_factory.create_agent_runtime(
        agent_config=agent,
        parent_config=parent,
        project_ctx=ProjectContext(str(tmp_path)),
        process_manager=MagicMock(),
        permissions={"r"},
    )


def test_agent_setting_wins(tmp_path, monkeypatch):
    _packaged()
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    parent = Config(skills="none", profile_skills=None)
    rt = _agent_runtime(tmp_path, AgentConfig(name="a", skills=["engineering"]), parent)
    assert rt.tool_registry.skill_scope.enabled == frozenset({"engineering"})


def test_agent_ignores_app_and_uses_its_profile(tmp_path, monkeypatch):
    _packaged()
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    parent = Config(skills="none", profile_skills=None)  # [app] says none
    rt = _agent_runtime(tmp_path, AgentConfig(name="a"), parent)
    assert rt.tool_registry.skill_scope.enabled == frozenset({"engineering"})  # built-in default
    assert "skill" not in rt.tool_registry.excluded_tools


def test_empty_list_hides_the_tool(tmp_path, monkeypatch):
    _packaged()
    rt = _runtime(tmp_path, monkeypatch, Config(skills=[]))
    assert "skill" in rt.tool_registry.excluded_tools
    assert "### Skills" not in rt.system_prompt


def test_rebuilt_prompt_keeps_the_catalog(tmp_path, monkeypatch):
    """tui/app.py rebuilds the prompt from registry.get_system_prompts()."""
    _packaged()
    rt = _runtime(tmp_path, monkeypatch, Config())
    rebuilt = rt.tool_registry.get_system_prompts(tags=frozenset(rt.config.tool_tags))
    assert "### Skills\n- engineering: Build\n" in rebuilt


def _switch_app(tmp_path):
    from ayder_cli.tui import commands

    registry = create_default_registry(ProjectContext(str(tmp_path)))
    registry.skill_scope = build_scope(tmp_path, None)
    app = MagicMock()
    app.registry = registry
    app.messages = [{"role": "system", "content": "s"}]
    app._agent_registry = None
    app.request_turn = lambda prepare=None, **kwargs: prepare()
    return commands, app


def _switch(commands, app, monkeypatch, cfg):
    monkeypatch.setattr(commands, "load_config_for_provider", lambda provider: cfg)
    monkeypatch.setattr(commands.provider_orchestrator, "create", lambda c: MagicMock())
    commands._apply_provider_switch(app, "other", MagicMock())


def test_provider_switch_applies_the_new_profiles_skills(tmp_path, monkeypatch):
    """Review C1: /provider must re-apply skills in both directions."""
    _packaged()
    commands, app = _switch_app(tmp_path)

    _switch(commands, app, monkeypatch, Config(profile_skills="none"))
    assert "skill" in app.registry.excluded_tools
    assert "### Skills" not in app.registry.get_system_prompts(tags=frozenset({"core"}))
    assert isinstance(app.registry.execute("skill", {"action": "load", "name": "engineering"}), ToolError)

    _switch(commands, app, monkeypatch, Config(profile_skills=["engineering"]))
    assert "skill" not in app.registry.excluded_tools
    assert app.registry.skill_scope.enabled == frozenset({"engineering"})
    assert app.registry.skill_scope.messages is app.messages
    assert "### Skills\n- engineering: Build\n" in app.registry.get_system_prompts(tags=frozenset({"core"}))
