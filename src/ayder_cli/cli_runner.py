"""CLI command runners for single-command execution and task management.

This module contains the logic for running the CLI in different modes:
- Single command execution (run_command)
- Task management commands (_run_tasks_cli, _run_implement_cli, _run_implement_all_cli)

All CLI paths drive TuiChatLoop via CliCallbacks, sharing the same async
execution engine used by the TUI.
"""

import asyncio
import sys
from pathlib import Path

from ayder_cli.application.runtime_factory import create_runtime
from ayder_cli.cli_callbacks import CliCallbacks
from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig


def _build_services(config=None, project_root="."):
    """Build the service dependency graph via the shared runtime factory.

    Returns:
        Tuple of (config, llm_provider, project_ctx,
                  enhanced_system, checkpoint_manager, memory_manager)
    """
    rt = create_runtime(config=config, project_root=project_root)
    return (
        rt.config,
        rt.llm_provider,
        rt.project_ctx,
        rt.system_prompt,
        rt.checkpoint_manager,
        rt.memory_manager,
    )


def _run_loop(
    prompt: str,
    permissions: set | None = None,
    iterations: int = 50,
) -> int:
    """Create a TuiChatLoop with CliCallbacks and run it.

    Shared helper used by CommandRunner, TaskRunner._execute_task, and
    TaskRunner.implement_all.

    Args:
        prompt: The user prompt to send to the loop.
        permissions: Granted permission categories.
        iterations: Max agentic iterations.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    rt = create_runtime()

    messages: list[dict] = [
        {"role": "system", "content": rt.system_prompt},
        {"role": "user", "content": prompt},
    ]

    config = TuiLoopConfig(
        model=rt.config.model,
        num_ctx=rt.config.num_ctx,
        max_output_tokens=getattr(rt.config, "max_output_tokens", 4096),
        stop_sequences=list(getattr(rt.config, "stop_sequences", [])),
        max_iterations=iterations,
        permissions=set(permissions or {"r"}),
        tool_tags=(
            frozenset(rt.config.tool_tags)
            if getattr(rt.config, "tool_tags", None)
            else None
        ),
    )

    cb = CliCallbacks(verbose=getattr(rt.config, "verbose", False))
    loop = TuiChatLoop(
        llm=rt.llm_provider,
        registry=rt.tool_registry,
        messages=messages,
        config=config,
        callbacks=cb,
        checkpoint_manager=rt.checkpoint_manager,
        memory_manager=rt.memory_manager,
    )

    asyncio.run(loop.run())
    return 0


class CommandRunner:
    """Runner for single command execution mode."""

    def __init__(self, prompt: str, permissions=None, iterations=50):
        self.prompt = prompt
        self.permissions = permissions
        self.iterations = iterations

    def run(self) -> int:
        """Execute the command and return exit code.

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            return _run_loop(
                self.prompt,
                permissions=self.permissions,
                iterations=self.iterations,
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def run_command(prompt: str, permissions=None, iterations=50) -> int:
    """Execute a single command and return exit code.

    Args:
        prompt: The command/prompt to execute
        permissions: Set of granted permission categories (e.g. {"r", "w", "x", "http"})
        iterations: Max agentic iterations per message

    Returns:
        Exit code (0 for success, 1 for error)
    """
    runner = CommandRunner(prompt, permissions=permissions, iterations=iterations)
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
            from ayder_cli.tasks import list_tasks

            result = list_tasks(ProjectContext("."))
            print(result)
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def implement_task(task_query: str, permissions=None, iterations=50) -> int:
        """Implement a specific task by ID or name.

        Args:
            task_query: Task ID or name pattern to search for
            permissions: Set of granted permission categories
            iterations: Max agentic iterations per message

        Returns:
            Exit code (0 for success, 1 for error/not found)
        """
        try:
            from ayder_cli.core.context import ProjectContext
            from ayder_cli.tasks import (
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
                        task_path, project_ctx, permissions, iterations
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
                        task_file, project_ctx, permissions, iterations
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
        iterations,
    ) -> int:
        """Execute a single task file.

        Args:
            task_path: Path to the task markdown file
            project_ctx: ProjectContext instance
            permissions: Set of granted permission categories
            iterations: Max agentic iterations per message

        Returns:
            Exit code (0 for success, 1 for error)
        """
        from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE

        rel_path = project_ctx.to_relative(task_path)
        prompt = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)
        return _run_loop(prompt, permissions=permissions, iterations=iterations)

    @staticmethod
    def implement_all(permissions=None, iterations=50) -> int:
        """Implement all pending tasks sequentially.

        Args:
            permissions: Set of granted permission categories
            iterations: Max agentic iterations per message

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            from ayder_cli.prompts import TASK_EXECUTION_ALL_PROMPT_TEMPLATE

            return _run_loop(
                TASK_EXECUTION_ALL_PROMPT_TEMPLATE,
                permissions=permissions,
                iterations=iterations,
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def _run_tasks_cli() -> int:
    """List all tasks and exit."""
    return TaskRunner.list_tasks()


def _run_implement_cli(task_query: str, permissions=None, iterations=50) -> int:
    """Implement a specific task by ID or name."""
    return TaskRunner.implement_task(
        task_query, permissions=permissions, iterations=iterations
    )


def _run_implement_all_cli(permissions=None, iterations=50) -> int:
    """Implement all pending tasks sequentially."""
    return TaskRunner.implement_all(permissions=permissions, iterations=iterations)


def _run_temporal_queue_cli(
    queue_name: str,
    prompt_path: str | None = None,
    permissions=None,
    iterations: int = 50,
) -> int:
    """Start a Temporal worker queue session."""
    from ayder_cli.services.temporal_worker import TemporalWorker, TemporalWorkerConfig

    worker_config = TemporalWorkerConfig(
        queue_name=queue_name,
        prompt_path=prompt_path,
        permissions=set(permissions or {"r"}),
        iterations=iterations,
    )
    worker = TemporalWorker(worker_config)
    return worker.run()
