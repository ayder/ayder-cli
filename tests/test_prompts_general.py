"""The system prompt exists and reaches the context.

Prompt and skill text is experimental (judged by live probes), so these
tests check structure only, never wording.
"""

from unittest.mock import MagicMock

from ayder_cli.application import runtime_factory
from ayder_cli.core import skills as sk
from ayder_cli.core.config import Config
from ayder_cli.prompts import EXTENDED_SYSTEM_PROMPT, STANDARD_SYSTEM_PROMPT, get_system_prompt
from ayder_cli.tools.builtins.skill_definitions import SKILL_TOOL_PROMPT


def test_standard_prompt_exists():
    assert STANDARD_SYSTEM_PROMPT.strip()
    assert STANDARD_SYSTEM_PROMPT.isascii()
    assert get_system_prompt("STANDARD") == STANDARD_SYSTEM_PROMPT
    assert EXTENDED_SYSTEM_PROMPT is STANDARD_SYSTEM_PROMPT


def test_runtime_injects_base_prompt_skill_tool_and_catalog(tmp_path, monkeypatch):
    skill_dir = sk.PACKAGED_SKILLS_DIR / "engineering"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\ndescription: Build\n---\nBody", encoding="utf-8")
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", lambda c: MagicMock())

    prompt = runtime_factory.create_runtime(config=Config(), project_root=str(tmp_path)).system_prompt

    assert prompt.startswith(STANDARD_SYSTEM_PROMPT)
    assert SKILL_TOOL_PROMPT in prompt
    assert "\n### Skills\n- engineering: Build\n" in prompt
