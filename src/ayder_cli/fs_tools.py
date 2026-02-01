import json
from pathlib import Path
from ayder_cli.tasks import create_task, show_task, implement_task, implement_all_tasks

# --- 1. Tool Implementations ---
# Implementations are now in ayder_cli.tools.impl
# Re-exported here for backwards compatibility

from ayder_cli.tools.impl import (
    list_files,
    read_file,
    write_file,
    replace_string,
    run_shell_command,
    get_project_structure,
    search_codebase,
)

# --- 2. Tool Definitions (JSON Schema) ---
# Schemas are now maintained in ayder_cli.tools.schemas
# Re-exported here for backwards compatibility

from ayder_cli.tools import tools_schema

# --- 2.5. Parameter Normalization & Validation ---
# Now maintained in ayder_cli.tools.registry
# Re-exported here for backwards compatibility

from ayder_cli.tools import (
    normalize_tool_arguments,
    validate_tool_call,
    PARAMETER_ALIASES,
    PATH_PARAMETERS,
)


# --- 3. Helper to Execute Tools ---

# Tool dispatch mapping (maps tool names to function lookups)
# Using lambda to ensure functions are looked up at call time (supports mocking in tests)
_TOOL_DISPATCH = {
    "list_files": lambda: list_files,
    "read_file": lambda: read_file,
    "write_file": lambda: write_file,
    "replace_string": lambda: replace_string,
    "run_shell_command": lambda: run_shell_command,
    "get_project_structure": lambda: get_project_structure,
    "search_codebase": lambda: search_codebase,
    "create_task": lambda: create_task,
    "show_task": lambda: show_task,
    "implement_task": lambda: implement_task,
    "implement_all_tasks": lambda: implement_all_tasks,
}

# Global registry instance (lazy initialization)
_default_registry = None


def _get_default_registry():
    """Lazy initialization of the default tool registry."""
    global _default_registry
    if _default_registry is None:
        from ayder_cli.tools.registry import ToolRegistry

        # Create a custom registry that looks up functions dynamically
        class DynamicToolRegistry(ToolRegistry):
            def __init__(self, dispatch_map):
                super().__init__()
                self._dispatch_map = dispatch_map

            def execute(self, name, arguments):
                """Execute with dynamic function lookup."""
                # Handle arguments being passed as a string (JSON) or a dict
                if isinstance(arguments, str):
                    try:
                        args = json.loads(arguments)
                    except json.JSONDecodeError:
                        return f"Error: Invalid JSON arguments for {name}"
                else:
                    args = arguments

                # Normalize parameters (apply aliases, resolve paths, coerce types)
                from ayder_cli.tools.registry import normalize_tool_arguments, validate_tool_call
                args = normalize_tool_arguments(name, args)

                # Validate before execution
                is_valid, error_msg = validate_tool_call(name, args)
                if not is_valid:
                    return f"Validation Error: {error_msg}"

                # Check if tool is registered and get function dynamically
                if name not in self._dispatch_map:
                    return f"Error: Unknown tool '{name}'"

                # Look up function at call time (supports mocking)
                tool_func = self._dispatch_map[name]()
                return tool_func(**args)

        _default_registry = DynamicToolRegistry(_TOOL_DISPATCH)
    return _default_registry


def execute_tool_call(tool_name, arguments):
    """Executes a tool call based on name and arguments."""
    registry = _get_default_registry()
    return registry.execute(tool_name, arguments)