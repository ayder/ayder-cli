"""/skill appends the skill block as a user message (spec 4.6)."""

from unittest.mock import MagicMock

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.skills import active_skills
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

    chat_view.add_system_message.assert_called_once_with("No skills found.")


def test_handle_skill_unknown_reports_available(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    handle_skill(app, "missing", chat_view)

    chat_view.add_system_message.assert_called_once_with(
        "Unknown skill: 'missing'. Available: alpha"
    )
    app.request_turn.assert_not_called()


def test_direct_load_appends_the_block_in_place(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    original = app.messages
    chat_view = MagicMock()

    handle_skill(app, "alpha", chat_view)

    assert app.messages is original
    assert app.messages[0] == {"role": "system", "content": "base"}
    assert app.messages[1]["role"] == "user"
    assert app.messages[1]["content"].startswith("### SKILL LOADED: alpha\n")
    assert [load.name for load in active_skills(app.messages)] == ["alpha"]
    chat_view.add_system_message.assert_called_once_with("Activated skill: alpha")
    app.query_one.return_value.set_skill.assert_called_with("alpha")
    assert app._last_request["run_loop"]() is False


def test_trailing_prompt_shares_the_block_message(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    handle_skill(app, "alpha fix this", chat_view)

    assert len(app.messages) == 2
    assert app.messages[1]["content"].endswith("### END SKILL: alpha\n\nfix this")
    chat_view.add_user_message.assert_called_once_with("fix this")
    assert app._last_request["run_loop"]() is True


def test_second_load_reports_already_active(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    handle_skill(app, "alpha", chat_view)
    handle_skill(app, "alpha", chat_view)

    assert len(app.messages) == 2
    chat_view.add_system_message.assert_called_with("Skill 'alpha' is already active.")


def test_request_with_an_active_skill_still_runs(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    handle_skill(app, "alpha", chat_view)
    handle_skill(app, "alpha fix the next failure", chat_view)

    assert len(app.messages) == 3
    assert app.messages[2] == {"role": "user", "content": "fix the next failure"}
    assert app.messages[2]["content"].count("### SKILL LOADED") == 0
    chat_view.add_user_message.assert_called_once_with("fix the next failure")
    assert app._last_request["run_loop"]() is True


def test_user_load_advances_the_agent_generation(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    app._agent_registry = MagicMock()
    chat_view = MagicMock()

    handle_skill(app, "alpha", chat_view)
    handle_skill(app, "alpha", chat_view)  # already active: no second bump

    app._agent_registry.new_generation.assert_called_once()


def test_picker_selection_appends_the_block(tmp_path):
    _write_skill(tmp_path, "alpha")
    app = _app(tmp_path)
    chat_view = MagicMock()

    def push_screen(_screen, callback):
        callback("alpha")

    app.push_screen.side_effect = push_screen
    handle_skill(app, "", chat_view)

    assert [load.name for load in active_skills(app.messages)] == ["alpha"]


def test_old_injected_message_is_inert():
    old = {"role": "system", "content": "### ACTIVE SKILL: alpha\nSCOPE: ...\n### END SKILL"}
    assert active_skills([{"role": "system", "content": "base"}, old]) == []


def test_app_has_no_injection_api():
    from ayder_cli.tui.app import AyderApp

    assert not hasattr(AyderApp, "inject_skill")
    assert not hasattr(AyderApp, "unload_skill")
