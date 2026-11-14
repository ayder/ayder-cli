"""Startup logs nothing to stderr before logging is configured, and the records it
does log (tool discovery) reach the configured sinks.

Discovery runs once per interpreter, at the first import of
ayder_cli.tools.definition, so the startup tests run main() in a fresh
interpreter. HOME, the working directory, the config and the log files all live
under tmp_path: the real ~/.ayder and the repo's .ayder/log are never touched.
No network (environment: local-faked).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

LOGURU_LINE = re.compile(r"\| (TRACE|DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL) +\|")
MAIN = (
    "import sys; sys.argv = ['ayder', *sys.argv[1:]]\n"
    "from ayder_cli.cli import main\n"
    "main()\n"
    "import json, ayder_cli.core.skills as s\n"
    "print(json.dumps([str(s.USER_SKILLS_DIR), str(s.BUILTIN_HOME)]))\n"
)


def _run_ayder(tmp_path: Path, *argv: str):
    """Run `ayder --config=<tmp config> *argv` in a fresh interpreter, logging at DEBUG.

    One `--config=` token, not `-c <path>`: main() detects a plugin subcommand by
    the first argument not starting with "-", and a separate path would be it,
    turning `list-plugins` into a prompt for the one-shot (LLM) path.
    """
    home, work, logs = tmp_path / "home", tmp_path / "work", tmp_path / "log"
    home.mkdir()
    work.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'config_version = "2.0"\n\n[app]\nprovider = "openai"\n\n[logging]\n'
        f'level = "DEBUG"\nfile_path = "{logs / "ayder.log"}"\n'
        f'error_path = "{logs / "errors.log"}"\n\n'
        # A dead local port: a run that strays onto the LLM path fails fast
        # instead of reaching a real model (e.g. a local Ollama on 11434).
        '[llm.openai]\ndriver = "openai"\nbase_url = "http://127.0.0.1:9/v1"\n'
        'api_key = "none"\nmodel = "none"\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-c", MAIN, f"--config={cfg}", *argv],
        cwd=work, env={**os.environ, "HOME": str(home)}, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=60,
    )
    main_log = logs / "ayder.log"
    return proc, main_log.read_text() if main_log.exists() else "", home


@pytest.mark.parametrize("argv", [["--version"], ["--help"], ["list-plugins"]],
                         ids=["version", "help", "list-plugins"])
def test_startup_writes_no_log_records_to_stderr(tmp_path, argv):
    """Baseline regression: tool discovery logged through Loguru's stderr default
    before setup_logging() ran (14 lines before the banner, live)."""
    proc, _, _ = _run_ayder(tmp_path, *argv)
    assert proc.returncode == 0, proc.stderr
    leaked = [line for line in proc.stderr.splitlines() if LOGURU_LINE.search(line)]
    assert leaked == [], leaked


def test_discovery_records_reach_the_configured_log_file(tmp_path):
    """Baseline regression: the discovery records never reached ayder.log."""
    proc, log_text, _ = _run_ayder(tmp_path, "list-plugins")
    assert proc.returncode == 0, proc.stderr
    assert "Auto-discovered" in log_text, log_text   # INFO
    assert "Discovered " in log_text, log_text       # DEBUG, one per definitions module


def test_config_flag_leaves_skills_in_home(tmp_path):
    """Preservation: with -c, skills stay in ~/.ayder (README, "Skills"), not
    beside the given config file."""
    proc, _, home = _run_ayder(tmp_path, "list-plugins")
    assert proc.returncode == 0, proc.stderr
    user_dir, builtin_home = json.loads(proc.stdout.splitlines()[-1])
    assert Path(user_dir).resolve() == (home / ".ayder" / "skills").resolve()
    assert Path(builtin_home).resolve() == (home / ".ayder" / "builtin").resolve()
