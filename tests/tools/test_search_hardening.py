"""Tests for search_codebase hardening.

Covers, against the real rg and grep binaries (no subprocess mocking):
- single-file targets via the `directory` parameter
- patterns that start with '-' (e.g. '-> str')
- context_lines output integrity (the heading-parser rewrite), across the
  full engine x target x context x format matrix
- honest truncation reporting when max_results is hit
- the 'locations' output format (file:line pairs, no content)
- glob semantics (basename vs path-anchored) and the grep-fallback
  basename approximation note
- zero-count filtering in 'count' output on the grep fallback
- schema descriptions that teach the above
"""

import re
import shutil

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError
from ayder_cli.tools.builtins.search import search_codebase
from ayder_cli.tools.builtins.search_definitions import TOOL_DEFINITIONS

CORE_PY = (
    '"""doc."""\n'
    "\n"
    "\n"
    "def alpha() -> str:\n"
    '    value = "alpha"\n'
    "    return value\n"
    "\n"
    "\n"
    "def beta() -> str:\n"
    '    other = "beta"\n'
    "    return other\n"
)  # "^def " matches at lines 4 and 9; "-> str" at 4 and 9

UTIL_PY = (
    "def gamma():\n"
    '    return "g"\n'
    "\n"
    "\n"
    "def delta():\n"
    '    return "d"\n'
)  # "^def " matches at lines 1 and 5


@pytest.fixture
def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "core.py").write_text(CORE_PY)
    (tmp_path / "src" / "util.py").write_text(UTIL_PY)
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "core.py").write_text('def epsilon():\n    return "e"\n')
    (tmp_path / "bulk").mkdir()
    (tmp_path / "bulk" / "many.py").write_text(
        "".join(f"def f{i}(): pass\n" for i in range(8))
    )
    (tmp_path / "bulk2").mkdir()
    (tmp_path / "bulk2" / "a.py").write_text(
        "".join(f"def a{i}(): pass\n" for i in range(4))
    )
    (tmp_path / "bulk2" / "b.py").write_text(
        "".join(f"def b{i}(): pass\n" for i in range(4))
    )
    return ProjectContext(str(tmp_path))


@pytest.fixture(params=["rg", "grep"])
def engine(request, monkeypatch):
    """Run each test against ripgrep and against the grep fallback."""
    if request.param == "rg":
        if not shutil.which("rg"):
            pytest.skip("ripgrep not installed")
    else:
        monkeypatch.setattr(
            "ayder_cli.tools.builtins.search.shutil.which", lambda name: None
        )
    return request.param


def _match_lines(result):
    """Lines the formatter presents as matches (not context, not headers)."""
    return [ln for ln in str(result).splitlines() if re.match(r"^Line \d+: ", ln)]


def _file_headers(result):
    return [
        ln[len("FILE: ") :]
        for ln in str(result).splitlines()
        if ln.startswith("FILE: ")
    ]


class TestSingleFileTarget:
    """`directory` must accept a single file as the search scope."""

    def test_full_format(self, project, engine):
        result = search_codebase(project, "^def ", directory="src/core.py")
        assert isinstance(result, ToolSuccess)
        assert "Matches found: 2" in result
        assert "def alpha" in result
        assert "def beta" in result
        assert _file_headers(result) == ["src/core.py"]

    def test_files_only_format(self, project, engine):
        result = search_codebase(
            project, "^def ", directory="src/core.py", output_format="files_only"
        )
        assert isinstance(result, ToolSuccess)
        assert "src/core.py" in result
        assert "Files with matches: 1" in result

    def test_count_format(self, project, engine):
        result = search_codebase(
            project, "^def ", directory="src/core.py", output_format="count"
        )
        assert isinstance(result, ToolSuccess)
        assert "src/core.py: 2" in result
        assert "Total matches: 2" in result

    def test_locations_format(self, project, engine):
        result = search_codebase(
            project, "^def ", directory="src/core.py", output_format="locations"
        )
        assert isinstance(result, ToolSuccess)
        assert "src/core.py: 4, 9" in result

    def test_no_matches_in_file(self, project, engine):
        result = search_codebase(project, "zzz_nothing", directory="src/core.py")
        assert isinstance(result, ToolSuccess)
        assert "No matches found" in result

    def test_nonexistent_path_names_the_problem(self, project):
        result = search_codebase(project, "def", directory="nope/missing.py")
        assert isinstance(result, ToolError)
        assert "does not exist" in result


class TestLeadingDashPattern:
    """Patterns starting with '-' must not be parsed as flags."""

    @pytest.mark.parametrize("target", ["src", "src/core.py"])
    def test_arrow_annotation_pattern(self, project, engine, target):
        result = search_codebase(project, "-> str", directory=target)
        assert isinstance(result, ToolSuccess)
        assert "Matches found: 2" in result
        assert "def alpha() -> str:" in result


class TestContextMatrix:
    """context_lines > 0 must yield well-formed output: real file headers,
    correct match counts, context shown but never misparsed as headers
    or matches. Full engine x target x context matrix."""

    @pytest.mark.parametrize("context", [0, 1, 2])
    @pytest.mark.parametrize(
        "target,expected_matches,expected_files",
        [
            ("src", 4, {"src/core.py", "src/util.py"}),
            ("src/core.py", 2, {"src/core.py"}),
        ],
    )
    def test_full_output_well_formed(
        self, project, engine, target, expected_matches, expected_files, context
    ):
        result = search_codebase(
            project, "^def ", directory=target, context_lines=context
        )
        assert isinstance(result, ToolSuccess)
        # Every FILE header names a real file — no '3-', '--', or content garbage.
        headers = _file_headers(result)
        assert set(headers) == expected_files
        for header in headers:
            assert (project.root / header).is_file(), f"bogus header {header!r}"
        # Only true matches are counted.
        assert f"Matches found: {expected_matches}" in result
        assert len(_match_lines(result)) == expected_matches

    @pytest.mark.parametrize("target", ["src", "src/core.py"])
    def test_context_content_is_shown(self, project, engine, target):
        result = search_codebase(
            project, "^def ", directory=target, context_lines=1
        )
        assert isinstance(result, ToolSuccess)
        # Line 5 of core.py is context around the line-4 match.
        assert 'value = "alpha"' in result

    def test_group_separator_not_a_header(self, project, engine):
        # context_lines=1 on core.py leaves a gap between the two groups,
        # so the engine emits a '--' separator line.
        result = search_codebase(
            project, "^def ", directory="src/core.py", context_lines=1
        )
        assert isinstance(result, ToolSuccess)
        assert "FILE: --" not in result

    def test_blank_context_lines_not_headers(self, project, engine):
        # context_lines=2 pulls in blank lines 2, 3, 7, 8 of core.py, which
        # the old parser rendered as 'FILE: 3-' garbage headers.
        result = search_codebase(
            project, "^def ", directory="src/core.py", context_lines=2
        )
        assert isinstance(result, ToolSuccess)
        for header in _file_headers(result):
            assert not re.match(r"^\d", header)

    @pytest.mark.parametrize("context", [0, 2])
    def test_multi_file_blocks_keep_their_headers(self, project, engine, context):
        result = search_codebase(
            project, "^def ", directory="src", context_lines=context
        )
        text = str(result)
        # Matches must be attributed to the right file: def gamma lives in
        # util.py, so it must appear after the util.py header, not core.py's.
        core_pos = text.find("FILE: src/core.py")
        util_pos = text.find("FILE: src/util.py")
        gamma_pos = text.find("def gamma")
        alpha_pos = text.find("def alpha")
        assert -1 not in (core_pos, util_pos, gamma_pos, alpha_pos)
        assert (util_pos < gamma_pos) and not (util_pos < alpha_pos < core_pos)


class TestTruncation:
    """Hitting max_results must be reported, never silent."""

    def test_notice_when_single_file_exceeds_limit(self, project, engine):
        result = search_codebase(
            project, "^def ", directory="bulk", max_results=5
        )
        assert isinstance(result, ToolSuccess)
        assert len(_match_lines(result)) == 5
        assert "truncated" in str(result).lower()
        assert "output_format='count'" in result

    def test_notice_when_total_across_files_exceeds_limit(self, project, engine):
        result = search_codebase(
            project, "^def ", directory="bulk2", max_results=5
        )
        assert isinstance(result, ToolSuccess)
        assert len(_match_lines(result)) == 5
        assert "truncated" in str(result).lower()

    def test_no_notice_under_limit(self, project, engine):
        result = search_codebase(project, "^def ", directory="src", max_results=50)
        assert isinstance(result, ToolSuccess)
        assert "truncated" not in str(result).lower()

    def test_locations_format_also_reports_truncation(self, project, engine):
        result = search_codebase(
            project,
            "^def ",
            directory="bulk",
            max_results=5,
            output_format="locations",
        )
        assert isinstance(result, ToolSuccess)
        assert "truncated" in str(result).lower()


class TestLocationsFormat:
    """'locations' answers where-exactly in one call: file:line pairs, no content."""

    def test_lists_files_with_line_numbers(self, project, engine):
        result = search_codebase(
            project, "^def ", directory="src", output_format="locations"
        )
        assert isinstance(result, ToolSuccess)
        assert "src/core.py: 4, 9" in result
        assert "src/util.py: 1, 5" in result

    def test_omits_match_content(self, project, engine):
        result = search_codebase(
            project, "^def ", directory="src", output_format="locations"
        )
        assert 'value = "alpha"' not in result
        assert "def alpha" not in result

    def test_no_matches(self, project, engine):
        result = search_codebase(
            project, "zzz_nothing", directory="src", output_format="locations"
        )
        assert isinstance(result, ToolSuccess)
        assert "No matches found" in result


class TestGlobSemantics:
    def test_basename_glob_matches_any_directory(self, project):
        if not shutil.which("rg"):
            pytest.skip("ripgrep not installed")
        result = search_codebase(project, "^def ", file_pattern="core.py")
        headers = _file_headers(result)
        assert set(headers) == {"src/core.py", "lib/core.py"}

    def test_path_anchored_glob_matches_one_path(self, project):
        if not shutil.which("rg"):
            pytest.skip("ripgrep not installed")
        result = search_codebase(project, "^def ", file_pattern="src/core.py")
        assert _file_headers(result) == ["src/core.py"]

    def test_grep_include_precedes_excludes(self, project, monkeypatch):
        """GNU grep >= 3.6 resolves --include/--exclude by position: a file
        matching no glob is searched unless the FIRST such option is
        --include. Emitting excludes first silently disables the include
        filter on Linux (BSD grep is order-insensitive, so macOS hides it)."""
        monkeypatch.setattr(
            "ayder_cli.tools.builtins.search.shutil.which", lambda name: None
        )
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd

            class R:
                returncode = 1
                stdout = ""
                stderr = ""

            return R()

        monkeypatch.setattr(
            "ayder_cli.tools.builtins.search.subprocess.run", fake_run
        )
        search_codebase(project, "^def ", file_pattern="core.py")
        cmd = captured["cmd"]
        include_at = cmd.index("--include")
        exclude_ats = [
            i for i, arg in enumerate(cmd) if str(arg).startswith("--exclude")
        ]
        assert exclude_ats, "expected --exclude options in grep command"
        assert include_at < min(exclude_ats)

    def test_grep_fallback_announces_basename_approximation(
        self, project, monkeypatch
    ):
        monkeypatch.setattr(
            "ayder_cli.tools.builtins.search.shutil.which", lambda name: None
        )
        result = search_codebase(project, "^def ", file_pattern="src/core.py")
        assert isinstance(result, ToolSuccess)
        assert "approximate" in str(result).lower()
        assert "core.py" in result
        # The approximation widens the scope — both core.py files match.
        assert set(_file_headers(result)) == {"src/core.py", "lib/core.py"}


class TestCountZeroFiltering:
    def test_grep_fallback_count_omits_zero_count_files(self, project, monkeypatch):
        monkeypatch.setattr(
            "ayder_cli.tools.builtins.search.shutil.which", lambda name: None
        )
        result = search_codebase(
            project, "alpha", directory="src", output_format="count"
        )
        assert isinstance(result, ToolSuccess)
        assert "src/core.py: 2" in result
        assert "util.py" not in result


class TestSchemaTeachesUsage:
    """The tool definition must teach glob semantics and file targets."""

    def _definition(self):
        return next(d for d in TOOL_DEFINITIONS if d.name == "search_codebase")

    def test_output_format_offers_locations(self):
        props = self._definition().parameters["properties"]
        assert "locations" in props["output_format"]["enum"]

    def test_file_pattern_teaches_glob_semantics(self):
        desc = self._definition().parameters["properties"]["file_pattern"][
            "description"
        ]
        assert "src/core.py" in desc  # path-anchored example
        assert "*.py" in desc  # extension example

    def test_directory_mentions_file_targets(self):
        desc = self._definition().parameters["properties"]["directory"]["description"]
        assert "file" in desc.lower()
