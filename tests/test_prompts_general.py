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


def test_standard_prompt_routes_by_the_kind_of_work():
    text = _flat(STANDARD_SYSTEM_PROMPT)
    assert "Larger kinds of work" not in text
    assert "Work out what the user wants: the kind of work and the result they expect." in text
    assert "If a skill catalog is listed under \"### Skills\", compare the request with each entry." in text
    assert "4. Otherwise do the work directly, without a skill." in text


def test_routing_rule_matches_kind_not_size():
    text = _flat(SKILL_TOOL_PROMPT)
    assert "larger kinds of work" not in text.lower()
    assert "Match by the kind of work, not by its size." in text
    assert "A request you can fully answer in one reply without tools needs no skill." in text
    assert (
        "Reason about what the request needs, and load the skill whose guidance "
        "will help you deliver it." in text
    )
