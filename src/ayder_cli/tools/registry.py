"""
Tool Registry Module

Provides a registry pattern for tool execution, replacing the if/elif dispatch block.
"""

import json
import inspect
import logging
from pathlib import Path
from typing import Callable, Dict, Tuple, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

from ayder_cli.tools.definition import TOOL_DEFINITIONS, TOOL_DEFINITIONS_BY_NAME
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError, ToolResult

logger = logging.getLogger(__name__)


# Type alias for middleware functions
MiddlewareFunc = Callable[[str, Dict[str, Any]], None]


class ToolExecutionStatus(Enum):
    """Status of tool execution for callbacks."""

    STARTED = "started"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ToolExecutionResult:
    """Result object passed to callbacks."""

    tool_name: str
    arguments: Dict[str, Any]
    status: ToolExecutionStatus
    result: Optional[ToolResult] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


# Type aliases for callbacks
PreExecuteCallback = Callable[[str, Dict[str, Any]], None]
PostExecuteCallback = Callable[["ToolExecutionResult"], None]


# --- Parameter Normalization & Validation ---

# Parameter aliases: common variations → canonical names (generated from ToolDefinitions)
PARAMETER_ALIASES = {
    td.name: dict(td.parameter_aliases)
    for td in TOOL_DEFINITIONS
    if td.parameter_aliases
}

# Parameters that should be resolved to absolute paths (generated from ToolDefinitions)
PATH_PARAMETERS = {
    td.name: list(td.path_parameters) for td in TOOL_DEFINITIONS if td.path_parameters
}


def normalize_tool_arguments(
    tool_name: str, arguments: dict, project_ctx: ProjectContext
) -> dict:
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
        for param_name in PATH_PARAMETERS[tool_name]:
            if param_name in normalized and normalized[param_name]:
                try:
                    validated_path = project_ctx.validate_path(normalized[param_name])
                    normalized[param_name] = str(validated_path)
                except ValueError:
                    # Security error - let it propagate to caller
                    raise

    # Step 3: Type coercion for integer parameters (derived from schema)
    tool_def = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    if tool_def:
        props = tool_def.parameters.get("properties", {})
        for key, schema in props.items():
            if (
                schema.get("type") == "integer"
                and key in normalized
                and isinstance(normalized[key], str)
            ):
                try:
                    normalized[key] = int(normalized[key])
                except ValueError:
                    pass  # Keep as string, validation will catch it

    return normalized


def validate_tool_call(tool_name: str, arguments: dict) -> tuple:
    """
    Validate tool call against schema.
    Returns: (is_valid, error_message)

    Searches TOOL_DEFINITIONS_BY_NAME (all tools, regardless of mode)
    so that any registered tool can be validated.
    """
    td = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    if not td:
        return False, f"Unknown tool: {tool_name}"

    # Check required parameters
    params = td.parameters
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
            return (
                False,
                f"Parameter '{param_name}' must be an integer, got {type(value).__name__}",
            )
        if expected_type == "string" and not isinstance(value, str):
            return (
                False,
                f"Parameter '{param_name}' must be a string, got {type(value).__name__}",
            )

    return True, ""


# --- Shared Execution Logic ---


def _execute_tool_with_hooks(
    tool_name: str,
    arguments,
    tool_func_getter: Callable[[str], Callable],
    middlewares: List[MiddlewareFunc],
    pre_execute_callbacks: List[PreExecuteCallback],
    post_execute_callbacks: List[PostExecuteCallback],
    project_ctx: ProjectContext,
    process_manager=None,
) -> ToolResult:
    """
    Execute a tool with the full execution pipeline (normalization, validation, callbacks).
    """
    import time

    # Handle arguments being passed as a string (JSON) or a dict
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return ToolError(
                f"Error: Invalid JSON arguments for {tool_name}", "validation"
            )
    else:
        args = arguments

    # Normalize parameters (apply aliases, resolve paths, coerce types)
    try:
        args = normalize_tool_arguments(tool_name, args, project_ctx)
    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")

    # Validate before execution
    is_valid, error_msg = validate_tool_call(tool_name, args)
    if not is_valid:
        return ToolError(f"Validation Error: {error_msg}", "validation")

    # Get the tool function
    tool_func = tool_func_getter(tool_name)
    if tool_func is None:
        return ToolError(f"Error: Unknown tool '{tool_name}'", "validation")

    # Run pre-execute callbacks
    for callback in pre_execute_callbacks:
        try:
            callback(tool_name, args)
        except Exception as e:
            logger.warning(f"Pre-execute callback failed for {tool_name}: {e}")

    # Run middlewares (pre-execution checks)
    for middleware in middlewares:
        try:
            middleware(tool_name, args)
        except PermissionError:
            raise
        except Exception as e:
            logger.warning(f"Middleware failed for {tool_name}: {e}")

    # Inject dependencies if the tool function expects them
    sig = inspect.signature(tool_func)
    call_args = args.copy()
    if "project_ctx" in sig.parameters:
        call_args["project_ctx"] = project_ctx
    if "process_manager" in sig.parameters and process_manager is not None:
        call_args["process_manager"] = process_manager

    # Execute the tool with timing
    start_time = time.time()

    try:
        result = tool_func(**call_args)
        status = ToolExecutionStatus.SUCCESS
        error = None
    except Exception as e:
        result = ToolError(f"Error executing {tool_name}: {str(e)}", "execution")
        status = ToolExecutionStatus.ERROR
        error = str(e)

    duration_ms = (time.time() - start_time) * 1000

    # Run post-execute callbacks
    execution_result = ToolExecutionResult(
        tool_name=tool_name,
        arguments=args,  # Pass original args (without injected context)
        status=status,
        result=result,
        error=error,
        duration_ms=duration_ms,
    )

    for callback in post_execute_callbacks:
        try:
            callback(execution_result)
        except Exception:
            pass

    return result


class ToolRegistry:
    """
    Registry for managing and executing tool functions with middleware support.
    """

    def __init__(self, project_ctx: ProjectContext, process_manager=None):
        """Initialize registry with project context."""
        self.project_ctx = project_ctx
        self.process_manager = process_manager
        self._registry: Dict[str, Callable] = {}
        self._middlewares: List[MiddlewareFunc] = []
        self._pre_execute_callbacks: List[PreExecuteCallback] = []
        self._post_execute_callbacks: List[PostExecuteCallback] = []

    def register(self, name: str, func: Callable) -> None:
        self._registry[name] = func

    def add_middleware(self, middleware: MiddlewareFunc) -> None:
        self._middlewares.append(middleware)

    def remove_middleware(self, middleware: MiddlewareFunc) -> None:
        if middleware in self._middlewares:
            self._middlewares.remove(middleware)

    def clear_middlewares(self) -> None:
        self._middlewares.clear()

    def get_middlewares(self) -> List[MiddlewareFunc]:
        return self._middlewares.copy()

    def add_pre_execute_callback(self, callback: PreExecuteCallback) -> None:
        self._pre_execute_callbacks.append(callback)

    def add_post_execute_callback(self, callback: PostExecuteCallback) -> None:
        self._post_execute_callbacks.append(callback)

    def remove_pre_execute_callback(self, callback: PreExecuteCallback) -> None:
        if callback in self._pre_execute_callbacks:
            self._pre_execute_callbacks.remove(callback)

    def remove_post_execute_callback(self, callback: PostExecuteCallback) -> None:
        if callback in self._post_execute_callbacks:
            self._post_execute_callbacks.remove(callback)

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Return all tool schemas."""
        return [td.to_openai_schema() for td in TOOL_DEFINITIONS]

    def _get_tool_func(self, name: str) -> Optional[Callable]:
        return self._registry.get(name)

    def execute(self, name: str, arguments) -> ToolResult:
        return _execute_tool_with_hooks(
            tool_name=name,
            arguments=arguments,
            tool_func_getter=self._get_tool_func,
            middlewares=self._middlewares,
            pre_execute_callbacks=self._pre_execute_callbacks,
            post_execute_callbacks=self._post_execute_callbacks,
            project_ctx=self.project_ctx,
            process_manager=self.process_manager,
        )

    def get_registered_tools(self) -> list:
        return list(self._registry.keys())

    def normalize_args(self, name: str, arguments: dict) -> dict:
        """Normalize arguments using the registry's project context."""
        return normalize_tool_arguments(name, arguments, self.project_ctx)

    def validate_args(self, name: str, arguments: dict) -> tuple:
        """Validate arguments against schema."""
        return validate_tool_call(name, arguments)


def _resolve_func_ref(func_ref: str) -> Callable:
    """Import and return a function from a 'module.path:function_name' reference."""
    import importlib

    module_path, func_name = func_ref.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def create_default_registry(
    project_ctx: ProjectContext, process_manager=None
) -> ToolRegistry:
    """
    Create and configure a ToolRegistry with all available tools.

    Tool functions are auto-discovered from TOOL_DEFINITIONS via func_ref.
    """
    registry = ToolRegistry(project_ctx, process_manager=process_manager)

    for td in TOOL_DEFINITIONS:
        func = _resolve_func_ref(td.func_ref)
        registry.register(td.name, func)

    return registry
