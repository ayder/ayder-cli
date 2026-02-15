"""CLI command runners for single-command execution and task management.

This module contains the logic for running the CLI in different modes:
- Single command execution (run_command)
- Task management commands (_run_tasks_cli, _run_implement_cli, _run_implement_all_cli)
"""

import sys
from pathlib import Path


def _build_services(config=None, project_root="."):
    """Build the service dependency graph (Composition Root).

    Returns:
        Tuple of (config, llm_provider, tool_executor, project_ctx,
                  enhanced_system, checkpoint_manager, memory_manager)
    """
    from ayder_cli.core.config import load_config
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.services.llm import create_llm_provider
    from ayder_cli.services.tools.executor import ToolExecutor
    from ayder_cli.tools.registry import create_default_registry
    from ayder_cli.process_manager import ProcessManager
    from ayder_cli.prompts import SYSTEM_PROMPT, PROJECT_STRUCTURE_MACRO_TEMPLATE
    from ayder_cli.checkpoint_manager import CheckpointManager
    from ayder_cli.memory import MemoryManager

    cfg = config or load_config()
    llm_provider = create_llm_provider(cfg)
    project_ctx = ProjectContext(project_root)
    process_manager = ProcessManager(max_processes=cfg.max_background_processes)
    tool_registry = create_default_registry(
        project_ctx, process_manager=process_manager
    )
    tool_executor = ToolExecutor(tool_registry)
    checkpoint_manager = CheckpointManager(project_ctx)

    # MemoryManager handles LLM-based checkpoint operations
    # It requires llm_provider and tool_executor for checkpoint creation
    memory_manager = MemoryManager(
        project_ctx,
        llm_provider=llm_provider,
        tool_executor=tool_executor,
        checkpoint_manager=checkpoint_manager,
    )

    # Build enhanced prompt with project structure
    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
    except Exception:
        macro = ""

    enhanced_system = SYSTEM_PROMPT.format(model_name=cfg.model) + macro

    return (
        cfg,
        llm_provider,
        tool_executor,
        project_ctx,
        enhanced_system,
        checkpoint_manager,
        memory_manager,
    )





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
            from ayder_cli.client import ChatSession, Agent

            services = _build_services()
            (
                cfg,
                llm_provider,
                tool_executor,
                _,
                enhanced_system,
                checkpoint_manager,
                memory_manager,
            ) = services

            session = ChatSession(
                config=cfg,
                system_prompt=enhanced_system,
                permissions=self.permissions,
                iterations=self.iterations,
                checkpoint_manager=checkpoint_manager,
                memory_manager=memory_manager,
            )
            agent = Agent(llm_provider, tool_executor, session)

            response = agent.chat(self.prompt)
            if response:
                print(response)

            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def run_command(prompt: str, permissions=None, iterations=50) -> int:
    """Execute a single command and return exit code.

    Args:
        prompt: The command/prompt to execute
        permissions: Set of granted permission categories (e.g. {"r", "w", "x"})
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

            services = _build_services()
            (
                cfg,
                llm_provider,
                tool_executor,
                _,
                enhanced_system,
                checkpoint_manager,
                memory_manager,
            ) = services

            project_ctx = ProjectContext(".")
            tasks_dir = _get_tasks_dir(project_ctx)

            # Try to find by ID first
            try:
                task_id = int(task_query)
                task_path = _get_task_path_by_id(project_ctx, task_id)
                if task_path:
                    return TaskRunner._execute_task(
                        task_path,
                        project_ctx,
                        cfg,
                        llm_provider,
                        tool_executor,
                        enhanced_system,
                        checkpoint_manager,
                        memory_manager,
                        permissions,
                        iterations,
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
                        task_file,
                        project_ctx,
                        cfg,
                        llm_provider,
                        tool_executor,
                        enhanced_system,
                        checkpoint_manager,
                        memory_manager,
                        permissions,
                        iterations,
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
        cfg,
        llm_provider,
        tool_executor,
        enhanced_system,
        checkpoint_manager,
        memory_manager,
        permissions,
        iterations,
    ) -> int:
        """Execute a single task file.

        Args:
            task_path: Path to the task markdown file
            project_ctx: ProjectContext instance
            cfg: Configuration object
            llm_provider: LLM provider instance
            tool_executor: Tool executor instance
            enhanced_system: Enhanced system prompt string
            checkpoint_manager: CheckpointManager instance
            memory_manager: MemoryManager instance
            permissions: Set of granted permission categories
            iterations: Max agentic iterations per message

        Returns:
            Exit code (0 for success, 1 for error)
        """
        from ayder_cli.client import ChatSession, Agent
        from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE

        rel_path = project_ctx.to_relative(task_path)
        prompt = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)

        session = ChatSession(
            config=cfg,
            system_prompt=enhanced_system,
            permissions=permissions,
            iterations=iterations,
            checkpoint_manager=checkpoint_manager,
            memory_manager=memory_manager,
        )
        agent = Agent(llm_provider, tool_executor, session)

        # Add the task execution prompt
        response = agent.chat(prompt)
        if response:
            print(response)
        return 0

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
            from ayder_cli.client import ChatSession, Agent
            from ayder_cli.prompts import TASK_EXECUTION_ALL_PROMPT_TEMPLATE

            services = _build_services()
            (
                cfg,
                llm_provider,
                tool_executor,
                _,
                enhanced_system,
                checkpoint_manager,
                memory_manager,
            ) = services

            session = ChatSession(
                config=cfg,
                system_prompt=enhanced_system,
                permissions=permissions,
                iterations=iterations,
                checkpoint_manager=checkpoint_manager,
                memory_manager=memory_manager,
            )
            agent = Agent(llm_provider, tool_executor, session)

            response = agent.chat(TASK_EXECUTION_ALL_PROMPT_TEMPLATE)
            if response:
                print(response)
            return 0
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
