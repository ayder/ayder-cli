"""AGENTS.md names only registered tools and existing files (audit P3-1).

Agents working on this repo read AGENTS.md first; a stale tool table or tree
sends them after tools and modules that do not exist.
"""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

import pytest

from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION
from ayder_cli.tools.definition import TOOL_DEFINITIONS

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
BRANCH = re.compile(r"^(?P<indent>(?:[│ ]   )*)[├└]── (?P<name>\S+)")
# Gitignored on purpose, and documented anyway: they exist only at runtime.
GITIGNORED_ENTRIES = {".ayder"}


@cache
def _tracked() -> frozenset[str]:
    """Every path git tracks, with all its parent directories.

    Checked against git, not the disk: a clean checkout has no runtime
    directories, and a case-insensitive disk would hide a wrong-case name.
    """
    if not (ROOT / ".git").exists():
        pytest.skip("needs a git checkout")
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    paths: set[str] = set()
    for name in filter(None, out.split("\0")):
        path = Path(name)
        paths.add(path.as_posix())
        paths.update(p.as_posix() for p in path.parents if p != Path("."))
    return frozenset(paths)


def _documented(rel: str) -> bool:
    return rel in _tracked() or rel in GITIGNORED_ENTRIES


def _section(heading: str) -> str:
    start = DOC.index(heading)
    end = DOC.find("\n## ", start + len(heading))
    return DOC[start:end if end != -1 else None]


def _table_rows(text: str) -> list[list[str]]:
    rows = [line for line in text.splitlines() if line.startswith("|")]
    return [[cell.strip() for cell in row.strip("|").split("|")] for row in rows[2:]]


def _builtin_tools() -> dict[str, tuple[str, ...]]:
    tools = {td.name: td.tags for td in TOOL_DEFINITIONS if td.func_ref.startswith("ayder_cli.")}
    tools[AGENT_TOOL_DEFINITION.name] = AGENT_TOOL_DEFINITION.tags
    return tools


def test_tool_table_matches_the_registry():
    """Every listed tool is registered under the listed tag, and every built-in is listed."""
    section = _section("### Pluggable Tool System")
    table = section[section.index("| Category"):]
    listed: dict[str, str] = {}
    for _category, tag, tools in _table_rows(table.split("\n\n")[0]):
        for name in re.findall(r"`([^`]+)`", tools):
            listed[name] = tag.strip("`")
    registered = _builtin_tools()
    assert set(listed) == set(registered), (
        f"documented but not registered: {sorted(set(listed) - set(registered))}; "
        f"registered but not documented: {sorted(set(registered) - set(listed))}"
    )
    wrong_tag = {n: t for n, t in listed.items() if t not in registered[n]}
    assert not wrong_tag, wrong_tag


def test_project_tree_names_existing_paths():
    """Every file and directory in the tree is tracked at the path its indentation gives."""
    block = _section("## Project Structure").split("```")[1]
    stack: list[str] = []
    missing = []
    for line in block.splitlines():
        m = BRANCH.match(line)
        # A branch line the parser cannot read would otherwise escape the check.
        assert m or "──" not in line, f"unparsed tree line: {line!r}"
        if not m:
            continue
        depth = len(m["indent"]) // 4
        assert depth <= len(stack), f"tree line skips a level: {line!r}"
        stack[depth:] = [m["name"].rstrip("/")]
        if "*" in m["name"]:
            continue
        rel = Path(*stack).as_posix()
        if not _documented(rel):
            missing.append(rel)
    assert not missing, missing


def test_key_files_exist():
    """Every path in Key Files Reference is tracked under src/ayder_cli/ or the repo root."""
    rows = _table_rows(_section("### Key Files Reference").split("\n## ")[0])
    missing = []
    for path, _purpose in rows:
        rel = path.strip("`").rstrip("/")
        if not (_documented(f"src/ayder_cli/{rel}") or _documented(rel)):
            missing.append(rel)
    assert not missing, missing
