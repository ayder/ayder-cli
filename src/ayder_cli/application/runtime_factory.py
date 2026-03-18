"""Shared runtime composition factory for CLI and TUI.

Creates all runtime components from a single composition root,
eliminating the duplicate `_build_services()` / `AyderApp.__init__()` wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from ayder_cli.core.config import Config, load_config
from ayder_cli.core.context import ProjectContext
from ayder_cli.providers import AIProvider, provider_orchestrator
from ayder_cli.services.interactions import (
    AutoApproveConfirmationPolicy,
    NullInteractionSink,
)
from ayder_cli.services.tools.executor import ToolExecutor as _ToolExecutor
from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.process_manager import ProcessManager
from ayder_cli.memory import MemoryManager
from ayder_cli.prompts import (
    get_system_prompt,
    PROJECT_STRUCTURE_MACRO_TEMPLATE,
)


@dataclass
class RuntimeComponents:
    """All runtime dependencies assembled by create_runtime()."""

    config: Config
    llm_provider: AIProvider
    process_manager: ProcessManager
    project_ctx: ProjectContext
    tool_registry: ToolRegistry
    memory_manager: MemoryManager
    system_prompt: str


def create_runtime(
    *,
    config: Config | None = None,
    project_root: str = ".",
    model_name: str | None = None,
) -> RuntimeComponents:
    """Assemble and return all shared runtime components.

    Args:
        config: Pre-built Config object; loads from disk if None.
        project_root: Project root directory (default: current directory).
        model_name: Override model name from config when provided.

    Returns:
        RuntimeComponents with all dependencies wired.
    """
    cfg = config or load_config()

    if model_name:
        cfg = cfg.model_copy(update={"model": model_name})

    llm_provider = provider_orchestrator.create(cfg)
    project_ctx = ProjectContext(project_root)
    process_manager = ProcessManager(max_processes=cfg.max_background_processes)
    tool_registry = create_default_registry(project_ctx, process_manager=process_manager)
    # ToolExecutor is still needed internally by MemoryManager for checkpoint
    # LLM calls (it uses tool_executor.execute_tool_calls to save summaries).
    # It is NOT exposed in RuntimeComponents.
    _tool_executor = _ToolExecutor(
        tool_registry,
        interaction_sink=NullInteractionSink(),
        confirmation_policy=AutoApproveConfirmationPolicy(),
    )
    memory_manager = MemoryManager(
        project_ctx,
        llm_provider=llm_provider,
        tool_executor=_tool_executor,
    )

    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
    except Exception:
        macro = ""

    # Format the final prompt (protocol injection now handled dynamically by chat_loop and protocols)
    base_prompt = get_system_prompt(cfg.prompt)
    tool_tags = frozenset(cfg.tool_tags) if getattr(cfg, "tool_tags", None) else None
    tool_prompts = tool_registry.get_system_prompts(tags=tool_tags)
    system_prompt = base_prompt + tool_prompts + macro

    return RuntimeComponents(
        config=cfg,
        llm_provider=llm_provider,
        process_manager=process_manager,
        project_ctx=project_ctx,
        tool_registry=tool_registry,
        memory_manager=memory_manager,
        system_prompt=system_prompt,
    )
