"""
Tool Registry Module

Provides a registry pattern for tool execution, replacing the if/elif dispatch block.
"""

import json
from pathlib import Path
from typing import Callable, Dict, Tuple

from ayder_cli.tools.schemas import tools_schema
from ayder_cli.path_context import ProjectContext


# --- Module-level ProjectContext ---

_default_project_ctx = None


def get_project_context():
    """Get or create the default project context."""
    global _default_project_ctx
    if _default_project_ctx is None:
        _default_project_ctx = ProjectContext(".")
    return _default_project_ctx


# --- Parameter Normalization & Validation ---

# Parameter aliases: common variations → canonical names
PARAMETER_ALIASES = {
    "read_file": {"path": "file_path", "absolute_path": "file_path", "filepath": "file_path"},
    "write_file": {"path": "file_path", "absolute_path": "file_path", "filepath": "file_path"},
    "replace_string": {"path": "file_path", "absolute_path": "file_path", "filepath": "file_path"},
    "list_files": {"dir": "directory", "path": "directory", "folder": "directory"},
}

# Parameters that should be resolved to absolute paths
PATH_PARAMETERS = {
    "read_file": ["file_path"],
    "write_file": ["file_path"],
    "replace_string": ["file_path"],
    "list_files": ["directory"],
    "search_codebase": ["directory"],
}


def normalize_tool_arguments(tool_name: str, arguments: dict) -> dict:
    """
    Normalize arguments by:
    1. Applying parameter aliases (path → file_path)
    2. Resolving path parameters to absolute paths via ProjectContext (validates sandbox)
    3. Type coercion (string "10" → int 10 for line numbers)
    """
    normalized = dict(arguments)  # Copy to avoid mutation

    # Step 1: Apply aliases
    if tool_name in PARAMETER_ALIASES:
        for alias, canonical in PARAMETER_ALIASES[tool_name].items():
            if alias in normalized and canonical not in normalized:
                normalized[canonical] = normalized.pop(alias)

    # Step 2: Resolve paths to absolute using ProjectContext (validates sandbox)
    if tool_name in PATH_PARAMETERS:
        project = get_project_context()
        for param_name in PATH_PARAMETERS[tool_name]:
            if param_name in normalized and normalized[param_name]:
                try:
                    validated_path = project.validate_path(normalized[param_name])
                    normalized[param_name] = str(validated_path)
                except ValueError:
                    # Security error - let it propagate to caller
                    raise

    # Step 3: Type coercion for line numbers
    if tool_name == "read_file":
        for key in ["start_line", "end_line"]:
            if key in normalized and isinstance(normalized[key], str):
                try:
                    normalized[key] = int(normalized[key])
                except ValueError:
                    pass  # Keep as string, validation will catch it

    return normalized


def validate_tool_call(tool_name: str, arguments: dict) -> tuple:
    """
    Validate tool call against schema.
    Returns: (is_valid, error_message)
    """
    # Find tool schema
    tool_schema = None
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == tool_name:
            tool_schema = tool["function"]
            break

    if not tool_schema:
        return False, f"Unknown tool: {tool_name}"

    # Check required parameters
    params = tool_schema.get("parameters", {})
    required = params.get("required", [])
    missing = [p for p in required if p not in arguments or arguments[p] is None]

    if missing:
        return False, f"Missing required parameter(s): {', '.join(missing)}"

    # Type validation
    properties = params.get("properties", {})
    for param_name, value in arguments.items():
        if param_name not in properties:
            continue

        expected_type = properties[param_name].get("type")
        if expected_type == "integer" and not isinstance(value, int):
            return False, f"Parameter '{param_name}' must be an integer, got {type(value).__name__}"
        if expected_type == "string" and not isinstance(value, str):
            return False, f"Parameter '{param_name}' must be a string, got {type(value).__name__}"

    return True, ""


class ToolRegistry:
    """
    Registry for managing and executing tool functions.

    Provides a dictionary-based registry pattern for tool execution with
    built-in argument normalization and validation.
    """

    def __init__(self):
        """Initialize an empty tool registry."""
        self._registry: Dict[str, Callable] = {}

    def register(self, name: str, func: Callable) -> None:
        """
        Register a tool function with the given name.

        Args:
            name: The name of the tool (used for dispatch)
            func: The callable function to execute for this tool
        """
        self._registry[name] = func

    def execute(self, name: str, arguments) -> str:
        """
        Execute a registered tool with the given arguments.

        Handles:
        - JSON string parsing for arguments
        - Argument normalization (via normalize_tool_arguments)
        - Argument validation (via validate_tool_call)
        - Error handling for unknown tools

        Args:
            name: The name of the registered tool to execute
            arguments: Either a dict of arguments or a JSON string

        Returns:
            The result of the tool execution as a string
        """
        # Handle arguments being passed as a string (JSON) or a dict
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                return f"Error: Invalid JSON arguments for {name}"
        else:
            args = arguments

        # Normalize parameters (apply aliases, resolve paths, coerce types)
        args = normalize_tool_arguments(name, args)

        # Validate before execution
        is_valid, error_msg = validate_tool_call(name, args)
        if not is_valid:
            return f"Validation Error: {error_msg}"

        # Check if tool is registered
        if name not in self._registry:
            return f"Error: Unknown tool '{name}'"

        # Execute the tool
        tool_func = self._registry[name]
        return tool_func(**args)

    def get_registered_tools(self) -> list:
        """
        Get a list of all registered tool names.

        Returns:
            A list of registered tool names
        """
        return list(self._registry.keys())


def create_default_registry() -> ToolRegistry:
    """
    Create and configure a ToolRegistry with all available tools.

    Registers all file system tools, task management tools, and code navigation tools.

    Returns:
        A fully configured ToolRegistry instance
    """
    from ayder_cli.tools.impl import (
        list_files,
        read_file,
        write_file,
        replace_string,
        run_shell_command,
        get_project_structure,
        search_codebase,
    )
    from ayder_cli.tasks import create_task, show_task, implement_task, implement_all_tasks

    registry = ToolRegistry()

    # Register file system tools
    registry.register("list_files", list_files)
    registry.register("read_file", read_file)
    registry.register("write_file", write_file)
    registry.register("replace_string", replace_string)
    registry.register("run_shell_command", run_shell_command)

    # Register code navigation tools
    registry.register("get_project_structure", get_project_structure)
    registry.register("search_codebase", search_codebase)

    # Register task management tools
    registry.register("create_task", create_task)
    registry.register("show_task", show_task)
    registry.register("implement_task", implement_task)
    registry.register("implement_all_tasks", implement_all_tasks)

    return registry


# Global default registry instance (lazy initialization)
_default_registry = None


class _MockableToolRegistry(ToolRegistry):
    """
    Special registry that looks up task functions dynamically from fs_tools module.
    This allows tests to mock functions in fs_tools and have the mocks take effect.
    """
    
    def execute(self, name: str, arguments) -> str:
        """Execute with dynamic function lookup for task tools."""
        # Handle arguments being passed as a string (JSON) or a dict
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                return f"Error: Invalid JSON arguments for {name}"
        else:
            args = arguments

        # Normalize parameters (apply aliases, resolve paths, coerce types)
        args = normalize_tool_arguments(name, args)

        # Validate before execution
        is_valid, error_msg = validate_tool_call(name, args)
        if not is_valid:
            return f"Validation Error: {error_msg}"

        # For task tools, look them up dynamically from fs_tools for mockability
        if name in ("create_task", "show_task", "implement_task", "implement_all_tasks"):
            # Import at call time to allow mocking
            from ayder_cli import fs_tools as fs
            
            func_map = {
                "create_task": fs.create_task,
                "show_task": fs.show_task,
                "implement_task": fs.implement_task,
                "implement_all_tasks": fs.implement_all_tasks,
            }
            tool_func = func_map.get(name)
            if tool_func is None:
                return f"Error: Unknown tool '{name}'"
            return tool_func(**args)
        
        # For other tools, use standard registry lookup
        if name not in self._registry:
            return f"Error: Unknown tool '{name}'"
        
        tool_func = self._registry[name]
        return tool_func(**args)


def _get_default_registry() -> ToolRegistry:
    """Get or create the default tool registry with mockable task functions."""
    global _default_registry
    if _default_registry is None:
        from ayder_cli.tools.impl import (
            list_files,
            read_file,
            write_file,
            replace_string,
            run_shell_command,
            get_project_structure,
            search_codebase,
        )
        
        # Create mockable registry
        registry = _MockableToolRegistry()
        
        # Register file system tools
        registry.register("list_files", list_files)
        registry.register("read_file", read_file)
        registry.register("write_file", write_file)
        registry.register("replace_string", replace_string)
        registry.register("run_shell_command", run_shell_command)
        registry.register("get_project_structure", get_project_structure)
        registry.register("search_codebase", search_codebase)
        
        # Task tools are handled dynamically in _MockableToolRegistry.execute()
        
        _default_registry = registry
    return _default_registry


def execute_tool_call(tool_name: str, arguments):
    """
    Execute a tool call using the default registry.
    
    This is a convenience function that uses a singleton registry instance.
    For testing or custom registries, use ToolRegistry.execute() directly.
    
    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments (dict or JSON string)
        
    Returns:
        Result of the tool execution as a string
    """
    registry = _get_default_registry()
    return registry.execute(tool_name, arguments)
