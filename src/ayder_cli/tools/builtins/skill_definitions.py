"""Tool definition for skill discovery and loading."""

from typing import Tuple

from ..definition import ToolDefinition

SKILL_TOOL_PROMPT = """

### Skill Tool
Use `skill(action="list")` to discover project skills in `.ayder/skills/`.
When a user request clearly matches an available skill, call
`skill(action="load", name="<skill-name>")` before continuing so the skill
instructions are active. Use `skill(action="unload")` when the user asks to
clear the active skill.
"""

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="skill",
        description=(
            "List, load, or unload project skills from .ayder/skills/. Loading "
            "a skill reads SKILL.md plus directly referenced local files and "
            "activates it as a system message."
        ),
        description_template="Skill action `{action}`",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.skill:skill",
        permission="r",
        safe_mode_blocked=False,
        system_prompt=SKILL_TOOL_PROMPT,
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "load", "unload"],
                    "description": "Operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Skill name. Required for action=load.",
                },
            },
            "required": ["action"],
        },
    ),
)
