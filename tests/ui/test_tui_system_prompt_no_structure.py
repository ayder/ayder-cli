"""The TUI's system prompt builds carry no project tree.

Kind: new interface. Startup (_init_system_prompt) and the model-switch
rebuild (update_system_prompt_model) used to call get_project_structure and
append a "### PROJECT STRUCTURE:" block, which models read as a cue to list
the project's files on any greeting.
"""

from unittest.mock import MagicMock

from ayder_cli.core.config import Config


def _app():
    from ayder_cli.tui.app import AyderApp

    app = AyderApp.__new__(AyderApp)
    app.registry = MagicMock()
    app.registry.execute.return_value = "tree"
    app.registry.get_system_prompts.return_value = "[TOOLS]"
    app.config = Config()
    app._system_prompt_override = None
    app.messages = []
    app.chat_loop = MagicMock()
    app.chat_loop.config.tool_tags = frozenset({"core"})
    return app


def test_startup_prompt_has_no_project_structure():
    app = _app()
    app._init_system_prompt()
    content = app.messages[0]["content"]
    assert content.endswith("[TOOLS]")
    assert "PROJECT STRUCTURE" not in content
    app.registry.execute.assert_not_called()


def test_model_switch_rebuild_has_no_project_structure():
    app = _app()
    app.messages = [{"role": "system", "content": "old"}]
    app.update_system_prompt_model()
    assert app.messages[0]["content"].endswith("[TOOLS]")
    assert "PROJECT STRUCTURE" not in app.messages[0]["content"]
    app.registry.execute.assert_not_called()
