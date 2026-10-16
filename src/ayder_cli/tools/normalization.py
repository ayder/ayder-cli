"""Argument normalization pipeline — aliases, path resolution, type coercion.

Extracted from tools/registry.py. Single responsibility: transform raw LLM
arguments into validated, absolute-path-resolved, correctly-typed dicts.
"""

from ayder_cli.tools.definition import TOOL_DEFINITIONS, TOOL_DEFINITIONS_BY_NAME
from ayder_cli.core.context import ProjectContext

# Generated at import time from ToolDefinitions — keyed by tool name
PARAMETER_ALIASES: dict[str, dict[str, str]] = {
    td.name: dict(td.parameter_aliases)
    for td in TOOL_DEFINITIONS
    if td.parameter_aliases
}

PATH_PARAMETERS: dict[str, list[str]] = {
    td.name: list(td.path_parameters)
    for td in TOOL_DEFINITIONS
    if td.path_parameters
}


def canonicalize_arguments(tool_name: str, arguments: dict) -> dict:
    """Return a canonical copy of ``arguments``, without touching the filesystem.

    1. Apply parameter aliases (e.g. ``path`` -> ``file_path``); a canonical key
       already present wins, and aliases apply in declaration order.
    2. Coerce ``"123"`` to ``123`` for ``integer`` parameters.
    3. Coerce ``"true"`` / ``"false"`` (case-insensitive, surrounding space
       ignored) to ``True`` / ``False`` for ``boolean`` parameters.

    Values that cannot be coerced are left as they are, for the schema
    validator to reject. Shared by the execution policy and the chat loop's
    required-argument gate, so both resolve aliases and coercions alike.
    """
    canonical = dict(arguments)  # copy to avoid mutating caller's dict
    td = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    parameter_aliases = (
        dict(td.parameter_aliases)
        if td is not None
        else PARAMETER_ALIASES.get(tool_name, {})
    )

    for alias, target in parameter_aliases.items():
        if alias in canonical and target not in canonical:
            canonical[target] = canonical.pop(alias)

    if td:
        props = td.parameters.get("properties", {})
        for key, schema in props.items():
            if key not in canonical or not isinstance(canonical[key], str):
                continue
            expected = schema.get("type")
            if expected == "integer":
                try:
                    canonical[key] = int(canonical[key])
                except ValueError:
                    pass  # keep as string; validation will catch it later
            elif expected == "boolean":
                word = canonical[key].strip().lower()
                if word in ("true", "false"):
                    canonical[key] = word == "true"

    return canonical


def normalize_arguments(
    tool_name: str, arguments: dict, project_ctx: ProjectContext
) -> dict:
    """Canonicalize tool arguments, then resolve path parameters.

    1. ``canonicalize_arguments``: aliases, integer and boolean coercion.
    2. Resolve path parameters to absolute paths via ProjectContext
       (also validates the path is inside the project sandbox).

    Args:
        tool_name: Name of the tool being called.
        arguments: Raw argument dict from the LLM.
        project_ctx: Project context for path sandboxing.

    Returns:
        Normalized argument dict (copy — original is not mutated).

    Raises:
        ValueError: If a path parameter resolves outside the project sandbox.
    """
    normalized = canonicalize_arguments(tool_name, arguments)
    td = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    path_parameters = (
        list(td.path_parameters)
        if td is not None
        else PATH_PARAMETERS.get(tool_name, [])
    )

    # Resolve path parameters to absolute (validates sandbox)
    for param_name in path_parameters:
        if param_name in normalized and normalized[param_name]:
            try:
                validated_path = project_ctx.validate_path(normalized[param_name])
                normalized[param_name] = str(validated_path)
            except ValueError:
                raise  # security error — propagate to caller

    return normalized
