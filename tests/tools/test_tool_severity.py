"""Tool severity, asserted on the production call path."""
from unittest.mock import MagicMock, patch

import pytest

# scripts/ is on sys.path via tests/conftest.py (§C15).
from logging_gates import BATCHES, collect, resolve  # noqa: E402


def test_download_file_is_trace_on_the_production_path(tmp_path, loguru_caplog):
    """`Downloading <name>` fires once per file -> TRACE, not DEBUG."""
    from ayder_cli.tools.plugin_github import _download_file

    payload = b"print('x')\n"
    response = MagicMock()
    response.read.return_value = payload
    response.__enter__ = lambda s: s
    response.__exit__ = lambda s, *a: False

    dest = tmp_path / "defs.py"
    with patch("ayder_cli.tools.plugin_github.urlopen", return_value=response):
        _download_file("https://example.invalid/defs.py", dest)

    assert dest.read_bytes() == payload
    hits = [r for r in loguru_caplog.records if r["message"].startswith("Downloading ")]
    assert hits, "download record never emitted"
    assert hits[0]["level"].name == "TRACE"
    assert hits[0]["extra"]["channel"] == "plugin"


def test_tool_dispatch_is_debug_on_the_production_path(tmp_path, loguru_caplog):
    """`Tool call:` is one record per call -> DEBUG, and it does not move."""
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.tools.builtins.shell import bash
    from ayder_cli.tools.execution import execute_tool
    from ayder_cli.tools.hooks import HookManager

    ctx = ProjectContext(str(tmp_path))
    execute_tool("bash", {"command": "echo hi"}, bash, HookManager(), ctx)

    hits = [r for r in loguru_caplog.records if r["message"].startswith("Tool call:")]
    assert hits, "tool-call record never emitted"
    assert hits[0]["level"].name == "DEBUG"
    assert hits[0]["extra"]["channel"] == "tool"


def test_tool_dispatch_does_not_leak_argument_values_or_keys(tmp_path, loguru_caplog):
    """`Tool call:` must carry only the tool name and an argument count --
    never argument values (secrets) or argument keys (unvalidated, and thus
    a second leak surface). Regression for the tools/execution.py:108 leak
    (`args={'variable_name': 'OPENAI_API_KEY', 'value': 'sk-proj-...'}`)
    found in review of commit 38676b2."""
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.tools.builtins.utils_tools import manage_environment_vars
    from ayder_cli.tools.execution import execute_tool
    from ayder_cli.tools.hooks import HookManager

    secret = "sk-proj-SENTINEL-DO-NOT-LOG-1234567890"
    ctx = ProjectContext(str(tmp_path))
    execute_tool(
        "manage_environment_vars",
        {"mode": "set", "variable_name": "OPENAI_API_KEY", "value": secret},
        manage_environment_vars,
        HookManager(),
        ctx,
    )

    hits = [r for r in loguru_caplog.records if r["message"].startswith("Tool call:")]
    assert len(hits) == 1, "expected exactly one dispatch record"
    hit = hits[0]
    assert hit["level"].name == "DEBUG"
    assert hit["extra"]["channel"] == "tool"
    assert "manage_environment_vars" in hit["message"]
    assert "args)" in hit["message"], "record must still carry an argument count"
    # Neither the secret value nor the argument keys may appear.
    assert secret not in hit["message"]
    assert "OPENAI_API_KEY" not in hit["message"]
    assert "variable_name" not in hit["message"]
    assert "value" not in hit["message"]
    # Nothing else logged during dispatch leaks it either.
    assert secret not in loguru_caplog.text


def test_no_warnings_on_the_happy_path(tmp_path, loguru_caplog):
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.tools.builtins.shell import bash
    from ayder_cli.tools.execution import execute_tool
    from ayder_cli.tools.hooks import HookManager

    execute_tool("bash", {"command": "echo hi"}, bash, HookManager(),
                 ProjectContext(str(tmp_path)))
    assert loguru_caplog.at_level("WARNING").messages == []


# --- AST assertion: supplements the production tests, never replaces them ---

EXPECTED = {
    "tools/plugin_github.py :: _download_file :: Downloading {}": "trace",
    "tools/plugin_github.py :: download_plugin :: Downloading '{}' at": "info",
    "tools/execution.py :: execute_tool :: Tool call:": "debug",
    "tools/plugin_manager.py :: discover_global_plugins :: Loaded global plugin": "info",
    "tools/builtins/context.py :: snapshot_conversation_for_clear :: Recovery snapshot save returned error:": "warning",
    "cli_runner.py :: _run_loop :: Registered {} agent(s):": "info",
}


@pytest.mark.parametrize("identity,level", sorted(EXPECTED.items()))
def test_frozen_levels(identity, level):
    assert resolve(identity, collect(BATCHES["tools-root"]))["level"] == level
