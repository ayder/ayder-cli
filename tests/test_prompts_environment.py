"""Every system prompt carries the session environment section.

Kind: baseline regression. On the parent no prompt named the project's absolute
path, so a model guessed one from a skill header and ran `git init` in the
user's home directory. Structure only, never wording: the section must hold the
resolved project root and the session start date, ahead of the tool prompts.
"""

from datetime import date
from unittest.mock import MagicMock

from ayder_cli.agents.config import AgentConfig
from ayder_cli.application import runtime_factory
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.skill_definitions import SKILL_TOOL_PROMPT


def _runtime(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    return runtime_factory.create_runtime(config=Config(), project_root=str(tmp_path), **kwargs)


def test_runtime_prompt_has_root_and_date_before_tools(tmp_path, monkeypatch):
    prompt = _runtime(tmp_path, monkeypatch).system_prompt
    root = str(tmp_path.resolve())

    assert root in prompt
    assert date.today().isoformat() in prompt
    assert prompt.index(root) < prompt.index(SKILL_TOOL_PROMPT)


def test_override_prompt_has_root(tmp_path, monkeypatch):
    prompt = _runtime(tmp_path, monkeypatch, system_prompt_override="Custom base.").system_prompt

    assert prompt.startswith("Custom base.")
    assert str(tmp_path.resolve()) in prompt


def test_agent_prompt_has_root(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    rt = runtime_factory.create_agent_runtime(
        agent_config=AgentConfig(name="a", system_prompt="Agent base."),
        parent_config=Config(),
        project_ctx=ProjectContext(str(tmp_path)),
        process_manager=MagicMock(),
        permissions={"r"},
    )

    assert str(tmp_path.resolve()) in rt.system_prompt
