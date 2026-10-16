"""The runtime's SkillScope reaches the skill tool and tracks the history.

Kind: new interface (the parent has no SkillScope and no injection).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.core.skills import SkillScope
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig
from ayder_cli.tools.registry import create_default_registry


def _skill(tmp_path, name="alpha"):
    skill_dir = tmp_path / ".ayder" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Body", encoding="utf-8")


def test_registry_injects_its_scope(tmp_path):
    _skill(tmp_path)
    registry = create_default_registry(ProjectContext(str(tmp_path)))
    registry.skill_scope = SkillScope(project_root=Path(tmp_path), enabled=frozenset())
    result = registry.execute("skill", {"action": "load", "name": "alpha"})
    # Only the injected scope disables it; the refusal names that reason.
    assert isinstance(result, ToolError)
    assert result.startswith("Unknown or disabled skill: 'alpha'."), result


def test_chat_loop_binds_the_history(tmp_path):
    registry = create_default_registry(ProjectContext(str(tmp_path)))
    registry.skill_scope = SkillScope(project_root=Path(tmp_path))
    messages = [{"role": "system", "content": "s"}]
    ChatLoop(
        llm=MagicMock(),
        registry=registry,
        messages=messages,
        config=ChatLoopConfig(),
        callbacks=MagicMock(),
        context_manager=MagicMock(),
    )
    assert registry.skill_scope.messages is messages


def test_runtime_gives_the_registry_a_scope(tmp_path, monkeypatch):
    from ayder_cli.application import runtime_factory

    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda cfg: MagicMock())
    rt = runtime_factory.create_runtime(config=Config(), project_root=str(tmp_path))
    scope = rt.tool_registry.skill_scope
    assert isinstance(scope, SkillScope)
    assert scope.project_root == Path(rt.project_ctx.root)
