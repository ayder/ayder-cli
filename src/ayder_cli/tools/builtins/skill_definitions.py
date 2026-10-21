"""Tool definition for skill discovery and loading."""

from typing import Tuple

from ..definition import ToolDefinition

SKILL_TOOL_PROMPT = """

### Skill Tool
The catalog under "### Skills" lists the enabled skills as `name: what it is for`.
Load a skill when it fits the work: `skill(action="load", name="<name>")` returns its
instructions; follow them while that work lasts. `skill(action="read", name="<name>",
path="<file>")` reads a file the skill lists; `skill(action="unload", name="<name>")`
stops it.
"""

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="skill",
        description=(
            "List, load, read or unload skills. Loading returns the skill's "
            "instructions as this tool's result; reading returns one of the "
            "skill's files."
        ),
        description_template="Skill action `{action}`",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.skill:skill",
        permission="r",
        parallel_safe=True,
        safe_mode_blocked=False,
        system_prompt=SKILL_TOOL_PROMPT,
        # load is bounded by MAX_SKILL_BYTES and read truncates itself, so the
        # loop's generic truncation must not cut a skill body in half.
        max_result_chars=0,
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "load", "read", "unload"],
                    "description": "Operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Skill name. Required for load and read.",
                },
                "path": {
                    "type": "string",
                    "description": "File inside the skill, relative to it. Required for read.",
                },
            },
            "required": ["action"],
        },
    ),
)
