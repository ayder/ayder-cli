"""CLI entry point for ayder.

This module handles argument parsing and delegates to cli_runner.py for execution.
"""

import argparse
import sys
from pathlib import Path
from ayder_cli.version import get_app_version


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ayder", description="AI-powered CLI assistant"
    )

    # Task-related CLI options
    parser.add_argument(
        "--tasks", action="store_true", help="List all saved tasks and exit"
    )
    parser.add_argument(
        "--implement",
        type=str,
        metavar="TASK",
        default=None,
        help="Implement a task by ID or name and exit (e.g., --implement 1 or --implement auth)",
    )
    parser.add_argument(
        "--implement-all",
        action="store_true",
        help="Implement all pending tasks sequentially and exit",
    )

    # Mutually exclusive group for file and stdin
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        metavar="FILE",
        help="Read prompt from file",
    )
    input_group.add_argument(
        "--stdin", action="store_true", help="Read prompt from stdin"
    )

    # Permission flags (Unix-style: r=read, w=write, x=execute)
    parser.add_argument(
        "-r",
        action="store_true",
        default=True,
        help="Auto-approve read tools (default: enabled)",
    )
    parser.add_argument(
        "-w",
        action="store_true",
        help="Auto-approve write tools (write_file, replace_string, create_task, etc.)",
    )
    parser.add_argument(
        "-x", action="store_true", help="Auto-approve execute tools (run_shell_command)"
    )

    # Max agentic iterations (overrides config.max_iterations)
    parser.add_argument(
        "-I",
        "--iterations",
        type=int,
        default=None,
        help="Max agentic iterations per message (default: from config, 50)",
    )

    # Version flag
    parser.add_argument("--version", action="version", version=get_app_version())

    # Positional command argument
    parser.add_argument(
        "command", nargs="?", default=None, help="Command to execute directly"
    )

    return parser


def main():
    """Main entry point for the CLI."""
    from ayder_cli.cli_runner import (
        run_command,
        _run_tasks_cli,
        _run_implement_cli,
        _run_implement_all_cli,
    )

    parser = create_parser()
    args = parser.parse_args()

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
        sys.exit(
            _run_implement_cli(
                args.implement, permissions=granted, iterations=iterations
            )
        )
    if args.implement_all:
        sys.exit(_run_implement_all_cli(permissions=granted, iterations=iterations))

    # Handle file/stdin input
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
        prompt = f"Context:\n{context}\n\nQuestion: {question}"
    elif context is not None:
        prompt = context
    elif question:
        prompt = question
    else:
        # Default: TUI mode
        from ayder_cli.tui import run_tui

        run_tui(permissions=granted, iterations=iterations)
        return

    sys.exit(run_command(prompt, permissions=granted, iterations=iterations))


if __name__ == "__main__":
    main()
