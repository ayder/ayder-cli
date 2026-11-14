"""
CLI-style TUI (Terminal User Interface) for ayder-cli.

Provides a clean, terminal-like interface:
- Simple text output with prefixes (> for user, < for assistant)
- Minimal borders and chrome
- Slash command auto-completion
- Status bar with context info
"""

import os
import sys
from pathlib import Path

from ayder_cli.tui.types import MessageType, ConfirmResult
from ayder_cli.tui.screens import (
    CLIConfirmScreen,
    CLIHelpScreen,
    CLIPermissionScreen,
    CLISafeModeScreen,
    CLISelectScreen,
    TaskEditScreen,
)
from ayder_cli.tui.widgets import (
    ChatView,
    ToolPanel,
    AutoCompleteInput,
    CLIInputBar,
    StatusBar,
)
from ayder_cli.tui.app import AyderApp
from ayder_cli.log import get_logger
from ayder_cli.logging_config import get_log_dir

logger = get_logger("ui")


class _StderrCapture:
    """Keep stray output off the screen while the TUI runs.

    Textual draws the whole screen to ``sys.__stderr__`` and sizes it from
    ``sys.__stdout__``, so anything else that writes to fd 1 or 2 would show on
    top of the UI until the next repaint: C libraries, child processes that
    inherit the fds, plugins. This gives Textual a private dup of the terminal
    and points fds 1 and 2, and ``sys.stderr``, at ``stderr.log``. No Textual
    method is overridden. ``restore`` undoes it in reverse order; if the log
    cannot be opened, stray output is discarded instead.
    """

    def __init__(self, log_path: Path) -> None:
        for stream in (sys.stdout, sys.stderr):
            stream.flush()  # earlier output belongs to the terminal, not the file
        self.log_path = log_path
        self._saved_sys = (sys.__stdout__, sys.__stderr__, sys.stdout, sys.stderr)
        self._saved_fds = (os.dup(1), os.dup(2))
        self._tty = os.fdopen(
            os.dup(2), "w", buffering=1, encoding="utf-8", errors="replace"
        )
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            self._log = open(os.devnull, "w")
        self._log.write(f"--- ayder TUI pid {os.getpid()} ---\n")
        for name in ("__stdout__", "__stderr__", "stdout"):
            setattr(sys, name, self._tty)
        sys.stderr = self._log
        os.dup2(self._log.fileno(), 1)
        os.dup2(self._log.fileno(), 2)
        self._active = True

    def restore(self) -> None:
        if not self._active:
            return
        self._active = False
        self._tty.flush()
        self._log.flush()
        for stream in {id(s): s for s in self._saved_sys if s is not None}.values():
            stream.flush()  # whatever old-stream writers buffered goes to the file
        os.dup2(self._saved_fds[0], 1)
        os.dup2(self._saved_fds[1], 2)
        for name, stream in zip(
            ("__stdout__", "__stderr__", "stdout", "stderr"), self._saved_sys
        ):
            setattr(sys, name, stream)
        for fd in self._saved_fds:
            os.close(fd)
        self._log.close()
        self._tty.close()


def run_tui(
    model: str = "default",
    safe_mode: bool = False,
    permissions: set | None = None,
    agent_mode: bool = False,
    system_prompt_override: str | None = None,
    provider: str | None = None,
    initial_messages: list[dict] | None = None,
    resume_session_id: str | None = None,
    session_name: str | None = None,
    log_settings=None,          # LoggingSettings | None
) -> None:
    """
    Run the CLI-style TUI application.

    Args:
        model: The LLM model name to use
        safe_mode: Whether to enable safe mode
        permissions: Set of granted permission levels ("r", "w", "x")
        agent_mode: When True, inject the AGENTIC orchestrator system prompt
            so the main LLM drives the multi-agent harness (ayder-cli --agent).
        system_prompt_override: When set, use this text as the system-prompt base
            instead of the built-in prompts.py prompt (ayder --system-prompt FILE).
        provider: When resuming, the provider profile the session last used;
            None uses the config's default provider.
        initial_messages: When resuming, the restored conversation (incl. the
            saved system prompt) to seed the app with.
        resume_session_id: When resuming, the id of the session being continued
            so save-on-exit updates the same file.
        session_name: Handle peers address this session by on the messaging
            inbox. Defaults to the working directory's name.
        log_settings: Fully-resolved LoggingSettings from the CLI entry point.
            When None, AyderApp resolves its own (e.g. when constructed directly
            in tests).
    """
    from ayder_cli.providers import ProviderUnavailableError
    from ayder_cli.core.session import persist_and_announce

    capture = _StderrCapture(get_log_dir() / "stderr.log")
    built = False
    try:
        app = AyderApp(
            model=model, safe_mode=safe_mode, permissions=permissions,
            agent_mode=agent_mode, system_prompt_override=system_prompt_override,
            provider=provider, initial_messages=initial_messages, resume_session_id=resume_session_id,
            session_name=session_name, log_settings=log_settings,
        )
        built = True
    except ProviderUnavailableError as e:
        capture.restore()  # the message is for the terminal, not the log
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
    finally:
        if not built:
            capture.restore()

    try:
        app.run(inline=False, mouse=True)
    finally:
        # First, so the mouse reset and everything printed below reach the terminal.
        capture.restore()
        # Mouse is enabled for the session; make sure reporting is switched off
        # on exit — Textual's driver may leave it on if the shutdown path doesn't
        # fully complete (e.g. Ctrl+Q or a crash).
        sys.stdout.write(
            "\033[?1000l"  # disable mouse click tracking
            "\033[?1002l"  # disable mouse button-event tracking
            "\033[?1003l"  # disable all mouse tracking
            "\033[?1006l"  # disable SGR extended mouse mode
        )
        sys.stdout.flush()

        # Auto-save the conversation so it can be resumed later.
        try:
            persist_and_announce(
                app.messages,
                session_id=app.resume_session_id or getattr(app, "_transcript_id", None),
                model=app.model,
                agent_mode=agent_mode,
                safe_mode=app.safe_mode,
                permissions=app.permissions,
                system_prompt_override=system_prompt_override,
                # The live provider, so a /provider switch is what resumes.
                provider=getattr(getattr(app, "config", None), "provider", None),
            )
        except Exception as exc:  # noqa: BLE001 - exit-path boundary: never let a save failure mask the exit
            logger.opt(exception=True).warning("Session auto-save failed on exit")
            print(f"Warning: could not save session: {exc}", file=sys.stderr)

    if app.return_code:
        # Textual prints a crash traceback through sys.stderr while the capture
        # is on, so it is in the log; say so, or the user sees nothing.
        print(
            f"ayder exited with an error; traceback in {capture.log_path}",
            file=sys.stderr,
        )


__all__ = [
    "MessageType",
    "ConfirmResult",
    "CLIConfirmScreen",
    "CLIHelpScreen",
    "CLIPermissionScreen",
    "CLISafeModeScreen",
    "CLISelectScreen",
    "TaskEditScreen",
    "ChatView",
    "ToolPanel",
    "AutoCompleteInput",
    "CLIInputBar",
    "StatusBar",
    "AyderApp",
    "run_tui",
]
