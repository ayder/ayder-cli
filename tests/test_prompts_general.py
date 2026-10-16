"""STANDARD is a general assistant; skills are chosen by a routing rule (spec 4.9).

Kind: new interface.
"""

import pytest

from ayder_cli.prompts import EXTENDED_SYSTEM_PROMPT, STANDARD_SYSTEM_PROMPT
from ayder_cli.tools.builtins.skill_definitions import SKILL_TOOL_PROMPT


def test_standard_prompt_is_a_general_assistant():
    assert "Engineering Role" not in STANDARD_SYSTEM_PROMPT
    assert "switch" not in STANDARD_SYSTEM_PROMPT.lower()
    assert STANDARD_SYSTEM_PROMPT.startswith("You are ayder, a general-purpose assistant")
    assert EXTENDED_SYSTEM_PROMPT is STANDARD_SYSTEM_PROMPT


@pytest.mark.parametrize("text", [STANDARD_SYSTEM_PROMPT, SKILL_TOOL_PROMPT])
def test_prompt_text_rules(text):
    assert text.isascii()
    assert len(text.splitlines()) < 130


def test_routing_rule_tells_the_model_to_choose():
    assert 'skill(action="load", name="<name>")' in SKILL_TOOL_PROMPT
    assert "Do not ask the user to choose a mode" in SKILL_TOOL_PROMPT
