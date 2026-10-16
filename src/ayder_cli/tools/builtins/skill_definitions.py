"""Tool definition for skill discovery and loading."""

from typing import Tuple

from ..definition import ToolDefinition

SKILL_TOOL_PROMPT = """

### Skill Tool
Skills hold the workflows for larger kinds of work. The catalog under "### Skills" lists
the ones enabled for this session.
- When a request matches a catalog entry, call `skill(action="load", name="<name>")`
  before you start the work, then follow the instructions it returns.
- Do not ask the user to choose a mode or a role; choose the skill yourself.
- Load more than one skill only when the request needs both. A skill stays loaded for
  the rest of the session; do not load it again unless you unloaded it.
- If no entry matches, continue without a skill.
- `skill(action="read", name="<name>", path="<file>")` reads a file the loaded skill lists.
- `skill(action="unload", name="<name>")` stops a skill when the work changes kind.
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
