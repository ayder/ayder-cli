"""CLI command runners for interactive and single-command execution modes.

This module contains the logic for running the CLI in different modes:
- Interactive REPL mode (run_interactive)
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
    from ayder_cli.services.llm import OpenAIProvider
    from ayder_cli.services.tools.executor import ToolExecutor
    from ayder_cli.tools.registry import create_default_registry
    from ayder_cli.process_manager import ProcessManager
    from ayder_cli.prompts import SYSTEM_PROMPT, PROJECT_STRUCTURE_MACRO_TEMPLATE
    from ayder_cli.checkpoint_manager import CheckpointManager
    from ayder_cli.memory import MemoryManager

    cfg = config or load_config()
    llm_provider = OpenAIProvider(base_url=cfg.base_url, api_key=cfg.api_key)
    project_ctx = ProjectContext(project_root)
    process_manager = ProcessManager(max_processes=cfg.max_background_processes)
    tool_registry = create_default_registry(project_ctx, process_manager=process_manager)
    tool_executor = ToolExecutor(tool_registry)
    checkpoint_manager = CheckpointManager(project_ctx)
    
    # MemoryManager handles LLM-based checkpoint operations
    # It requires llm_provider and tool_executor for checkpoint creation
    memory_manager = MemoryManager(
        project_ctx, 
        llm_provider=llm_provider, 
        tool_executor=tool_executor,
        checkpoint_manager=checkpoint_manager
    )

    # Build enhanced prompt with project structure
    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = PROJECT_STRUCTURE_MACRO_TEMPLATE.format(project_structure=structure)
    except Exception:
        macro = ""

    enhanced_system = SYSTEM_PROMPT + macro

    return (cfg, llm_provider, tool_executor, project_ctx, 
            enhanced_system, checkpoint_manager, memory_manager)


class InteractiveRunner:
    """Runner for interactive REPL mode."""

    def __init__(self, permissions=None, iterations=50):
        self.permissions = permissions
        self.iterations = iterations
        self.cfg = None
        self.llm_provider = None
        self.tool_executor = None
        self.project_ctx = None
        self.enhanced_system = None
        self.checkpoint_manager = None
        self.memory_manager = None
        self.chat_session = None
        self.agent = None

    def _initialize(self):
        """Initialize services and session."""
        from ayder_cli.client import ChatSession, Agent

        services = _build_services()
        (self.cfg, self.llm_provider, self.tool_executor,
         self.project_ctx, self.enhanced_system, 
         self.checkpoint_manager, self.memory_manager) = services

        self.chat_session = ChatSession(
            self.cfg, self.enhanced_system,
            permissions=self.permissions, iterations=self.iterations,
            checkpoint_manager=self.checkpoint_manager,
            memory_manager=self.memory_manager
        )
        self.chat_session.start()
        self.agent = Agent(self.llm_provider, self.tool_executor, self.chat_session)

    def _handle_command(self, user_input: str) -> bool:
        """Handle a slash command. Returns True if command was processed.

        Args:
            user_input: The command string starting with '/'

        Returns:
            True if command was handled, False otherwise
        """
        from ayder_cli.core.context import SessionContext
        from ayder_cli.commands import handle_command
        from ayder_cli.ui import draw_box, print_running, print_assistant_message

        session_ctx = SessionContext(
            config=self.cfg, project=self.project_ctx,
            messages=self.chat_session.messages, state=self.chat_session.state,
            llm=self.llm_provider,
            system_prompt=self.enhanced_system
        )

        # Track message count to detect if command added messages for agent
        msg_count_before = len(self.chat_session.messages)
        handle_command(user_input, session_ctx)
        msg_count_after = len(self.chat_session.messages)

        # If command added messages (e.g., /implement), process them through agent
        if msg_count_after > msg_count_before:
            try:
                print_running()
                # Get the last added message content
                last_msg = self.chat_session.messages[-1]
                if last_msg.get("role") == "user":
                    # Remove the message we just added (agent.chat will re-add it)
                    self.chat_session.messages.pop()
                    response = self.agent.chat(last_msg["content"])
                    if response is not None:
                        print_assistant_message(response)
            except Exception as e:
                draw_box(f"Error: {str(e)}", title="Error", width=80, color_code="31")

        return True

    def _process_input(self, user_input: str) -> bool:
        """Process user input (command or regular message).

        Args:
            user_input: The input string from user

        Returns:
            True to continue loop, False to exit
        """
        from ayder_cli.ui import draw_box, print_running, print_assistant_message

        if not user_input:
            return True

        if user_input.startswith('/'):
            self._handle_command(user_input)
            return True

        try:
            print_running()
            response = self.agent.chat(user_input)
            if response is not None:
                print_assistant_message(response)
        except Exception as e:
            draw_box(f"Error: {str(e)}", title="Error", width=80, color_code="31")

        return True

    def run(self):
        """Run the interactive REPL loop."""
        self._initialize()

        while True:
            user_input = self.chat_session.get_input()
            if user_input is None:
                break
            if not self._process_input(user_input):
                break


def run_interactive(permissions=None, iterations=50):
    """Run interactive chat mode (REPL).

    Args:
        permissions: Set of granted permission categories (e.g. {"r", "w", "x"})
        iterations: Max agentic iterations per message
    """
    runner = InteractiveRunner(permissions=permissions, iterations=iterations)
    runner.run()


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
            (cfg, llm_provider, tool_executor, _, enhanced_system, 
             checkpoint_manager, memory_manager) = services

            session = ChatSession(
                config=cfg, system_prompt=enhanced_system,
                permissions=self.permissions, iterations=self.iterations,
                checkpoint_manager=checkpoint_manager,
                memory_manager=memory_manager
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
            from ayder_cli.client import ChatSession, Agent
            from ayder_cli.core.context import ProjectContext
            from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE
            from ayder_cli.tasks import (
                _get_tasks_dir, _get_task_path_by_id, _extract_id, _parse_title
            )

            services = _build_services()
            (cfg, llm_provider, tool_executor, _, enhanced_system,
             checkpoint_manager, memory_manager) = services
            
            project_ctx = ProjectContext(".")
            tasks_dir = _get_tasks_dir(project_ctx)

            # Try to find by ID first
            try:
                task_id = int(task_query)
                task_path = _get_task_path_by_id(project_ctx, task_id)
                if task_path:
                    return TaskRunner._execute_task(
                        task_path, project_ctx, cfg, llm_provider, tool_executor,
                        enhanced_system, checkpoint_manager, memory_manager,
                        permissions, iterations
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
                        task_file, project_ctx, cfg, llm_provider, tool_executor,
                        enhanced_system, checkpoint_manager, memory_manager,
                        permissions, iterations
                    )

            print(f"No tasks found matching: {task_query}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def _execute_task(
        task_path: Path, project_ctx, cfg, llm_provider, tool_executor,
        enhanced_system, checkpoint_manager, memory_manager, permissions, iterations
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
            config=cfg, system_prompt=enhanced_system,
            permissions=permissions, iterations=iterations,
            checkpoint_manager=checkpoint_manager,
            memory_manager=memory_manager
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
            (cfg, llm_provider, tool_executor, _, enhanced_system,
             checkpoint_manager, memory_manager) = services

            session = ChatSession(
                config=cfg, system_prompt=enhanced_system,
                permissions=permissions, iterations=iterations,
                checkpoint_manager=checkpoint_manager,
                memory_manager=memory_manager
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
    return TaskRunner.implement_task(task_query, permissions=permissions, iterations=iterations)


def _run_implement_all_cli(permissions=None, iterations=50) -> int:
    """Implement all pending tasks sequentially."""
    return TaskRunner.implement_all(permissions=permissions, iterations=iterations)
