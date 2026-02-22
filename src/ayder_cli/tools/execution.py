"""Tool execution engine — the full execution pipeline.

Extracted from tools/registry.py. Single responsibility: run a tool function
through the complete pipeline (JSON parse → normalize → hooks →
dependency injection → execute → post-hooks).

Schema validation is handled upstream by ValidationAuthority → SchemaValidator.
"""

import inspect
import json
import logging
import time
from typing import Any, Callable, Optional

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolResult
from ayder_cli.tools.hooks import HookManager, ToolExecutionResult, ToolExecutionStatus
from ayder_cli.tools.normalization import normalize_arguments

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Execution pipeline
# ---------------------------------------------------------------------------


def execute_tool(
    tool_name: str,
    arguments: Any,
    tool_func: Optional[Callable],
    hook_manager: HookManager,
    project_ctx: ProjectContext,
    process_manager: Any = None,
) -> ToolResult:
    """Execute a tool through the full pipeline.

    Pipeline:
    1. Parse JSON arguments (if passed as string).
    2. Normalize arguments (aliases, path resolution, type coercion).
    3. Check tool_func is not None — returns "Unknown tool" error if None.
    4. Run pre-execute callbacks (failures logged, not raised).
    5. Run middlewares (PermissionError re-raised; others logged).
    6. Inject dependencies (``project_ctx``, ``process_manager``) via signature inspection.
    7. Execute with timing.
    8. Run post-execute callbacks (failures logged, not raised).
    9. Return result.

    Schema validation is handled upstream by ValidationAuthority → SchemaValidator
    before this function is called.

    Args:
        tool_name: Registered tool name.
        arguments: dict or JSON string.
        tool_func: The resolved callable (may be None for unknown tools).
        hook_manager: Manages middleware and callbacks.
        project_ctx: Project context for path sandboxing.
        process_manager: Optional process manager injected for shell tools.

    Returns:
        ``ToolSuccess`` or ``ToolError``.
    """
    # Step 1: Parse JSON string arguments
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return ToolError(
                f"Error: Invalid JSON arguments for {tool_name}", "validation"
            )
    else:
        args = dict(arguments)

    # Step 2: Normalize (aliases, paths, type coercion)
    try:
        args = normalize_arguments(tool_name, args, project_ctx)
    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")

    # Step 3: Check tool function exists
    if tool_func is None:
        return ToolError(f"Error: Unknown tool '{tool_name}'", "validation")

    # Step 4: Pre-execute callbacks
    hook_manager.run_pre_callbacks(tool_name, args)

    # Step 5: Middlewares (PermissionError propagates)
    hook_manager.run_middlewares(tool_name, args)

    # Step 6: Dependency injection
    sig = inspect.signature(tool_func)
    call_args = args.copy()
    if "project_ctx" in sig.parameters:
        call_args["project_ctx"] = project_ctx
    if "process_manager" in sig.parameters and process_manager is not None:
        call_args["process_manager"] = process_manager

    # Step 7: Execute with timing
    logger.debug(f"Tool call: {tool_name}  args={args}")
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

    # Step 8: Post-execute callbacks
    exec_result = ToolExecutionResult(
        tool_name=tool_name,
        arguments=args,
        status=status,
        result=result,
        error=error,
        duration_ms=duration_ms,
    )
    hook_manager.run_post_callbacks(exec_result)

    return result
