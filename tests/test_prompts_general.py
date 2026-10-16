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


def _flat(text):
    return " ".join(text.split())


def test_standard_prompt_defers_the_skill_decision_to_the_skill_tool():
    text = _flat(STANDARD_SYSTEM_PROMPT)
    assert "Larger kinds of work" not in text
    assert "Work out what the user wants: the kind of work and the result they expect." in text
    assert "decide whether to load a skill as the Skill Tool section says." in text
    assert "3. If no skill is loaded, do the work directly." in text
    # The trigger is stated once, in the Skill Tool section.
    assert "more than a single reply" not in text
    assert "quick questions directly" not in text


def test_routing_rule_is_one_two_step_decision():
    text = _flat(SKILL_TOOL_PROMPT)
    assert "Before you start a request, decide in two steps:" in text
    assert "1. Which entry fits? Compare the kind of work the request asks for with each entry." in text
    assert "2. Is it worth loading? Load the fitting skill when the work takes several steps" in text
    assert "even if that reply needs a tool call or two" in text
    assert (
        "Reason about what the request needs, and load the skill whose guidance "
        "will help you deliver it." in text
    )
    for stale in ("not by its size", "larger kinds of work", "without tools needs no skill"):
        assert stale not in text.lower()
