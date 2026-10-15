"""Tool arguments are canonical before validation (H2: findings F9, F10, F11).

``ExecutionPolicy.execute_with_registry`` validated the raw arguments, so a
declared alias such as ``read_file(path=...)`` failed the required-argument
check before ``normalize_arguments`` could map it (F9). Boolean parameters
were never type-checked, so ``replace_all="false"`` and ``dry_run="false"``
were truthy strings (F10). A non-object argument value crashed the
required-argument check with ``TypeError`` (F11).
"""

from __future__ import annotations

import pytest

from ayder_cli.application.execution_policy import ExecutionPolicy, ToolRequest
from ayder_cli.application.validation import ValidationError
from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.normalization import canonicalize_arguments
from ayder_cli.tools.registry import create_default_registry


@pytest.fixture
def project(tmp_path):
    ctx = ProjectContext(str(tmp_path))
    return ctx, create_default_registry(ctx), tmp_path


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy({"r", "w"})


def test_policy_accepts_declared_alias(project):
    """Baseline regression (F9): fails with a missing 'file_path' today."""
    _, registry, root = project
    (root / "a.txt").write_text("hello\n")
    result = _policy().execute_with_registry(
        ToolRequest("read_file", {"path": "a.txt"}), registry, pre_approved=True
    )
    assert result.success, result.error
    assert "hello" in result.result


def test_string_false_keeps_non_unique_replace_from_running(project):
    """Baseline regression (F10): "false" is truthy today, so both matches
    are replaced. As a real False, the non-unique match is refused."""
    _, registry, root = project
    target = root / "f.txt"
    target.write_text("x = 1\nx = 1\n")
    before = target.read_bytes()
    result = _policy().execute_with_registry(
        ToolRequest(
            "file_editor",
            {"file_path": "f.txt", "operation": "replace", "old_string": "x = 1",
             "new_string": "x = 2", "replace_all": "false"},
        ),
        registry,
        pre_approved=True,
    )
    assert not result.success
    assert "not unique" in str(result.error)
    assert target.read_bytes() == before


def test_string_false_dry_run_is_not_a_preview(project):
    """Baseline regression (F10): dry_run="false" previews instead of writing today."""
    _, registry, root = project
    target = root / "g.txt"
    target.write_text("a\n")
    result = _policy().execute_with_registry(
        ToolRequest(
            "file_editor",
            {"file_path": "g.txt", "operation": "replace", "old_string": "a",
             "new_string": "b", "dry_run": "False"},
        ),
        registry,
        pre_approved=True,
    )
    assert result.success, result.error
    assert target.read_text() == "b\n"


def test_non_boolean_string_is_rejected(project):
    """Baseline regression (F10): "maybe" reaches the tool as a truthy value today."""
    _, registry, root = project
    target = root / "h.txt"
    target.write_text("x\nx\n")
    result = _policy().execute_with_registry(
        ToolRequest(
            "file_editor",
            {"file_path": "h.txt", "operation": "replace", "old_string": "x",
             "new_string": "y", "replace_all": "maybe"},
        ),
        registry,
        pre_approved=True,
    )
    assert not result.success
    assert isinstance(result.error, ValidationError)
    assert result.error.field == "replace_all"
    assert target.read_text() == "x\nx\n"


@pytest.mark.parametrize("arguments", [None, [], 1, "null"])
def test_non_dict_arguments_return_validation_error(project, arguments):
    """Baseline regression (F11): None/list/int crash with TypeError today."""
    _, registry, _ = project
    result = _policy().execute_with_registry(
        ToolRequest("read_file", arguments), registry, pre_approved=True
    )
    assert not result.success
    assert isinstance(result.error, ValidationError)
    assert "JSON object" in result.error.message


def test_integer_coercion_unchanged(project):
    """Preservation: "2" still becomes 2 for an integer parameter."""
    _, registry, root = project
    (root / "n.txt").write_text("1\n2\n3\n")
    result = _policy().execute_with_registry(
        ToolRequest("read_file", {"file_path": "n.txt", "start_line": "2",
                                  "end_line": "2"}),
        registry,
        pre_approved=True,
    )
    assert result.success, result.error
    assert result.result.startswith("2: 2\n")
    assert "3: 3" not in result.result


def test_canonicalize_arguments_resolves_alias_and_coercions():
    """New interface: the pure canonicalizer used by policy and loop gate."""
    raw = {"path": "a.txt", "replace_all": " TRUE ", "dry_run": "false",
           "line_number": "7"}
    out = canonicalize_arguments("file_editor", raw)
    assert out == {"file_path": "a.txt", "replace_all": True, "dry_run": False,
                   "line_number": 7}
    assert raw["path"] == "a.txt" and "file_path" not in raw  # input not mutated
