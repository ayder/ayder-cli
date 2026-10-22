"""AGENTS.md names only registered tools and existing files (audit P3-1).

Agents working on this repo read AGENTS.md first; a stale tool table or tree
sends them after tools and modules that do not exist.
"""

from __future__ import annotations

import re
from pathlib import Path

from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION
from ayder_cli.tools.definition import TOOL_DEFINITIONS

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
BRANCH = re.compile(r"^(?P<indent>(?:[│ ]   )*)[├└]── (?P<name>\S+)")


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
    """Every file and directory in the tree exists at the path its indentation gives."""
    block = _section("## Project Structure").split("```")[1]
    stack: list[str] = []
    missing = []
    for line in block.splitlines():
        m = BRANCH.match(line)
        if not m or "*" in m["name"]:
            continue
        depth = len(m["indent"]) // 4
        stack[depth:] = [m["name"].rstrip("/")]
        rel = Path(*stack)
        if not (ROOT / rel).exists():
            missing.append(str(rel))
    assert not missing, missing


def test_key_files_exist():
    """Every path in Key Files Reference exists under src/ayder_cli/ or the repo root."""
    rows = _table_rows(_section("### Key Files Reference").split("\n## ")[0])
    missing = []
    for path, _purpose in rows:
        rel = path.strip("`")
        if not ((ROOT / "src" / "ayder_cli" / rel).exists() or (ROOT / rel).exists()):
            missing.append(rel)
    assert not missing, missing
