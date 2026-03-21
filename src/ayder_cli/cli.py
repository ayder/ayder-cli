"""CLI entry point for ayder.

This module handles argument parsing and delegates to cli_runner.py for execution.
"""

import argparse
import sys
from pathlib import Path
from ayder_cli.version import get_app_version
from ayder_cli.logging_config import LOG_LEVELS, setup_logging


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add all shared arguments to *parser* (used by both create_parser and _create_base_parser)."""
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
    # Conditional: only add --temporal-task-queue if temporal plugin is loaded
    try:
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME
        if "temporal_workflow" in TOOL_DEFINITIONS_BY_NAME:
            parser.add_argument(
                "--temporal-task-queue",
                type=str,
                metavar="QUEUE",
                default=None,
                help="Start Temporal worker bound to the given task queue",
            )
    except ImportError:
        pass

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
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        metavar="FILE",
        help="Inject custom system prompt from file",
    )

    # Permission flags: r=read, w=write, x=execute, http=web/network
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
    parser.add_argument(
        "--http",
        action="store_true",
        help="Auto-approve web/network tools (fetch_web)",
    )

    parser.add_argument(
        "--verbose",
        nargs="?",
        const="INFO",
        default=None,
        type=str.upper,
        choices=LOG_LEVELS,
        metavar="LEVEL",
        help="Enable verbose console output and logging; default level is INFO",
    )
    parser.add_argument(
        "--logging-level",
        type=str.upper,
        choices=LOG_LEVELS,
        metavar="LEVEL",
        default=None,
        help="Set the logging level for this session (e.g. DEBUG, INFO). Logs are written to .ayder/log/ayder.log",
    )

    # Version flag
    parser.add_argument("--version", action="version", version=get_app_version())


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser (includes plugin subcommands)."""
    parser = argparse.ArgumentParser(
        prog="ayder", description="AI-powered CLI assistant"
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    # Plugin management subcommands
    install_parser = subparsers.add_parser(
        "install-plugin", help="Install a plugin from GitHub or local path"
    )
    install_parser.add_argument("source", help="GitHub URL or local path")
    install_parser.add_argument(
        "--project", action="store_true",
        help="Install to project-local .ayder/plugins/ instead of global",
    )
    install_parser.add_argument(
        "--force", action="store_true", help="Overwrite if already installed"
    )
    install_parser.add_argument(
        "--yes", "-y", action="store_true", help="Auto-confirm dependency installation"
    )

    uninstall_parser = subparsers.add_parser(
        "uninstall-plugin", help="Uninstall a plugin by name"
    )
    uninstall_parser.add_argument("name", help="Plugin name to uninstall")

    subparsers.add_parser("list-plugins", help="List installed plugins")

    update_parser = subparsers.add_parser(
        "update-plugin", help="Update one or all plugins"
    )
    update_parser.add_argument(
        "name", nargs="?", default=None, help="Plugin name (omit for all)"
    )

    _add_common_args(parser)

    return parser


def _create_base_parser() -> argparse.ArgumentParser:
    """Create a parser without plugin subcommands but with the positional command arg.

    Used by main() when no plugin subcommand is detected, so that free-form
    command strings (e.g. "ayder -w do something") are accepted as plain
    positionals without being validated against subcommand choices.
    """
    parser = argparse.ArgumentParser(
        prog="ayder", description="AI-powered CLI assistant"
    )
    _add_common_args(parser)

    # Positional command argument (not present in create_parser to avoid
    # conflicting with plugin subcommand choices)
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
        _run_temporal_queue_cli,
    )

    _PLUGIN_SUBCOMMANDS = {
        "install-plugin", "uninstall-plugin", "list-plugins", "update-plugin"
    }
    # Detect plugin subcommands before building the parser.  When argparse
    # has subparsers configured, any unrecognised positional string is
    # validated against the subcommand choices and raises an error — even
    # through parse_known_args.  We avoid this by only engaging the
    # subcommand parser when the invocation actually starts with a known
    # plugin subcommand name.
    raw_args = sys.argv[1:]
    non_option_args = [a for a in raw_args if not a.startswith("-")]
    _is_plugin_subcommand = bool(
        non_option_args and non_option_args[0] in _PLUGIN_SUBCOMMANDS
    )

    if _is_plugin_subcommand:
        parser = create_parser()
        args = parser.parse_args()
        args.command = None
    else:
        # Build the parser without subparsers so a free-form "ayder -w do X"
        # command string is accepted as a plain positional.
        parser = _create_base_parser()
        args = parser.parse_args()
        args.subcommand = None

    # Handle plugin subcommands
    if args.subcommand == "install-plugin":
        from ayder_cli.tools.plugin_manager import install_plugin, uninstall_plugin, PluginError
        try:
            manifest = install_plugin(
                args.source,
                project_local=args.project,
                project_path=Path.cwd() if args.project else None,
                force=args.force,
            )
            # Handle dependencies
            if manifest.dependencies:
                print(f"Plugin '{manifest.name}' requires dependencies:")
                for dep, version in manifest.dependencies.items():
                    print(f"  {dep} {version}")
                if getattr(args, "yes", False):
                    confirm = "y"
                else:
                    confirm = input("Install dependencies? [y/N] ")
                if confirm.lower() == "y":
                    try:
                        _install_plugin_deps(manifest.dependencies)
                    except Exception as e:
                        # Rollback: remove the installed plugin
                        uninstall_plugin(
                            manifest.name,
                            project_path=Path.cwd() if args.project else None,
                        )
                        print(f"Error installing dependencies: {e}", file=sys.stderr)
                        print(f"Plugin '{manifest.name}' removed (rollback).", file=sys.stderr)
                        sys.exit(1)
            print(f"Plugin '{manifest.name}' v{manifest.version} installed.")
        except PluginError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.subcommand == "uninstall-plugin":
        from ayder_cli.tools.plugin_manager import uninstall_plugin, PluginError
        try:
            uninstall_plugin(args.name, project_path=Path.cwd())
            print(f"Plugin '{args.name}' uninstalled.")
        except PluginError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.subcommand == "list-plugins":
        from ayder_cli.tools.plugin_manager import list_installed_plugins
        plugins = list_installed_plugins(project_path=Path.cwd())
        if not plugins:
            print("No plugins installed.")
        else:
            print("Installed plugins:")
            for p in plugins:
                source_info = p.get("source", "unknown")
                scope = p.get("scope", "global")
                print(f"  {p['name']:20s} v{p['version']:10s} ({scope}: {source_info})")
        return

    if args.subcommand == "update-plugin":
        from ayder_cli.tools.plugin_manager import update_plugin, PluginError
        try:
            updated = update_plugin(args.name, project_path=Path.cwd())
            if updated:
                print(f"Updated: {', '.join(updated)}")
            else:
                print("No plugins to update.")
        except PluginError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Build granted permissions set from flags
    # Read tools are auto-approved by default (use --no-r to disable)
    granted = {"r"}
    if args.w:
        granted.add("w")
    if args.x:
        granted.add("x")
    if args.http:
        granted.add("http")

    from ayder_cli.core.config import load_config

    cfg = load_config(notify_migration=True, output=print)
    
    # Priority: 1. --verbose level, 2. --logging-level, 3. config.logging_level
    effective_log_level = args.verbose or args.logging_level
    
    setup_logging(
        cfg,
        level_override=effective_log_level,
        console_stream=sys.stdout if args.verbose is not None else None,
    )

    # Handle task-related CLI options
    if args.tasks:
        sys.exit(_run_tasks_cli())
    if args.implement:
        sys.exit(
            _run_implement_cli(
                args.implement, permissions=granted
            )
        )
    if args.implement_all:
        sys.exit(_run_implement_all_cli(permissions=granted))
    if getattr(args, "temporal_task_queue", None):
        sys.exit(
            _run_temporal_queue_cli(
                queue_name=args.temporal_task_queue,
                prompt_path=args.prompt,
                permissions=granted,
            )
        )

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

        run_tui(permissions=granted)
        return

    sys.exit(run_command(prompt, permissions=granted))


def _install_plugin_deps(dependencies: dict[str, str]) -> None:
    """Install plugin pip dependencies via uv pip or pip fallback.

    uv pip is tried first. If uv is not installed (FileNotFoundError), pip is
    tried. If uv is found but returns a non-zero exit code (CalledProcessError),
    the error propagates immediately — pip is NOT tried as a fallback for failed
    installs.
    """
    import subprocess
    pkgs = [f"{name}{ver}" for name, ver in dependencies.items()]
    for cmd in (["uv", "pip", "install"], ["pip", "install"]):
        try:
            subprocess.run([*cmd, *pkgs], check=True)
            return
        except FileNotFoundError:
            # Binary not found — try next fallback
            continue
    print("Warning: Could not find uv or pip to install dependencies.")


if __name__ == "__main__":
    main()
