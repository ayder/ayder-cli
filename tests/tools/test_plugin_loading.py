"""Integration tests for external plugin loading into the tool registry."""

import sys
from pathlib import Path

import pytest

from ayder_cli.tools.plugin_manager import (
    load_plugin_definitions,
    PluginError,
)


@pytest.fixture
def valid_plugin(tmp_path):
    """Create a valid plugin with definitions and implementation."""
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()

    (plugin_dir / "plugin.toml").write_text("""\
[plugin]
name = "test-plugin"
version = "1.0.0"
api_version = 1
description = "Test"
author = "test"

[tools]
definitions = "test_defs.py"
""")
    (plugin_dir / "test_defs.py").write_text("""\
from ayder_cli.tools.definition import ToolDefinition

TOOL_DEFINITIONS = (
    ToolDefinition(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        tags=("test",),
        func_ref="test_impl:test_func",
    ),
)
""")
    (plugin_dir / "test_impl.py").write_text("""\
from ayder_cli.core.result import ToolSuccess

def test_func():
    return ToolSuccess("ok")
""")
    return plugin_dir


def test_load_plugin_definitions(valid_plugin):
    defs, handlers = load_plugin_definitions(valid_plugin)
    assert len(defs) == 1
    assert defs[0].name == "test_tool"
    assert "test_tool" in handlers
    assert callable(handlers["test_tool"])


def test_load_plugin_cleans_sys_path(valid_plugin):
    original_path = sys.path.copy()
    load_plugin_definitions(valid_plugin)
    assert str(valid_plugin) not in sys.path
    assert len(sys.path) == len(original_path)


def test_load_plugin_incompatible_api(tmp_path):
    plugin_dir = tmp_path / "bad-api"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.toml").write_text("""\
[plugin]
name = "bad-api"
version = "1.0.0"
api_version = 999
description = "Future plugin"
author = "test"

[tools]
definitions = "defs.py"
""")
    (plugin_dir / "defs.py").write_text("TOOL_DEFINITIONS = ()")
    with pytest.raises(PluginError, match="API"):
        load_plugin_definitions(plugin_dir)


def test_load_plugin_definition_empty_func_ref(tmp_path):
    plugin_dir = tmp_path / "empty-func-ref"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.toml").write_text("""\
[plugin]
name = "empty-func-ref"
version = "1.0.0"
api_version = 1
description = "Plugin with empty func_ref"
author = "test"

[tools]
definitions = "defs.py"
""")
    (plugin_dir / "defs.py").write_text("""\
from ayder_cli.tools.definition import ToolDefinition

TOOL_DEFINITIONS = (
    ToolDefinition(
        name="no_ref_tool",
        description="A tool with no func_ref",
        parameters={"type": "object", "properties": {}},
        tags=("test",),
        func_ref="",
    ),
)
""")
    with pytest.raises(PluginError, match="func_ref"):
        load_plugin_definitions(plugin_dir)
