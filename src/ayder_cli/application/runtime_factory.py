"""Shared runtime composition factory for CLI and TUI.

Creates all runtime components from a single composition root,
eliminating the duplicate `_build_services()` / `AyderApp.__init__()` wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from ayder_cli.core.config import Config, load_config
from ayder_cli.core.context import ProjectContext
from ayder_cli.services.llm import LLMProvider, create_llm_provider
from ayder_cli.services.interactions import (
    AutoApproveConfirmationPolicy,
    NullInteractionSink,
)
from ayder_cli.services.tools.executor import ToolExecutor as _ToolExecutor
from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.process_manager import ProcessManager
from ayder_cli.checkpoint_manager import CheckpointManager
from ayder_cli.memory import MemoryManager
from ayder_cli.prompts import SYSTEM_PROMPT, TOOL_PROTOCOL_BLOCK, PROJECT_STRUCTURE_MACRO_TEMPLATE


@dataclass
class RuntimeComponents:
    """All runtime dependencies assembled by create_runtime()."""

    config: Config
    llm_provider: LLMProvider
    process_manager: ProcessManager
    project_ctx: ProjectContext
    tool_registry: ToolRegistry
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

    if model_name:
        cfg = cfg.model_copy(update={"model": model_name})

    llm_provider = create_llm_provider(cfg)
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
    checkpoint_manager = CheckpointManager(project_ctx)
    memory_manager = MemoryManager(
        project_ctx,
        llm_provider=llm_provider,
        tool_executor=_tool_executor,
        checkpoint_manager=checkpoint_manager,
    )

    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
    except Exception:
        macro = ""

    # Inject XML TOOL PROTOCOL for OpenAI-compatible drivers (openai/ollama use custom
    # XML parsing). Anthropic and Gemini use native function-calling — the block adds
    # noise there.
    tool_protocol = TOOL_PROTOCOL_BLOCK if cfg.driver in ("openai", "ollama") else ""
    system_prompt = SYSTEM_PROMPT + tool_protocol + macro

    return RuntimeComponents(
        config=cfg,
        llm_provider=llm_provider,
        process_manager=process_manager,
        project_ctx=project_ctx,
        tool_registry=tool_registry,
        checkpoint_manager=checkpoint_manager,
        memory_manager=memory_manager,
        system_prompt=system_prompt,
    )
