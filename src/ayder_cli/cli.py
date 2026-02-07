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

    # Max agentic iterations
    parser.add_argument(
        "-I", "--iterations",
        type=int,
        default=10,
        help="Max agentic iterations per message (default: 10)"
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
        Tuple of (config, llm_provider, tool_executor, project_ctx, enhanced_prompt)
    """
    from ayder_cli.core.config import load_config
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.services.llm import OpenAIProvider
    from ayder_cli.services.tools.executor import ToolExecutor
    from ayder_cli.tools.registry import create_default_registry
    from ayder_cli.prompts import SYSTEM_PROMPT

    cfg = config or load_config()
    llm_provider = OpenAIProvider(base_url=cfg.base_url, api_key=cfg.api_key)
    project_ctx = ProjectContext(project_root)
    tool_registry = create_default_registry(project_ctx)
    tool_executor = ToolExecutor(tool_registry)

    # Build enhanced prompt with project structure
    try:
        structure = tool_registry.execute("get_project_structure", {"max_depth": 3})
        macro = f"\n\n### PROJECT STRUCTURE:\n```\n{structure}\n```\n\nThis is the current project structure. Use `search_codebase` to locate specific code before reading files.\n"
    except Exception:
        macro = ""

    return cfg, llm_provider, tool_executor, project_ctx, SYSTEM_PROMPT + macro


def run_interactive(permissions=None, iterations=10):
    """Run interactive chat mode (REPL)."""
    from ayder_cli.client import ChatSession, Agent
    from ayder_cli.core.context import SessionContext
    from ayder_cli.commands import handle_command
    from ayder_cli.ui import draw_box, print_running, print_assistant_message

    cfg, llm_provider, tool_executor, project_ctx, enhanced_prompt = _build_services()

    chat_session = ChatSession(cfg, enhanced_prompt, permissions, iterations)
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
                messages=chat_session.messages, state=chat_session.state
            )
            handle_command(user_input, session_ctx)
            continue

        try:
            print_running()
            response = agent.chat(user_input)
            if response is not None:
                print_assistant_message(response)
        except Exception as e:
            draw_box(f"Error: {str(e)}", title="Error", width=80, color_code="31")


def run_command(prompt: str, permissions=None, iterations=10) -> int:
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

        cfg, llm_provider, tool_executor, _, enhanced_prompt = _build_services()

        session = ChatSession(
            config=cfg, system_prompt=enhanced_prompt,
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

    # Handle file/stdin input
    prompt = read_input(args)
    if prompt:
        sys.exit(run_command(prompt, permissions=granted, iterations=args.iterations))

    # Default: interactive CLI mode
    run_interactive(permissions=granted, iterations=args.iterations)


if __name__ == "__main__":
    main()
