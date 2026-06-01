"""Verify registry dependency injection by callable signature."""

from unittest.mock import MagicMock

from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.registry import ToolRegistry


def _tool_with_context_manager(project_ctx, context_manager, foo: str):
    return f"ctx_mgr={context_manager.tag} foo={foo}"


def _tool_with_app(project_ctx, app, foo: str):
    return f"app_msgs={len(app.messages)} foo={foo}"


def test_registry_injects_context_manager(tmp_path):
    project_ctx = ProjectContext(tmp_path)
    fake_mgr = MagicMock(tag="MGR")
    registry = ToolRegistry(project_ctx, context_manager=fake_mgr)
    registry.register("ctxtool", _tool_with_context_manager)

    result = registry.execute("ctxtool", {"foo": "bar"})

    assert "ctx_mgr=MGR" in str(result)
    assert "foo=bar" in str(result)


def test_registry_injects_app(tmp_path):
    project_ctx = ProjectContext(tmp_path)
    fake_app = MagicMock(messages=[1, 2, 3])
    registry = ToolRegistry(project_ctx, app=fake_app)
    registry.register("apptool", _tool_with_app)

    result = registry.execute("apptool", {"foo": "bar"})

    assert "app_msgs=3" in str(result)


def test_registry_skips_injection_when_param_absent(tmp_path):
    def simple_tool(project_ctx, foo: str):
        return f"foo={foo}"

    project_ctx = ProjectContext(tmp_path)
    registry = ToolRegistry(project_ctx)
    registry.register("simpletool", simple_tool)

    result = registry.execute("simpletool", {"foo": "bar"})

    assert "foo=bar" in str(result)
