"""
Tool definitions for utility operations.

Tools: manage_environment_vars
"""

from typing import Tuple

from .definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="manage_environment_vars",
        description="Manage .env files: load, validate, generate secure values, and set environment variables.",
        description_template="Environment variables will be {mode}d",
        tags=("core",),
        func_ref="ayder_cli.tools.utils_tools:manage_environment_vars",
        parameters={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["validate", "load", "generate", "set"],
                    "description": "Operation mode: 'validate' (check if variable exists), 'load' (display all variables), 'generate' (create secure random value), 'set' (update variable with specific value)",
                },
                "variable_name": {
                    "type": "string",
                    "description": "Variable name (required for validate/generate/set modes)",
                },
                "value": {
                    "type": "string",
                    "description": "Variable value (required for set mode only)",
                },
            },
            "required": ["mode"],
        },
        permission="w",
        safe_mode_blocked=False,
    ),
)