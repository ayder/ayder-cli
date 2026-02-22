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


def normalize_arguments(
    tool_name: str, arguments: dict, project_ctx: ProjectContext
) -> dict:
    """Normalize tool arguments in three steps.

    1. Apply parameter aliases (e.g. ``path`` → ``file_path``).
    2. Resolve path parameters to absolute paths via ProjectContext
       (also validates the path is inside the project sandbox).
    3. Coerce string values to int for integer-typed parameters.

    Args:
        tool_name: Name of the tool being called.
        arguments: Raw argument dict from the LLM.
        project_ctx: Project context for path sandboxing.

    Returns:
        Normalized argument dict (copy — original is not mutated).

    Raises:
        ValueError: If a path parameter resolves outside the project sandbox.
    """
    normalized = dict(arguments)  # copy to avoid mutating caller's dict

    # Step 1: Apply aliases
    if tool_name in PARAMETER_ALIASES:
        for alias, canonical in PARAMETER_ALIASES[tool_name].items():
            if alias in normalized and canonical not in normalized:
                normalized[canonical] = normalized.pop(alias)

    # Step 2: Resolve path parameters to absolute (validates sandbox)
    if tool_name in PATH_PARAMETERS:
        for param_name in PATH_PARAMETERS[tool_name]:
            if param_name in normalized and normalized[param_name]:
                try:
                    validated_path = project_ctx.validate_path(normalized[param_name])
                    normalized[param_name] = str(validated_path)
                except ValueError:
                    raise  # security error — propagate to caller

    # Step 3: Type coercion (string → int for integer-typed parameters)
    td = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    if td:
        props = td.parameters.get("properties", {})
        for key, schema in props.items():
            if (
                schema.get("type") == "integer"
                and key in normalized
                and isinstance(normalized[key], str)
            ):
                try:
                    normalized[key] = int(normalized[key])
                except ValueError:
                    pass  # keep as string; validation will catch it later

    return normalized


# Deprecated alias — preserved for callers that import the old name
normalize_tool_arguments = normalize_arguments
