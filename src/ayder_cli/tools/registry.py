"""Tool Registry — registration, schema queries, and dispatch.

Responsibilities (after Phase 2 decomposition):
1. Tool function registration and lookup.
2. Schema queries with optional capability-tag filtering.
3. Dispatch to the execution engine in tools/execution.py.
"""

import importlib
import logging
from typing import Any, Callable, Dict, List

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolResult
from ayder_cli.tools.definition import TOOL_DEFINITIONS
from ayder_cli.tools.execution import execute_tool
from ayder_cli.tools.hooks import HookManager
from ayder_cli.tools.normalization import normalize_arguments

logger = logging.getLogger(__name__)

# Deprecated module-level alias (callers that import this name still work)
normalize_tool_arguments = normalize_arguments


class ToolRegistry:
    """Registry for tool functions with schema queries and execution dispatch."""

    def __init__(self, project_ctx: ProjectContext, process_manager: Any = None) -> None:
        self.project_ctx = project_ctx
        self.process_manager = process_manager
        self._registry: Dict[str, Callable] = {}
        self.hooks = HookManager()

    def register(self, name: str, func: Callable) -> None:
        self._registry[name] = func

    def get_schemas(self, tags: frozenset | None = None) -> List[Dict[str, Any]]:
        if tags is None:
            return [td.to_openai_schema() for td in TOOL_DEFINITIONS]
        return [td.to_openai_schema() for td in TOOL_DEFINITIONS if set(td.tags) & tags]

    def execute(self, name: str, arguments: Any) -> ToolResult:
        tool_func = self._registry.get(name)
        return execute_tool(
            tool_name=name,
            arguments=arguments,
            tool_func=tool_func,
            hook_manager=self.hooks,
            project_ctx=self.project_ctx,
            process_manager=self.process_manager,
        )

    def get_registered_tools(self) -> list:
        return list(self._registry.keys())

    # -- Hook convenience delegates ------------------------------------------

    def add_middleware(self, mw: Callable) -> None:
        self.hooks.add_middleware(mw)

    def remove_middleware(self, mw: Callable) -> None:
        self.hooks.remove_middleware(mw)

    def clear_middlewares(self) -> None:
        self.hooks.clear_middlewares()

    def get_middlewares(self) -> list:
        return self.hooks.get_middlewares()

    def add_pre_execute_callback(self, cb: Callable) -> None:
        self.hooks.add_pre_callback(cb)

    def add_post_execute_callback(self, cb: Callable) -> None:
        self.hooks.add_post_callback(cb)

    def remove_pre_execute_callback(self, cb: Callable) -> None:
        self.hooks.remove_pre_callback(cb)

    def remove_post_execute_callback(self, cb: Callable) -> None:
        self.hooks.remove_post_callback(cb)

    # -- Deprecated methods --------------------------------------------------

    def normalize_args(self, name: str, arguments: dict) -> dict:
        return normalize_arguments(name, arguments, self.project_ctx)


def _resolve_func_ref(func_ref: str) -> Callable:
    """Import and return a callable from a ``'module.path:function_name'`` ref."""
    module_path, func_name = func_ref.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, func_name)


def create_default_registry(
    project_ctx: ProjectContext, process_manager: Any = None
) -> ToolRegistry:
    """Create a ToolRegistry with all tools from TOOL_DEFINITIONS auto-registered."""
    reg = ToolRegistry(project_ctx, process_manager=process_manager)
    for td in TOOL_DEFINITIONS:
        func = _resolve_func_ref(td.func_ref)
        reg.register(td.name, func)
    return reg
