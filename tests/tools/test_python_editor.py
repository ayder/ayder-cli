"""Tests for the python_editor tool."""

import json
from pathlib import Path

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.python_editor import PythonEditorBackend, python_editor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CODE = '''\
import os
from pathlib import Path

MY_VAR: int = 42

def greet(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}"

def helper():
    pass

class UserSession:
    """A user session."""

    active: bool = True

    def login(self, user: str):
        """Log the user in."""
        self.user = user

    def logout(self):
        """Log the user out."""
        self.user = None

def use_greet():
    return greet("world")
'''


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    f = tmp_path / "sample.py"
    f.write_text(SAMPLE_CODE)
    return f


@pytest.fixture
def ctx(tmp_path: Path) -> ProjectContext:
    return ProjectContext(str(tmp_path))


# ---------------------------------------------------------------------------
# python_editor dispatcher tests
# ---------------------------------------------------------------------------


class TestPythonEditorDispatcher:
    def test_invalid_json_params(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "get", params="{bad json")
        assert isinstance(result, ToolError)
        assert "Invalid JSON" in result

    def test_params_not_dict(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "get", params='"string"')
        assert isinstance(result, ToolError)
        assert "JSON object" in result

    def test_file_not_found(self, ctx, tmp_path):
        result = python_editor(ctx, str(tmp_path / "nonexistent.py"), "list_all")
        assert isinstance(result, ToolError)
        assert "not found" in result.lower() or "STRUCTURAL_ERROR" in result

    def test_unknown_method(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "bogus")
        assert isinstance(result, ToolError)
        assert "Unknown method" in result or "STRUCTURAL_ERROR" in result

    def test_success_returns_tool_success(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "list_all")
        assert isinstance(result, ToolSuccess)


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


class TestListAll:
    def test_lists_functions_classes_vars(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "list_all")
        assert "func: greet" in result
        assert "func: helper" in result
        assert "class: UserSession" in result
        assert "var: MY_VAR" in result
        assert "func: use_greet" in result

    def test_lists_class_methods(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "list_all")
        assert "method: UserSession.login" in result
        assert "method: UserSession.logout" in result

    def test_empty_file(self, ctx, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        result = python_editor(ctx, str(f), "list_all")
        assert "No symbols" in result


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_function(self, ctx, sample_file):
        params = json.dumps({"target_name": "greet"})
        result = python_editor(ctx, str(sample_file), "get", params)
        assert "def greet" in result
        assert "Hello" in result

    def test_get_class(self, ctx, sample_file):
        params = json.dumps({"target_name": "UserSession"})
        result = python_editor(ctx, str(sample_file), "get", params)
        assert "class UserSession" in result
        assert "def login" in result

    def test_get_dotted_name(self, ctx, sample_file):
        params = json.dumps({"target_name": "UserSession.login"})
        result = python_editor(ctx, str(sample_file), "get", params)
        assert "def login" in result
        assert "self.user = user" in result

    def test_get_variable(self, ctx, sample_file):
        params = json.dumps({"target_name": "MY_VAR"})
        result = python_editor(ctx, str(sample_file), "get", params)
        assert "MY_VAR" in result
        assert "42" in result

    def test_get_missing_target(self, ctx, sample_file):
        params = json.dumps({"target_name": "nonexistent"})
        result = python_editor(ctx, str(sample_file), "get", params)
        assert isinstance(result, ToolError)

    def test_get_missing_param(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "get", "{}")
        assert isinstance(result, ToolError)


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------


class TestRename:
    def test_rename_function_and_references(self, ctx, sample_file):
        params = json.dumps({"old_name": "greet", "new_name": "say_hello"})
        result = python_editor(ctx, str(sample_file), "rename", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "def say_hello" in content
        assert "say_hello(" in content  # reference in use_greet
        assert "def greet" not in content

    def test_rename_missing_params(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "rename", "{}")
        assert isinstance(result, ToolError)


# ---------------------------------------------------------------------------
# replace
# ---------------------------------------------------------------------------


class TestReplace:
    def test_replace_function(self, ctx, sample_file):
        new_code = 'def helper():\n    return "replaced"\n'
        params = json.dumps({"target_name": "helper", "new_code": new_code})
        result = python_editor(ctx, str(sample_file), "replace", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert '"replaced"' in content

    def test_replace_class_method(self, ctx, sample_file):
        new_code = '    def login(self, user: str, password: str):\n        self.user = user\n        self.password = password\n'
        params = json.dumps(
            {"target_name": "UserSession.login", "new_code": new_code}
        )
        result = python_editor(ctx, str(sample_file), "replace", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "password" in content

    def test_replace_not_found(self, ctx, sample_file):
        params = json.dumps({"target_name": "missing", "new_code": "def x(): pass"})
        result = python_editor(ctx, str(sample_file), "replace", params)
        assert isinstance(result, ToolError)

    def test_replace_missing_params(self, ctx, sample_file):
        result = python_editor(
            ctx, str(sample_file), "replace", json.dumps({"target_name": "helper"})
        )
        assert isinstance(result, ToolError)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_function(self, ctx, sample_file):
        params = json.dumps({"target_name": "helper"})
        result = python_editor(ctx, str(sample_file), "delete", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "def helper" not in content
        # Other functions should still be present
        assert "def greet" in content

    def test_delete_class_method(self, ctx, sample_file):
        params = json.dumps({"target_name": "UserSession.logout"})
        result = python_editor(ctx, str(sample_file), "delete", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "def logout" not in content
        assert "def login" in content  # other method preserved

    def test_delete_not_found(self, ctx, sample_file):
        params = json.dumps({"target_name": "missing"})
        result = python_editor(ctx, str(sample_file), "delete", params)
        assert isinstance(result, ToolError)


# ---------------------------------------------------------------------------
# add_decorator
# ---------------------------------------------------------------------------


class TestAddDecorator:
    def test_add_decorator_to_function(self, ctx, sample_file):
        params = json.dumps({"target_name": "greet", "decorator": "cache"})
        result = python_editor(ctx, str(sample_file), "add_decorator", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "@cache" in content

    def test_add_decorator_with_args(self, ctx, sample_file):
        params = json.dumps(
            {"target_name": "greet", "decorator": "rate_limit(5)"}
        )
        result = python_editor(ctx, str(sample_file), "add_decorator", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "@rate_limit(5)" in content

    def test_add_decorator_with_at_sign(self, ctx, sample_file):
        params = json.dumps({"target_name": "greet", "decorator": "@staticmethod"})
        result = python_editor(ctx, str(sample_file), "add_decorator", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "@staticmethod" in content

    def test_add_decorator_to_class(self, ctx, sample_file):
        params = json.dumps({"target_name": "UserSession", "decorator": "dataclass"})
        result = python_editor(ctx, str(sample_file), "add_decorator", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "@dataclass" in content

    def test_add_decorator_not_found(self, ctx, sample_file):
        params = json.dumps({"target_name": "missing", "decorator": "cache"})
        result = python_editor(ctx, str(sample_file), "add_decorator", params)
        assert isinstance(result, ToolError)


# ---------------------------------------------------------------------------
# add_import
# ---------------------------------------------------------------------------


class TestAddImport:
    def test_add_plain_import(self, ctx, sample_file):
        params = json.dumps({"module": "sys"})
        result = python_editor(ctx, str(sample_file), "add_import", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "import sys" in content

    def test_add_from_import(self, ctx, sample_file):
        params = json.dumps({"module": "typing", "name": "Optional"})
        result = python_editor(ctx, str(sample_file), "add_import", params)
        assert isinstance(result, ToolSuccess)

        content = sample_file.read_text()
        assert "from typing import Optional" in content

    def test_import_placed_after_existing_imports(self, ctx, sample_file):
        params = json.dumps({"module": "sys"})
        python_editor(ctx, str(sample_file), "add_import", params)

        content = sample_file.read_text()
        lines = content.splitlines()
        # Find the import sys line
        sys_idx = next(i for i, l in enumerate(lines) if "import sys" in l)
        # It should be after the existing "from pathlib import Path" line
        pathlib_idx = next(
            i for i, l in enumerate(lines) if "from pathlib import Path" in l
        )
        assert sys_idx > pathlib_idx

    def test_add_import_missing_module(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "add_import", "{}")
        assert isinstance(result, ToolError)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_verify_valid(self, ctx, sample_file):
        result = python_editor(ctx, str(sample_file), "verify")
        assert isinstance(result, ToolSuccess)
        assert "valid" in result.lower()

    def test_verify_invalid(self, ctx, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        result = python_editor(ctx, str(f), "verify")
        # The initial parse in __init__ will fail, so we get a STRUCTURAL_ERROR
        assert isinstance(result, ToolError)
        assert "STRUCTURAL_ERROR" in result or "Syntax" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_default_params_omitted(self, ctx, sample_file):
        """list_all works without explicit params."""
        result = python_editor(ctx, str(sample_file), "list_all")
        assert isinstance(result, ToolSuccess)

    def test_chained_operations(self, ctx, sample_file):
        """Multiple operations in sequence work correctly."""
        # Rename greet -> say_hello
        python_editor(
            ctx,
            str(sample_file),
            "rename",
            json.dumps({"old_name": "greet", "new_name": "say_hello"}),
        )
        # Add decorator
        python_editor(
            ctx,
            str(sample_file),
            "add_decorator",
            json.dumps({"target_name": "say_hello", "decorator": "cache"}),
        )
        # Verify final state
        content = sample_file.read_text()
        assert "def say_hello" in content
        assert "@cache" in content
        assert "def greet" not in content
