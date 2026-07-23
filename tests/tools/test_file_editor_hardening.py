"""Tests for file_editor hardening: match-failure hints, atomic writes,
and per-file serialization of concurrent edits."""

import os
import threading

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError
from ayder_cli.tools.builtins.filesystem import file_editor


@pytest.fixture
def project_context(tmp_path):
    return ProjectContext(str(tmp_path))


class TestReplaceClosestMatchHint:
    """A failed 'replace' should point at the nearest fuzzy match so the
    model can self-correct in one turn instead of re-reading the file."""

    def test_not_found_includes_closest_match_hint(self, tmp_path, project_context):
        test_file = tmp_path / "code.py"
        test_file.write_text("def foo(self):\n\treturn 1\n")

        # Model guesses spaces where the file has a tab — the classic miss.
        result = file_editor(
            project_context,
            str(test_file),
            "replace",
            old_string="def foo(self):\n    return 1",
            new_string="def foo(self):\n    return 2",
        )

        assert isinstance(result, ToolError)
        assert "not found" in result
        assert "line 1" in result
        # repr() of the region must expose the tab so the mismatch is visible
        assert "\\t" in result

    def test_not_found_hint_names_similarity(self, tmp_path, project_context):
        test_file = tmp_path / "code.py"
        test_file.write_text("alpha\ndef bar(x):\n    return x\nomega\n")

        result = file_editor(
            project_context,
            str(test_file),
            "replace",
            old_string="def bar(x) :\n    return x",
            new_string="def bar(x):\n    return x + 1",
        )

        assert isinstance(result, ToolError)
        assert "line 2" in result

    def test_not_found_without_similar_content_stays_plain(self, tmp_path, project_context):
        test_file = tmp_path / "data.txt"
        test_file.write_text("alpha\nbeta\n")

        result = file_editor(
            project_context,
            str(test_file),
            "replace",
            old_string="zzzz_qqqq_completely_unrelated",
            new_string="whatever",
        )

        assert isinstance(result, ToolError)
        assert "not found" in result
        assert "losest match" not in result  # no misleading hint


class TestAtomicWrite:
    """Mutations must never leave a truncated/partial file behind."""

    def test_failed_write_preserves_original_content(self, tmp_path, project_context, monkeypatch):
        test_file = tmp_path / "important.txt"
        test_file.write_text("original content")

        def boom(*args, **kwargs):
            raise OSError("simulated crash during rename")

        monkeypatch.setattr(os, "replace", boom)

        result = file_editor(
            project_context, str(test_file), "write", content="new content"
        )

        assert isinstance(result, ToolError)
        assert test_file.read_text() == "original content"

    def test_failed_write_leaves_no_temp_files(self, tmp_path, project_context, monkeypatch):
        test_file = tmp_path / "important.txt"
        test_file.write_text("original content")

        def boom(*args, **kwargs):
            raise OSError("simulated crash during rename")

        monkeypatch.setattr(os, "replace", boom)

        file_editor(project_context, str(test_file), "write", content="new content")

        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "important.txt"]
        assert leftovers == []

    def test_overwrite_preserves_file_mode(self, tmp_path, project_context):
        test_file = tmp_path / "script.sh"
        test_file.write_text("#!/bin/sh\necho old\n")
        os.chmod(test_file, 0o755)

        result = file_editor(
            project_context, str(test_file), "write", content="#!/bin/sh\necho new\n"
        )

        assert isinstance(result, ToolSuccess)
        assert os.stat(test_file).st_mode & 0o777 == 0o755


class TestConcurrentSameFileEdits:
    """Parallel tool execution must not lose edits to the same file.

    The chat loop runs auto-approved tool calls concurrently via
    asyncio.to_thread; two replaces on one file must serialize."""

    def test_parallel_replaces_on_same_file_all_land(self, tmp_path, project_context):
        n = 8
        test_file = tmp_path / "shared.txt"
        test_file.write_text("".join(f"token{i}\n" for i in range(n)))

        barrier = threading.Barrier(n)
        errors = []

        def worker(i):
            barrier.wait()
            result = file_editor(
                project_context,
                str(test_file),
                "replace",
                old_string=f"token{i}",
                new_string=f"done{i}",
            )
            if not isinstance(result, ToolSuccess):
                errors.append(str(result))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        final = test_file.read_text()
        missing = [i for i in range(n) if f"done{i}" not in final]
        assert missing == [], f"lost edits from threads {missing}:\n{final}"
