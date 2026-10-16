"""Loading a skill never rewrites what was sent before it (spec criterion 3).

Kind: baseline regression. On the parent, a load through
the registry appends an "### ACTIVE SKILL:" system message, which Claude and
Gemini fold into their system parameter, so the system-parameter asserts
fail there.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.providers.impl.claude import ClaudeProvider
from ayder_cli.providers.impl.gemini import GeminiProvider
from ayder_cli.providers.impl.ollama import OllamaProvider
from ayder_cli.tools.registry import create_default_registry


def _app(messages):
    from ayder_cli.tui.app import AyderApp

    app = AyderApp.__new__(AyderApp)
    app.messages = messages
    app._active_skill = None  # read by the parent's inject_skill; harmless after
    app._agent_registry = None
    app.query_one = MagicMock(return_value=MagicMock())
    return app


def _histories(tmp_path):
    """The history before a model-initiated load, and after it, as ChatLoop
    would hold it: the tool result is appended after the assistant call."""
    skill_dir = tmp_path / ".ayder" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\ndescription: A\n---\nAlpha rules", encoding="utf-8")

    messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "fix the failing test"},
    ]
    before = json.loads(json.dumps(messages))

    registry = create_default_registry(ProjectContext(str(tmp_path)))
    registry.app = _app(messages)
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "skill", "arguments": '{"action": "load", "name": "alpha"}'},
    }
    messages.append({"role": "assistant", "content": "", "tool_calls": [call]})
    result = registry.execute("skill", {"action": "load", "name": "alpha"})
    messages.append({"role": "tool", "tool_call_id": "c1", "name": "skill", "content": str(result)})
    return before, messages


@pytest.mark.parametrize("provider_cls", [ClaudeProvider, GeminiProvider])
def test_system_parameter_is_unchanged(tmp_path, provider_cls):
    before, after = _histories(tmp_path)
    system_before, _ = provider_cls._convert_messages(before)
    system_after, _ = provider_cls._convert_messages(after)
    assert system_after == system_before


@pytest.mark.parametrize("provider_cls", [ClaudeProvider, GeminiProvider])
def test_converted_turns_extend_the_previous_request(tmp_path, provider_cls):
    before, after = _histories(tmp_path)
    _, turns_before = provider_cls._convert_messages(before)
    _, turns_after = provider_cls._convert_messages(after)
    assert turns_after[: len(turns_before)] == turns_before


def test_ollama_and_openai_messages_extend_the_previous_request(tmp_path):
    before, after = _histories(tmp_path)
    ollama = OllamaProvider.__new__(OllamaProvider)
    converted_before = ollama._convert_messages(before)
    converted_after = ollama._convert_messages(after)
    assert converted_after[: len(converted_before)] == converted_before
    # OpenAI-compatible drivers send the message list as is.
    assert after[: len(before)] == before
    assert [m["role"] for m in after].count("system") == 1


def test_the_tool_result_carries_the_skill(tmp_path):
    _, after = _histories(tmp_path)
    assert after[-1]["content"].startswith("### SKILL LOADED: alpha")
    assert "Alpha rules" in after[-1]["content"]
