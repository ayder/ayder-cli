"""Tool Registry — registration, schema queries, and dispatch.

Responsibilities (after Phase 2 decomposition):
1. Tool function registration and lookup.
2. Schema queries with optional capability-tag filtering.
3. Dispatch to the execution engine in tools/execution.py.
"""

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolResult
from ayder_cli.tools.definition import TOOL_DEFINITIONS
from ayder_cli.tools.execution import execute_tool
from ayder_cli.tools.hooks import HookManager
from ayder_cli.tools.normalization import normalize_arguments

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for tool functions with schema queries and execution dispatch."""

    def __init__(self, project_ctx: ProjectContext, process_manager: Any = None) -> None:
        self.project_ctx = project_ctx
        self.process_manager = process_manager
        self._registry: Dict[str, Callable] = {}
        self._dynamic_definitions: list = []
        self.hooks = HookManager()

    def register(self, name: str, func: Callable) -> None:
        self._registry[name] = func

    def register_dynamic_tool(self, tool_def: Any, handler: Callable) -> None:
        """Register a tool dynamically at runtime (e.g., call_agent).

        Adds the ToolDefinition to a per-instance list (included in schema
        queries), the handler to _registry (for execution dispatch), and
        the definition to the global name lookup (for SchemaValidator).
        """
        from ayder_cli.tools.definition import register_dynamic_definition

        self._dynamic_definitions.append(tool_def)
        self._registry[tool_def.name] = handler
        register_dynamic_definition(tool_def)

    def get_schemas(self, tags: frozenset | None = None) -> List[Dict[str, Any]]:
        all_defs = list(TOOL_DEFINITIONS) + self._dynamic_definitions
        if tags is None:
            return [td.to_openai_schema() for td in all_defs]
        return [td.to_openai_schema() for td in all_defs if set(td.tags) & tags]

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

    def get_system_prompts(self, tags: frozenset | None = None) -> str:
        """Return concatenated system_prompt blocks for enabled tools."""
        all_defs = list(TOOL_DEFINITIONS) + self._dynamic_definitions
        defs = all_defs if tags is None else [td for td in all_defs if set(td.tags) & tags]
        return "".join(td.system_prompt for td in defs if td.system_prompt)

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
    from ayder_cli.tools.definition import _PLUGIN_HANDLERS

    reg = ToolRegistry(project_ctx, process_manager=process_manager)
    for td in TOOL_DEFINITIONS:
        if td.name in _PLUGIN_HANDLERS:
            # External plugin — use pre-resolved handler
            reg.register(td.name, _PLUGIN_HANDLERS[td.name])
        else:
            # Builtin — resolve func_ref as before
            func = _resolve_func_ref(td.func_ref)
            reg.register(td.name, func)

    # Phase 2: Load project-local plugins
    project_path = project_ctx.root
    _load_project_plugins(reg, project_path)

    return reg


def _load_project_plugins(reg: ToolRegistry, project_path: Path) -> None:
    """Load project-local plugins and register them dynamically."""
    from ayder_cli.tools.plugin_manager import (
        load_plugin_definitions,
        PROJECT_PLUGINS_DIR_NAME,
        GLOBAL_PLUGINS_DIR,
    )

    plugins_dir = project_path / PROJECT_PLUGINS_DIR_NAME
    if not plugins_dir.exists():
        return

    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name == "plugins.json":
            continue
        toml_path = plugin_dir / "plugin.toml"
        if not toml_path.exists():
            continue

        try:
            # Check for plugin-name conflict with global plugins
            if GLOBAL_PLUGINS_DIR.exists() and (GLOBAL_PLUGINS_DIR / plugin_dir.name).exists():
                raise ValueError(
                    f"Plugin name conflict: '{plugin_dir.name}' exists in both "
                    f"global and project-local plugins"
                )

            defs, handlers = load_plugin_definitions(plugin_dir)

            # Pre-check all names before registering any
            existing_names = set(reg.get_registered_tools())
            for td in defs:
                if td.name in existing_names:
                    raise ValueError(
                        f"Tool name conflict: '{td.name}' from project plugin "
                        f"'{plugin_dir.name}' conflicts with an existing tool"
                    )

            # All checks passed — register all
            for td in defs:
                reg.register_dynamic_tool(td, handlers[td.name])

            logger.info(
                f"Loaded project plugin '{plugin_dir.name}' ({len(defs)} tools)"
            )
        except Exception as e:
            logger.warning(f"Skipping project plugin '{plugin_dir.name}': {e}")
