"""Shared runtime composition factory for CLI and TUI.

Creates all runtime components from a single composition root,
eliminating the duplicate `_build_services()` / `AyderApp.__init__()` wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ayder_cli.core.config import Config, load_config, load_config_for_provider
from ayder_cli.core.context_manager_factory import context_manager_factory

if TYPE_CHECKING:
    from ayder_cli.agents.config import AgentConfig
from ayder_cli.core.context import ProjectContext
from ayder_cli.providers import AIProvider, provider_orchestrator
from ayder_cli.providers.retry import RetryConfig, RetryingProvider
from ayder_cli.tools.registry import ToolRegistry, create_default_registry
from ayder_cli.process_manager import ProcessManager
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
    system_prompt: str
    context_manager: Any = field(default=None)  # ContextManagerProtocol


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

    llm_provider: AIProvider = provider_orchestrator.create(cfg)
    project_ctx = ProjectContext(project_root)
    process_manager = ProcessManager(max_processes=cfg.max_background_processes)
    tool_registry = create_default_registry(project_ctx, process_manager=process_manager)

    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
    except Exception:
        macro = ""

    # Format the final prompt (protocol injection now handled dynamically by chat_loop and protocols)
    base_prompt = get_system_prompt(cfg.prompt)
    tool_tags = frozenset(cfg.tool_tags) if cfg.tool_tags else None
    tool_prompts = tool_registry.get_system_prompts(tags=tool_tags)
    system_prompt = base_prompt + tool_prompts + macro

    # Create context manager and freeze system prompt
    context_mgr = context_manager_factory.create(cfg)
    tool_schemas = tool_registry.get_schemas(tags=tool_tags)
    context_mgr.freeze_system_prompt(system_prompt, tool_schemas)

    llm_provider = _maybe_wrap_with_retry(llm_provider, cfg, context_mgr)

    return RuntimeComponents(
        config=cfg,
        llm_provider=llm_provider,
        process_manager=process_manager,
        project_ctx=project_ctx,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
        context_manager=context_mgr,
    )


def _maybe_wrap_with_retry(
    provider: AIProvider, cfg: Config, context_mgr: Any
) -> AIProvider:
    """Wrap provider with RetryingProvider when cfg.retry.enabled.

    Wires CacheMonitor.reset() as the on_reconnect hook for drivers whose
    context manager exposes ``_cache_monitor`` (currently OllamaContextManager).
    """
    if not cfg.retry.enabled:
        return provider
    retry_cfg = RetryConfig(
        enabled=cfg.retry.enabled,
        max_attempts=cfg.retry.max_attempts,
        initial_delay_seconds=cfg.retry.initial_delay_seconds,
        max_delay_seconds=cfg.retry.max_delay_seconds,
        backoff_coefficient=cfg.retry.backoff_coefficient,
        jitter=cfg.retry.jitter,
        retry_on_names=cfg.retry.retry_on_names,
    )
    on_reconnect = None
    monitor = getattr(context_mgr, "_cache_monitor", None)
    if monitor is not None and hasattr(monitor, "reset"):
        on_reconnect = monitor.reset
    return RetryingProvider(provider, retry_cfg, on_reconnect=on_reconnect)


def create_agent_runtime(
    *,
    agent_config: "AgentConfig",
    parent_config: Config,
    project_ctx: "ProjectContext",
    process_manager: "ProcessManager",
    permissions: set[str],
) -> RuntimeComponents:
    """Assemble runtime components for a single agent run.

    Does NOT call create_runtime() — assembles components directly.
    Shares ProcessManager and ProjectContext with parent; isolates
    AIProvider, ToolRegistry, and ContextManager.

    Args:
        agent_config: Agent-specific configuration.
        parent_config: Parent's Config for inheriting provider/model defaults.
        project_ctx: Shared project context (same project for all agents).
        process_manager: Shared process manager (global process limit).
        permissions: Global permission set from ExecutionPolicy.

    Returns:
        RuntimeComponents with agent-specific wiring.
    """

    # 1. Resolve provider config
    if agent_config.provider:
        cfg = load_config_for_provider(agent_config.provider)
    else:
        cfg = parent_config

    # 2. Apply model override
    if agent_config.model:
        cfg = cfg.model_copy(update={"model": agent_config.model})

    # 3. Create isolated AIProvider
    llm_provider = provider_orchestrator.create(cfg)

    # 4. Create isolated ToolRegistry (shared PM and ProjectContext)
    tool_registry = create_default_registry(project_ctx, process_manager=process_manager)

    # 5. Build agent system prompt
    summary_suffix = (
        "\n\n---\nWhen you have completed your task, end your final response with "
        "a structured summary block:\n"
        "<agent-summary>\n"
        "FINDINGS: [what you found or accomplished]\n"
        "FILES_CHANGED: [list of files modified, or 'none']\n"
        "RECOMMENDATIONS: [any follow-up actions]\n"
        "</agent-summary>"
    )
    tool_tags = frozenset(cfg.tool_tags) if cfg.tool_tags else None
    tool_prompts = tool_registry.get_system_prompts(tags=tool_tags)
    system_prompt = agent_config.system_prompt + tool_prompts + summary_suffix

    # Create context manager and freeze agent system prompt
    context_mgr = context_manager_factory.create(cfg)
    tool_schemas = tool_registry.get_schemas(tags=tool_tags)
    context_mgr.freeze_system_prompt(system_prompt, tool_schemas)

    llm_provider = _maybe_wrap_with_retry(llm_provider, cfg, context_mgr)

    return RuntimeComponents(
        config=cfg,
        llm_provider=llm_provider,
        process_manager=process_manager,
        project_ctx=project_ctx,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
        context_manager=context_mgr,
    )
