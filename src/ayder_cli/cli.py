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
        "--temporal-prompt",
        type=str,
        default=None,
        metavar="FILE",
        help="Prompt file for the Temporal worker (only used with --temporal-task-queue)",
    )
    parser.add_argument(
        "--system-prompt",
        type=str,
        default=None,
        metavar="FILE",
        help="Use FILE's contents as the main LLM system prompt, overriding the "
        "built-in prompt from prompts.py (tool instructions and project structure "
        "are still appended)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        metavar="FILE",
        help="Path to a config.toml to use instead of ~/.ayder/config.toml",
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
        "-x", action="store_true", help="Auto-approve execute tools (bash)"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Auto-approve web/network tools (fetch_web)",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Agent harness mode: inject the AGENTIC orchestrator system prompt so the "
        "main LLM drives the configured agents (spec -> plan -> build -> QA -> review -> gate). "
        "Implies write+execute+http permissions (the agents run unattended)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show logs on the console. The level comes from --logging-level (or "
        "config); if neither is set, defaults to INFO. Does not otherwise change "
        "the log level.",
    )
    parser.add_argument(
        "--logging-level",
        type=str.upper,
        choices=LOG_LEVELS,
        metavar="LEVEL",
        default=None,
        help="Set the logging level for this session (e.g. DEBUG, INFO). Logs are written to .ayder/log/ayder.log",
    )

    parser.add_argument(
        "--resume",
        type=str,
        metavar="ID",
        default=None,
        help="Resume a saved session by id (or unique prefix) from "
        ".ayder/sessions/. Takes no other session options "
        "(restores the original model, permissions, and system prompt).",
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

    # Apply the -c/--config override before anything reads the config file.
    if getattr(args, "config", None):
        from ayder_cli.core.config import set_config_path

        config_file = Path(args.config).expanduser()
        if not config_file.is_file():
            print(f"Error: Config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        set_config_path(config_file)

    # Handle plugin subcommands
    if args.subcommand == "install-plugin":
        from ayder_cli.tools.plugin_manager import (
            install_plugin,
            install_plugin_dependencies,
            uninstall_plugin,
            PluginError,
        )
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
                        install_plugin_dependencies(manifest.dependencies)
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

    # --resume: restore a saved session and launch the TUI. It is mutually
    # exclusive with session-shaping options — the saved file already carries
    # the model, permissions, agent mode, and system prompt.
    if getattr(args, "resume", None):
        _conflicts: list[str] = []
        if getattr(args, "agent", False):
            _conflicts.append("--agent")
        if getattr(args, "system_prompt", None):
            _conflicts.append("--system-prompt")
        if getattr(args, "w", False):
            _conflicts.append("-w")
        if getattr(args, "x", False):
            _conflicts.append("-x")
        if getattr(args, "http", False):
            _conflicts.append("--http")
        if getattr(args, "file", None):
            _conflicts.append("--file/-f")
        if getattr(args, "stdin", False):
            _conflicts.append("--stdin")
        if getattr(args, "command", None):
            _conflicts.append("a command")
        if getattr(args, "implement", None):
            _conflicts.append("--implement")
        if getattr(args, "implement_all", False):
            _conflicts.append("--implement-all")
        if getattr(args, "tasks", False):
            _conflicts.append("--tasks")
        if getattr(args, "temporal_task_queue", None):
            _conflicts.append("--temporal-task-queue")
        if getattr(args, "temporal_prompt", None):
            _conflicts.append("--temporal-prompt")
        if _conflicts:
            print(
                "Error: --resume takes no other options — it restores the "
                "original session's settings. Usage: ayder --resume <id>",
                file=sys.stderr,
            )
            sys.exit(1)

        from ayder_cli.core.session import SessionError, load_session

        try:
            sess = load_session(args.resume)
        except SessionError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        from ayder_cli.tui import run_tui

        run_tui(
            model=sess.model or "default",
            safe_mode=sess.safe_mode,
            permissions=set(sess.permissions),
            agent_mode=sess.agent_mode,
            initial_messages=sess.messages,
            resume_session_id=sess.session_id,
        )
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
    # --agent runs an autonomous orchestrator whose agents must write code, run
    # commands, and fetch docs unattended — imply write+execute+http.
    if args.agent:
        granted.update({"w", "x", "http"})

    from ayder_cli.core.config import load_config

    cfg = load_config(notify_migration=True, output=print)
    
    # --verbose only enables console output; the level comes from --logging-level
    # (or config.logging_level). When --verbose is used with no level configured
    # anywhere, default the console to INFO so it isn't empty.
    effective_log_level = args.logging_level
    if args.verbose and effective_log_level is None and cfg.logging_level is None:
        effective_log_level = "INFO"

    setup_logging(
        cfg,
        level_override=effective_log_level,
        console_stream=sys.stdout if args.verbose else None,
    )

    # --agent: warn early if the harness has nothing to orchestrate.
    if args.agent and not (isinstance(cfg.agents, dict) and cfg.agents):
        print(
            "Warning: --agent set but no agents are configured in config.toml "
            "([agents.*] sections). See docs/config.toml.example.",
            file=sys.stderr,
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
                prompt_path=args.temporal_prompt,
                permissions=granted,
            )
        )

    # Read the --system-prompt override file (overrides prompts.py base prompt).
    system_prompt_override = None
    if args.system_prompt:
        sp_file = Path(args.system_prompt).expanduser()
        try:
            system_prompt_override = sp_file.read_text()
        except FileNotFoundError:
            print(
                f"Error: System prompt file not found: {args.system_prompt}",
                file=sys.stderr,
            )
            sys.exit(1)
        except Exception as e:
            print(
                f"Error reading system prompt file {args.system_prompt}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

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

        run_tui(
            permissions=granted,
            agent_mode=args.agent,
            system_prompt_override=system_prompt_override,
        )
        return

    sys.exit(
        run_command(
            prompt,
            permissions=granted,
            agent_mode=args.agent,
            system_prompt_override=system_prompt_override,
        )
    )


if __name__ == "__main__":
    main()
