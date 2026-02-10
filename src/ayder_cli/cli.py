import argparse
import sys
from pathlib import Path
from ayder_cli.banner import get_app_version


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ayder",
        description="AI-powered CLI assistant"
    )

    # Boolean flag for TUI mode
    parser.add_argument(
        "--tui", "-t",
        action="store_true",
        help="Launch TUI mode"
    )

    # Task-related CLI options
    parser.add_argument(
        "--tasks",
        action="store_true",
        help="List all saved tasks and exit"
    )
    parser.add_argument(
        "--implement",
        type=str,
        metavar="TASK",
        default=None,
        help="Implement a task by ID or name and exit (e.g., --implement 1 or --implement auth)"
    )
    parser.add_argument(
        "--implement-all",
        action="store_true",
        help="Implement all pending tasks sequentially and exit"
    )

    # Mutually exclusive group for file and stdin
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        metavar="FILE",
        help="Read prompt from file"
    )
    input_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read prompt from stdin"
    )

    # Permission flags (Unix-style: r=read, w=write, x=execute)
    parser.add_argument(
        "-r",
        action="store_true",
        default=True,
        help="Auto-approve read tools (default: enabled)"
    )
    parser.add_argument(
        "-w",
        action="store_true",
        help="Auto-approve write tools (write_file, replace_string, create_task, etc.)"
    )
    parser.add_argument(
        "-x",
        action="store_true",
        help="Auto-approve execute tools (run_shell_command)"
    )

    # Max agentic iterations (overrides config.max_iterations)
    parser.add_argument(
        "-I", "--iterations",
        type=int,
        default=None,
        help="Max agentic iterations per message (default: from config, 50)"
    )

    # Version flag
    parser.add_argument(
        "--version",
        action="version",
        version=get_app_version()
    )

    # Positional command argument
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="Command to execute directly"
    )

    return parser


def read_input(args) -> str:
    """Build prompt from file/stdin/command combinations.

    Args:
        args: Parsed command-line arguments

    Returns:
        Constructed prompt string or None if no input provided

    Exits:
        - Exit code 1 if file not found
        - Exit code 1 if --stdin used without piped input
    """
    context = None
    question = args.command

    if args.file:
        try:
            context = Path(args.file).read_text()
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file {args.file}: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.stdin:
        if sys.stdin.isatty():
            print("Error: --stdin requires piped input", file=sys.stderr)
            sys.exit(1)
        context = sys.stdin.read()

    if context is not None and question:
        return f"Context:\n{context}\n\nQuestion: {question}"
    elif context is not None:
        return context
    elif question:
        return question
    else:
        return None


def _build_services(config=None, project_root="."):
    """Build the service dependency graph (Composition Root).

    Returns:
        Tuple of (config, llm_provider, tool_executor, project_ctx, enhanced_system)
    """
    from ayder_cli.core.config import load_config
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.services.llm import OpenAIProvider
    from ayder_cli.services.tools.executor import ToolExecutor
    from ayder_cli.tools.registry import create_default_registry
    from ayder_cli.process_manager import ProcessManager
    from ayder_cli.prompts import SYSTEM_PROMPT

    cfg = config or load_config()
    llm_provider = OpenAIProvider(base_url=cfg.base_url, api_key=cfg.api_key)
    project_ctx = ProjectContext(project_root)
    process_manager = ProcessManager(max_processes=cfg.max_background_processes)
    tool_registry = create_default_registry(project_ctx, process_manager=process_manager)
    tool_executor = ToolExecutor(tool_registry)

    # Build enhanced prompt with project structure
    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = f"\n\n### PROJECT STRUCTURE:\n```\n{structure}\n```\n\nThis is the current project structure. Use `search_codebase` to locate specific code before reading files.\n"
    except Exception:
        macro = ""

    enhanced_system = SYSTEM_PROMPT + macro

    return cfg, llm_provider, tool_executor, project_ctx, enhanced_system


def run_interactive(permissions=None, iterations=50):
    """Run interactive chat mode (REPL)."""
    from ayder_cli.client import ChatSession, Agent
    from ayder_cli.core.context import SessionContext
    from ayder_cli.commands import handle_command
    from ayder_cli.ui import draw_box, print_running, print_assistant_message

    cfg, llm_provider, tool_executor, project_ctx, enhanced_system = _build_services()

    chat_session = ChatSession(cfg, enhanced_system,
                               permissions=permissions, iterations=iterations)
    chat_session.start()
    agent = Agent(llm_provider, tool_executor, chat_session)

    while True:
        user_input = chat_session.get_input()
        if user_input is None:
            break
        if not user_input:
            continue

        if user_input.startswith('/'):
            session_ctx = SessionContext(
                config=cfg, project=project_ctx,
                messages=chat_session.messages, state=chat_session.state,
                llm=llm_provider,
                system_prompt=enhanced_system
            )
            # Track message count to detect if command added messages for agent
            msg_count_before = len(chat_session.messages)
            handle_command(user_input, session_ctx)
            msg_count_after = len(chat_session.messages)

            # If command added messages (e.g., /implement), process them through agent
            if msg_count_after > msg_count_before:
                try:
                    print_running()
                    # Get the last added message content
                    last_msg = chat_session.messages[-1]
                    if last_msg.get("role") == "user":
                        # Remove the message we just added (agent.chat will re-add it)
                        chat_session.messages.pop()
                        response = agent.chat(last_msg["content"])
                        if response is not None:
                            print_assistant_message(response)
                except Exception as e:
                    draw_box(f"Error: {str(e)}", title="Error", width=80, color_code="31")
            continue

        try:
            print_running()
            response = agent.chat(user_input)
            if response is not None:
                print_assistant_message(response)
        except Exception as e:
            draw_box(f"Error: {str(e)}", title="Error", width=80, color_code="31")


def run_command(prompt: str, permissions=None, iterations=50) -> int:
    """Execute a single command and return exit code.

    Args:
        prompt: The command/prompt to execute
        permissions: Set of granted permission categories (e.g. {"r", "w", "x"})
        iterations: Max agentic iterations per message

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        from ayder_cli.client import ChatSession, Agent

        cfg, llm_provider, tool_executor, _, enhanced_system = _build_services()

        session = ChatSession(
            config=cfg, system_prompt=enhanced_system,
            permissions=permissions, iterations=iterations
        )
        agent = Agent(llm_provider, tool_executor, session)

        response = agent.chat(prompt)
        if response:
            print(response)

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_tasks_cli() -> int:
    """List all tasks and exit."""
    try:
        from ayder_cli.core.context import ProjectContext
        from ayder_cli.tasks import list_tasks
        result = list_tasks(ProjectContext("."))
        print(result)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_implement_cli(task_query: str, permissions=None, iterations=50) -> int:
    """Implement a specific task by ID or name."""
    try:
        from ayder_cli.client import ChatSession, Agent
        from ayder_cli.core.context import ProjectContext
        from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE
        from ayder_cli.tasks import _get_tasks_dir, _get_task_path_by_id, _extract_id, _parse_title

        cfg, llm_provider, tool_executor, _, enhanced_system = _build_services()

        project_ctx = ProjectContext(".")
        tasks_dir = _get_tasks_dir(project_ctx)

        # Try to find by ID first
        try:
            task_id = int(task_query)
            task_path = _get_task_path_by_id(project_ctx, task_id)
            if task_path:
                rel_path = project_ctx.to_relative(task_path)
                prompt = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)

                session = ChatSession(
                    config=cfg, system_prompt=enhanced_system,
                    permissions=permissions, iterations=iterations
                )
                agent = Agent(llm_provider, tool_executor, session)

                # Add the task execution prompt
                response = agent.chat(prompt)
                if response:
                    print(response)
                return 0
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
                rel_path = project_ctx.to_relative(task_file)
                prompt = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)

                session = ChatSession(
                    config=cfg, system_prompt=enhanced_system,
                    permissions=permissions, iterations=iterations
                )
                agent = Agent(llm_provider, tool_executor, session)

                response = agent.chat(prompt)
                if response:
                    print(response)
                return 0

        print(f"No tasks found matching: {task_query}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_implement_all_cli(permissions=None, iterations=50) -> int:
    """Implement all pending tasks sequentially."""
    try:
        from ayder_cli.client import ChatSession, Agent
        from ayder_cli.prompts import TASK_EXECUTION_ALL_PROMPT_TEMPLATE

        cfg, llm_provider, tool_executor, _, enhanced_system = _build_services()

        session = ChatSession(
            config=cfg, system_prompt=enhanced_system,
            permissions=permissions, iterations=iterations
        )
        agent = Agent(llm_provider, tool_executor, session)

        response = agent.chat(TASK_EXECUTION_ALL_PROMPT_TEMPLATE)
        if response:
            print(response)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # Auto-detect piped input: if stdin is not a TTY and no explicit input method specified,
    # automatically enable --stdin mode for better UX
    if not sys.stdin.isatty() and not args.stdin and not args.file and not args.tui:
        args.stdin = True

    # Handle TUI mode
    if args.tui:
        if args.command:
            parser.error("--tui cannot be used with a command argument")
        from ayder_cli.tui import run_tui
        run_tui()
        return

    # Build granted permissions set from flags
    # Read tools are auto-approved by default (use --no-r to disable)
    granted = {"r"}
    if args.w:
        granted.add("w")
    if args.x:
        granted.add("x")

    # Resolve iterations: CLI flag overrides config value
    if args.iterations is None:
        from ayder_cli.core.config import load_config
        iterations = load_config().max_iterations
    else:
        iterations = args.iterations

    # Handle task-related CLI options
    if args.tasks:
        sys.exit(_run_tasks_cli())
    if args.implement:
        sys.exit(_run_implement_cli(args.implement, permissions=granted, iterations=iterations))
    if args.implement_all:
        sys.exit(_run_implement_all_cli(permissions=granted, iterations=iterations))

    # Handle file/stdin input
    prompt = read_input(args)
    if prompt:
        sys.exit(run_command(prompt, permissions=granted, iterations=iterations))

    # Default: interactive CLI mode
    run_interactive(permissions=granted, iterations=iterations)


if __name__ == "__main__":
    main()
