"""The TUI keeps stray output off the screen.

Textual draws the whole screen to ``sys.__stderr__`` and sizes it from
``sys.__stdout__``, so anything else writing to fd 1 or 2 (C libraries, child
processes, plugins) would show on top of the UI. ``run_tui`` therefore gives
Textual a private dup of the terminal and points fds 1 and 2 at ``stderr.log``.

``_StderrCapture`` runs in a subprocess here so pytest's own fd capture is not
involved: the child's stdout and stderr are pipes, and "the terminal" is the
child's original stderr.
"""

import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

CHILD = textwrap.dedent(
    """
    import os, sys
    from pathlib import Path
    from ayder_cli.tui import _StderrCapture

    cap = _StderrCapture(Path(sys.argv[1]))

    os.write(1, b"DURING-FD1\\n")
    os.write(2, b"DURING-FD2\\n")
    print("DURING-PRINT-ERR", file=sys.stderr)
    print("TTY-STDOUT")

    tty = sys.__stderr__.fileno()
    assert sys.__stdout__.fileno() == tty and sys.stdout is sys.__stdout__
    assert tty not in (1, 2)
    assert not os.path.samestat(os.fstat(tty), os.fstat(2)), "the tty handle is the log"
    assert os.path.samestat(os.fstat(sys.stderr.fileno()), os.fstat(2)), "sys.stderr is not the log"

    cap.restore()
    os.write(1, b"AFTER-FD1\\n")
    os.write(2, b"AFTER-FD2\\n")
    print("AFTER-PRINT-ERR", file=sys.stderr)
    print("AFTER-PRINT")
    """
)


def _run_child(log: Path, code: str = CHILD):
    return subprocess.run(
        [sys.executable, "-c", code, str(log)], capture_output=True, text=True
    )


def test_capture_sends_stray_output_to_the_log_and_restore_gives_it_back(tmp_path):
    log = tmp_path / "logs" / "stderr.log"
    done = _run_child(log)
    assert done.returncode == 0, done.stderr

    text = log.read_text()
    assert "--- ayder TUI pid " in text
    for token in ("DURING-FD1", "DURING-FD2", "DURING-PRINT-ERR"):
        assert token in text
    for token in ("TTY-STDOUT", "AFTER-FD1", "AFTER-FD2", "AFTER-PRINT"):
        assert token not in text

    # While captured, nothing stray reached the terminal; sys.stdout is the
    # private terminal handle (the child's original stderr).
    assert "DURING" not in done.stdout and "DURING" not in done.stderr
    assert "TTY-STDOUT" in done.stderr
    # After restore the real streams are back.
    assert done.stdout.splitlines() == ["AFTER-FD1", "AFTER-PRINT"]
    assert "AFTER-FD2" in done.stderr and "AFTER-PRINT-ERR" in done.stderr


def test_unwritable_log_dir_discards_instead_of_failing(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    code = textwrap.dedent(
        """
        import os, sys
        from pathlib import Path
        from ayder_cli.tui import _StderrCapture

        cap = _StderrCapture(Path(sys.argv[1]) / "logs" / "stderr.log")
        os.write(2, b"DURING-FD2\\n")
        cap.restore()
        os.write(2, b"AFTER-FD2\\n")
        """
    )
    done = _run_child(blocker, code)
    assert done.returncode == 0, done.stderr
    assert "DURING-FD2" not in done.stderr and "AFTER-FD2" in done.stderr


# -- run_tui ----------------------------------------------------------------


def _run_tui_with(tmp_path, monkeypatch, return_code):
    import ayder_cli.tui as tui

    monkeypatch.setattr(tui, "get_log_dir", lambda: tmp_path)
    with patch("ayder_cli.tui.AyderApp") as mock_app:
        instance = MagicMock()
        instance.return_code = return_code
        mock_app.return_value = instance
        tui.run_tui()
    return instance


def test_a_crash_leaves_a_notice_that_points_at_the_log(tmp_path, monkeypatch, capsys):
    _run_tui_with(tmp_path, monkeypatch, return_code=1)
    err = capsys.readouterr().err
    assert f"ayder exited with an error; traceback in {tmp_path / 'stderr.log'}" in err
    assert "exited with an error" not in (tmp_path / "stderr.log").read_text()


def test_a_clean_exit_prints_no_notice(tmp_path, monkeypatch, capsys):
    _run_tui_with(tmp_path, monkeypatch, return_code=0)
    assert "exited with an error" not in capsys.readouterr().err


def test_run_tui_restores_the_streams_before_it_runs_the_exit_path(tmp_path, monkeypatch):
    import ayder_cli.tui as tui

    seen = {}
    monkeypatch.setattr(tui, "get_log_dir", lambda: tmp_path)
    before = (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__)

    def fake_run(**kwargs):
        seen["during"] = (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__)

    with patch("ayder_cli.tui.AyderApp") as mock_app:
        instance = MagicMock()
        instance.return_code = 0
        instance.run.side_effect = fake_run
        mock_app.return_value = instance
        with patch("ayder_cli.core.session.persist_and_announce") as persist:
            persist.side_effect = lambda *a, **k: seen.update(
                at_exit=(sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__)
            )
            tui.run_tui()

    assert seen["during"] != before  # the app ran with the capture in place
    assert seen["at_exit"] == before  # and the exit path ran after restore
    assert (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__) == before
