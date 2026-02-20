"""
Tool definitions for virtual environment operations.

Tools: create_virtualenv, install_requirements, list_virtualenvs, activate_virtualenv, remove_virtualenv
"""

from typing import Tuple

from .definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="create_virtualenv",
        description="Create a new Python virtual environment in the project directory",
        description_template="Virtual environment {env_name} will be created",
        tags=("venv",),
        func_ref="ayder_cli.tools.venv:create_virtualenv",
        parameters={
            "type": "object",
            "properties": {
                "env_name": {
                    "type": "string",
                    "description": "Name of the virtual environment directory (default: .venv)",
                    "default": ".venv",
                },
                "python_version": {
                    "type": "string",
                    "description": "Python version to use (default: 3.12)",
                    "default": "3.12",
                },
            },
            "required": [],
        },
        permission="x",
        safe_mode_blocked=False,
        parameter_aliases=(
            ("name", "env_name"),
            ("venv_name", "env_name"),
        ),
        path_parameters=("env_name",),
    ),
    ToolDefinition(
        name="install_requirements",
        description="Install project dependencies from requirements.txt or pyproject.toml into the virtual environment",
        description_template="Dependencies will be installed from {requirements_file} into {env_name}",
        tags=("venv",),
        func_ref="ayder_cli.tools.venv:install_requirements",
        parameters={
            "type": "object",
            "properties": {
                "requirements_file": {
                    "type": "string",
                    "description": "Path to requirements file (default: requirements.txt)",
                    "default": "requirements.txt",
                },
                "env_name": {
                    "type": "string",
                    "description": "Name of the virtual environment (default: .venv)",
                    "default": ".venv",
                },
            },
            "required": [],
        },
        permission="x",
        safe_mode_blocked=False,
        parameter_aliases=(
            ("req_file", "requirements_file"),
            ("reqs", "requirements_file"),
        ),
        path_parameters=("requirements_file", "env_name"),
    ),
    ToolDefinition(
        name="list_virtualenvs",
        description="List all virtual environments in the project directory",
        description_template="Virtual environments will be listed",
        tags=("venv",),
        func_ref="ayder_cli.tools.venv:list_virtualenvs",
        parameters={
            "type": "object",
            "properties": {},
        },
        permission="r",
        safe_mode_blocked=False,
    ),
    ToolDefinition(
        name="activate_virtualenv",
        description="Get activation instructions for a virtual environment",
        description_template="Activation instructions for {env_name} will be provided",
        tags=("venv",),
        func_ref="ayder_cli.tools.venv:activate_virtualenv",
        parameters={
            "type": "object",
            "properties": {
                "env_name": {
                    "type": "string",
                    "description": "Name of the virtual environment (default: .venv)",
                    "default": ".venv",
                },
            },
            "required": [],
        },
        permission="r",
        safe_mode_blocked=False,
        parameter_aliases=(("name", "env_name"),),
        path_parameters=("env_name",),
    ),
    ToolDefinition(
        name="remove_virtualenv",
        description="Remove/uninstall a virtual environment",
        description_template="Virtual environment {env_name} will be removed",
        tags=("venv",),
        func_ref="ayder_cli.tools.venv:remove_virtualenv",
        parameters={
            "type": "object",
            "properties": {
                "env_name": {
                    "type": "string",
                    "description": "Name of the virtual environment to remove (default: .venv)",
                    "default": ".venv",
                },
                "force": {
                    "type": "boolean",
                    "description": "Skip confirmation prompt and remove directly (default: false)",
                    "default": False,
                },
            },
            "required": [],
        },
        permission="x",
        safe_mode_blocked=False,
        parameter_aliases=(("name", "env_name"),),
        path_parameters=("env_name",),
    ),
)