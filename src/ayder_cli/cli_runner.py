"""CLI command runners for single-command execution and task management.

This module contains the logic for running the CLI in different modes:
- Single command execution (run_command)
- Task management commands (_run_tasks_cli, _run_implement_cli, _run_implement_all_cli)

All CLI paths drive ChatLoop via CliCallbacks, sharing the same async
execution engine used by the TUI.
"""

import asyncio
import logging
import sys
from pathlib import Path

from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.tool import (
    AGENT_TOOL_DEFINITION,
    create_agent_handler,
)
from ayder_cli.application.runtime_factory import create_runtime
from ayder_cli.providers import ProviderUnavailableError
from ayder_cli.cli_callbacks import CliCallbacks
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

logger = logging.getLogger(__name__)


def _run_loop(
    prompt: str,
    permissions: set | None = None,
    agent_mode: bool = False,
    system_prompt_override: str | None = None,
) -> int:
    """Create a ChatLoop with CliCallbacks and run it.

    Shared helper used by CommandRunner, TaskRunner._execute_task, and
    TaskRunner.implement_all.

    Args:
        prompt: The user prompt to send to the loop.
        permissions: Granted permission categories.
        agent_mode: When True, inject the AGENTIC orchestrator system prompt
            (ayder-cli --agent) so the main LLM drives the multi-agent harness.
        system_prompt_override: When set, use this text as the system prompt base
            instead of the built-in prompts.py prompt (ayder --system-prompt FILE).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    rt = create_runtime(
        prompt_tier="AGENTIC" if agent_mode else None,
        system_prompt_override=system_prompt_override,
    )

    messages: list[dict] = [
        {"role": "system", "content": rt.system_prompt},
        {"role": "user", "content": prompt},
    ]

    agent_registry: AgentRegistry | None = None
    if hasattr(rt.config, "agents") and isinstance(rt.config.agents, dict) and rt.config.agents:
        agent_registry = AgentRegistry(
            agents=rt.config.agents,
            parent_config=rt.config,
            project_ctx=rt.project_ctx,
            process_manager=rt.process_manager,
            permissions=set(permissions or {"r"}),
            agent_timeout=getattr(rt.config, "agent_timeout", 600),
            max_concurrent_agents=getattr(rt.config, "max_concurrent_agents", 5),
        )
        rt.tool_registry.register_dynamic_tool(
            AGENT_TOOL_DEFINITION, create_agent_handler(agent_registry)
        )

        cap_prompts = agent_registry.get_capability_prompts()
        if cap_prompts and messages[0].get("role") == "system":
            messages[0]["content"] += cap_prompts
            logger.info(f"Registered {len(rt.config.agents)} agent(s): {', '.join(rt.config.agents.keys())}")

    config = ChatLoopConfig(
        model=rt.config.model,
        provider=rt.config.provider,
        num_ctx=rt.config.num_ctx,
        max_output_tokens=rt.config.max_output_tokens,
        stop_sequences=list(rt.config.stop_sequences),
        permissions=set(permissions or {"r"}),
        tool_tags=frozenset(rt.config.tool_tags) if rt.config.tool_tags else None,
        max_history=rt.config.max_history_messages,
    )

    cb = CliCallbacks(verbose=rt.config.verbose)
    loop = ChatLoop(
        llm=rt.llm_provider,
        registry=rt.tool_registry,
        messages=messages,
        config=config,
        callbacks=cb,
        context_manager=rt.context_manager,
    )

    async def _drive() -> None:
        # AgentRegistry.dispatch needs a running loop to schedule agent runs
        # via run_coroutine_threadsafe. Wire it before entering the chat loop
        # so agent(action="call") works in single-shot CLI mode too.
        if agent_registry is not None:
            agent_registry.set_loop(asyncio.get_running_loop())
        await loop.run()

    asyncio.run(_drive())
    print()  # Ensure terminal prompt starts on a new line after streaming output
    return 0


class CommandRunner:
    """Runner for single command execution mode."""

    def __init__(self, prompt: str, permissions=None, agent_mode: bool = False,
                 system_prompt_override: str | None = None):
        self.prompt = prompt
        self.permissions = permissions
        self.agent_mode = agent_mode
        self.system_prompt_override = system_prompt_override

    def run(self) -> int:
        """Execute the command and return exit code.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            return _run_loop(
                self.prompt,
                permissions=self.permissions,
                agent_mode=self.agent_mode,
                system_prompt_override=self.system_prompt_override,
            )
        except ProviderUnavailableError as e:
            print(str(e), file=sys.stderr)   # message already starts with "Error:"
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def run_command(prompt: str, permissions=None, agent_mode: bool = False,
                system_prompt_override: str | None = None) -> int:
    """Execute a single command and return exit code.

    Args:
        prompt: The command/prompt to execute
        permissions: Set of granted permission categories (e.g. {"r", "w", "x", "http"})
        agent_mode: When True, inject the AGENTIC orchestrator system prompt (ayder-cli --agent).
        system_prompt_override: When set, use this text as the system prompt base
            instead of the built-in prompts.py prompt (ayder --system-prompt FILE).

    Returns:
        Exit code (0 for success, 1 for error)
    """
    runner = CommandRunner(
        prompt, permissions=permissions, agent_mode=agent_mode,
        system_prompt_override=system_prompt_override,
    )
    return runner.run()


class TaskRunner:
    """Runner for task-related CLI commands."""

    @staticmethod
    def list_tasks() -> int:
        """List all tasks and return exit code.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            from ayder_cli.core.context import ProjectContext
            from ayder_cli.tools.builtins.tasks import list_tasks

            result = list_tasks(ProjectContext("."))
            print(result)
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def implement_task(task_query: str, permissions=None) -> int:
        """Implement a specific task by ID or name.

        Args:
            task_query: Task ID or name pattern to search for
            permissions: Set of granted permission categories

        Returns:
            Exit code (0 for success, 1 for error/not found)
        """
        try:
            from ayder_cli.core.context import ProjectContext
            from ayder_cli.tools.builtins.tasks import (
                _get_tasks_dir,
                _get_task_path_by_id,
                _extract_id,
                _parse_title,
            )

            project_ctx = ProjectContext(".")
            tasks_dir = _get_tasks_dir(project_ctx)

            # Try to find by ID first
            try:
                task_id = int(task_query)
                task_path = _get_task_path_by_id(project_ctx, task_id)
                if task_path:
                    return TaskRunner._execute_task(
                        task_path, project_ctx, permissions
                    )
            except ValueError:
                pass

            # Search by name/pattern
            query_lower = task_query.lower()
            for task_file in sorted(tasks_dir.glob("*.md")):
                task_id = _extract_id(task_file.name)
                if task_id is None:
                    continue
                title = _parse_title(task_file)
                if query_lower in title.lower():
                    return TaskRunner._execute_task(
                        task_file, project_ctx, permissions
                    )

            print(f"No tasks found matching: {task_query}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def _execute_task(
        task_path: Path,
        project_ctx,
        permissions,
    ) -> int:
        """Execute a single task file.

        Args:
            task_path: Path to the task markdown file
            project_ctx: ProjectContext instance
            permissions: Set of granted permission categories

        Returns:
            Exit code (0 for success, 1 for error)
        """
        from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE

        rel_path = project_ctx.to_relative(task_path)
        prompt = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
        return _run_loop(prompt, permissions=permissions)

    @staticmethod
    def implement_all(permissions=None) -> int:
        """Implement all pending tasks sequentially.

        Args:
            permissions: Set of granted permission categories

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            from ayder_cli.prompts import TASK_EXECUTION_ALL_PROMPT_TEMPLATE

            return _run_loop(
                TASK_EXECUTION_ALL_PROMPT_TEMPLATE,
                permissions=permissions,
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def _run_tasks_cli() -> int:
    """List all tasks and exit."""
    return TaskRunner.list_tasks()


def _run_implement_cli(task_query: str, permissions=None) -> int:
    """Implement a specific task by ID or name."""
    return TaskRunner.implement_task(
        task_query, permissions=permissions
    )


def _run_implement_all_cli(permissions=None) -> int:
    """Implement all pending tasks sequentially."""
    return TaskRunner.implement_all(permissions=permissions)


def _run_temporal_queue_cli(
    queue_name: str,
    prompt_path: str | None = None,
    permissions=None,
) -> int:
    """Start a Temporal worker queue session."""
    from ayder_cli.tools.plugin_manager import _find_plugin_module, PluginError

    try:
        temporal_worker = _find_plugin_module("temporal-tools", "temporal_worker")
        TemporalWorker = getattr(temporal_worker, "TemporalWorker")
        TemporalWorkerConfig = getattr(temporal_worker, "TemporalWorkerConfig")
    except (ImportError, PluginError) as exc:
        raise RuntimeError(
            "temporal-tools plugin is not installed. "
            "Run: ayder plugin install temporal-tools"
        ) from exc

    worker_config = TemporalWorkerConfig(
        queue_name=queue_name,
        prompt_path=prompt_path,
        permissions=set(permissions or {"r"}),
    )
    worker = TemporalWorker(worker_config)
    return worker.run()
