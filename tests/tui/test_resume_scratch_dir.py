"""A resumed session is started with, and saves, the scratch directory it used.

Kind: baseline regression. Live session (2026-11-25): ``ayder --resume`` created a new
scratch directory, so the file tools refused the one named all through the restored
history. Environment: local-faked (no network). ``run_tui`` is driven with a fake app
(Textual is not under test); the constructor test builds the real ``AyderApp``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import ayder_cli.tui as tui
from ayder_cli.core.context import new_scratch_dir
from ayder_cli.core.session import load_session
from ayder_cli.tui.app import AyderApp


def _fake_app(scratch: Path | None) -> MagicMock:
    app = MagicMock()
    app.return_code = 0  # a bare MagicMock is truthy
    app.messages = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    app.resume_session_id = None
    app._transcript_id = "aaaa-bbbb"
    app.model = "m"
    app.safe_mode = False
    app.permissions = {"r"}
    app.config.provider = None
    app.registry.project_ctx.scratch_dir = scratch
    return app


def test_run_tui_hands_the_saved_scratch_dir_to_the_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tui, "get_log_dir", lambda: tmp_path)  # stderr.log goes here
    with patch("ayder_cli.tui.AyderApp", return_value=_fake_app(None)) as app_class:
        tui.run_tui(resume_scratch_dir="/tmp/ayder-1/proj-abc/20261125-151818-271ec0")

    assert (
        app_class.call_args.kwargs.get("resume_scratch_dir")
        == "/tmp/ayder-1/proj-abc/20261125-151818-271ec0"
    )


def test_run_tui_saves_the_sessions_scratch_dir_on_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tui, "get_log_dir", lambda: tmp_path)
    scratch = tmp_path / "scratch" / "20261125-151818-271ec0"
    with patch("ayder_cli.tui.AyderApp", return_value=_fake_app(scratch)):
        tui.run_tui()

    assert load_session("aaaa-bbbb", root=tmp_path).scratch_dir == str(scratch)


def test_the_app_builds_its_runtime_on_the_saved_scratch_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    saved = new_scratch_dir(tmp_path).resolve()

    app = AyderApp(model="test", resume_scratch_dir=str(saved))

    assert app.registry.project_ctx.scratch_dir == saved
