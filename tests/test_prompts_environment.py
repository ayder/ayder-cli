"""Every system prompt carries the session environment section.

Kind: baseline regression. On the parent no prompt named the project's absolute
path, so a model guessed one from a skill header and ran `git init` in the
user's home directory. Structure only, never wording: the section must hold the
resolved project root and the session start date and time, ahead of the tool
prompts.
"""

import re
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from ayder_cli.agents.config import AgentConfig
from ayder_cli.application import runtime_factory
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext, new_scratch_dir
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


def test_runtime_prompt_has_start_time(tmp_path, monkeypatch):
    """Baseline regression: the start date came without a time of day."""
    prompt = _runtime(tmp_path, monkeypatch).system_prompt

    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}", prompt)


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


def _scratch_line(prompt):
    m = re.search(r"^Scratch directory: (.+)$", prompt, re.MULTILINE)
    return Path(m.group(1)) if m else None


def _agent_runtime(project_ctx, monkeypatch):
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())
    return runtime_factory.create_agent_runtime(
        agent_config=AgentConfig(name="a", system_prompt="Agent base."),
        parent_config=Config(),
        project_ctx=project_ctx,
        process_manager=MagicMock(),
        permissions={"r"},
    )


def test_runtime_prompt_names_the_session_scratch_dir(tmp_path, monkeypatch):
    """New interface: the session gets a scratch directory the file tools may use."""
    rt = _runtime(tmp_path, monkeypatch)
    named = _scratch_line(rt.system_prompt)

    assert named is not None and named.is_dir()
    assert named.resolve() == rt.project_ctx.scratch_dir
    assert rt.system_prompt.index(str(named)) < rt.system_prompt.index(SKILL_TOOL_PROMPT)


def test_agent_prompt_names_its_own_dir_inside_the_session_dir(tmp_path, monkeypatch):
    session = new_scratch_dir(tmp_path)
    rt = _agent_runtime(ProjectContext(str(tmp_path), scratch_dir=session), monkeypatch)
    named = _scratch_line(rt.system_prompt)

    assert named is not None and named.is_dir()
    assert named.parent.resolve() == session.resolve()


def test_no_scratch_dir_no_scratch_line(tmp_path, monkeypatch):
    rt = _agent_runtime(ProjectContext(str(tmp_path)), monkeypatch)

    assert _scratch_line(rt.system_prompt) is None
    assert str(tmp_path.resolve()) in rt.system_prompt
