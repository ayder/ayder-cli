from unittest.mock import MagicMock, patch

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess
from ayder_cli.tui import commands
from ayder_cli.tui.commands import COMMAND_MAP, handle_skill


def _write_skill(tmp_path, name: str, content: str = "Skill body") -> None:
    skill_dir = tmp_path / ".ayder" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _app(tmp_path):
    from ayder_cli.tui.app import AyderApp

    app = AyderApp.__new__(AyderApp)
    app.registry = MagicMock()
    app.registry.project_ctx = ProjectContext(str(tmp_path))
    app.messages = [{"role": "system", "content": "base"}]
    app._active_skill = None
    app._agent_registry = None
    app.query_one = MagicMock(return_value=MagicMock())
    app.push_screen = MagicMock()

    def request_turn(prepare=None, **kwargs):
        if prepare is not None:
            prepare()
        app._last_request = kwargs

    app.request_turn = MagicMock(side_effect=request_turn)
    return app


def test_skill_command_registered():
    assert COMMAND_MAP["/skill"] is handle_skill


def test_handle_skill_no_skills_reports_message(tmp_path):
    app = _app(tmp_path)
    chat_view = MagicMock()

    handle_skill(app, "", chat_view)

    chat_view.add_system_message.assert_called_once_with(
        "No skills found in .ayder/skills/"
    )


def test_handle_skill_unknown_reports_available(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    handle_skill(app, "missing", chat_view)

    chat_view.add_system_message.assert_called_once_with(
        "Unknown skill: 'missing'. Available: alpha"
    )
    app.request_turn.assert_not_called()


def test_handle_skill_direct_load_delegates_to_skill_tool(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    with patch(
        "ayder_cli.tui.commands.skill",
        return_value=ToolSuccess("Activated skill: alpha"),
    ) as skill_tool:
        handle_skill(app, "alpha", chat_view)

    skill_tool.assert_called_once_with(
        project_ctx=app.registry.project_ctx,
        app=app,
        action="load",
        name="alpha",
    )
    chat_view.add_system_message.assert_called_once_with("Activated skill: alpha")


def test_handle_skill_with_trailing_prompt_loads_then_appends_prompt(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    handle_skill(app, "alpha fix this", chat_view)

    assert app._active_skill == "alpha"
    chat_view.add_user_message.assert_called_once_with("fix this")
    assert app.messages[-1] == {"role": "user", "content": "fix this"}
    assert app._last_request["run_loop"]() is True


def test_handle_skill_picker_selection_delegates_to_skill_tool(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    def push_screen(_screen, callback):
        callback("alpha")

    app.push_screen.side_effect = push_screen
    with patch(
        "ayder_cli.tui.commands.skill",
        return_value=ToolSuccess("Activated skill: alpha"),
    ) as skill_tool:
        handle_skill(app, "", chat_view)

    skill_tool.assert_called_once_with(
        project_ctx=app.registry.project_ctx,
        app=app,
        action="load",
        name="alpha",
    )


def test_handle_skill_no_direct_injection_helper_exists():
    assert not hasattr(commands, "_apply_skill")
    assert not hasattr(commands, "_discover_skills")
