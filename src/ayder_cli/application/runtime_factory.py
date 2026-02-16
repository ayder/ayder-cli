"""Shared runtime composition factory for CLI and TUI.

Creates all runtime components from a single composition root,
eliminating the duplicate `_build_services()` / `AyderApp.__init__()` wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from ayder_cli.core.config import Config, load_config
from ayder_cli.core.context import ProjectContext
from ayder_cli.services.llm import LLMProvider, create_llm_provider
from ayder_cli.services.tools.executor import ToolExecutor
from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.process_manager import ProcessManager
from ayder_cli.checkpoint_manager import CheckpointManager
from ayder_cli.memory import MemoryManager
from ayder_cli.prompts import SYSTEM_PROMPT, PROJECT_STRUCTURE_MACRO_TEMPLATE


@dataclass
class RuntimeComponents:
    """All runtime dependencies assembled by create_runtime()."""

    config: Config
    llm_provider: LLMProvider
    process_manager: ProcessManager
    project_ctx: ProjectContext
    tool_registry: ToolRegistry
    tool_executor: ToolExecutor
    checkpoint_manager: CheckpointManager
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

    effective_model = model_name or cfg.model

    llm_provider = create_llm_provider(cfg)
    project_ctx = ProjectContext(project_root)
    process_manager = ProcessManager(max_processes=cfg.max_background_processes)
    tool_registry = create_default_registry(project_ctx, process_manager=process_manager)
    tool_executor = ToolExecutor(tool_registry)
    checkpoint_manager = CheckpointManager(project_ctx)
    memory_manager = MemoryManager(
        project_ctx,
        llm_provider=llm_provider,
        tool_executor=tool_executor,
        checkpoint_manager=checkpoint_manager,
    )

    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
    except Exception:
        macro = ""

    system_prompt = SYSTEM_PROMPT.format(model_name=effective_model) + macro

    return RuntimeComponents(
        config=cfg,
        llm_provider=llm_provider,
        process_manager=process_manager,
        project_ctx=project_ctx,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        checkpoint_manager=checkpoint_manager,
        memory_manager=memory_manager,
        system_prompt=system_prompt,
    )
