"""Tool definition for skill discovery and loading."""

from typing import Tuple

from ..definition import ToolDefinition

SKILL_TOOL_PROMPT = """

### Skill Tool
The catalog under "### Skills" lists the skills enabled for this session, one
per line as `name: the kinds of requests it is for`.
- Match by the kind of work, not by its size. "Plan a multi-step web project"
  matches an entry for planning multi-step technical work; "fix the failing
  test" matches an entry for debugging code.
- When a request matches and needs more than one reply, call
  `skill(action="load", name="<name>")` before you start the work, then follow
  the instructions it returns.
- A request you can fully answer in one reply without tools needs no skill.
- If no entry matches, do the work without a skill.
- Do not ask the user to choose a mode or a role. Reason about what the
  request needs, and load the skill whose guidance will help you deliver it.
- Load more than one skill only when the request needs both. A loaded skill
  stays loaded for the session; do not load it again unless you unloaded it.
- `skill(action="read", name="<name>", path="<file>")` reads a file the loaded
  skill lists; `skill(action="unload", name="<name>")` stops it when the work
  changes kind.
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
