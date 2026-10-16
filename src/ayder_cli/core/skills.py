"""Skill discovery, frontmatter, scope, delivery blocks and the active set.

A skill is a directory holding SKILL.md. Three layers are searched, a later
one overriding an earlier one by name: builtin (the packaged skills; MR C
reads them from the synced copy in ~/.ayder/builtin), user (~/.ayder/skills)
and project (<project>/.ayder/skills).

Skills reach the model as appended content, never as a system message: the
``skill`` tool returns the block below as its result, and ``/skill`` appends
it as a user message. Nothing earlier in the history changes, so the message
prefix (and the provider's KV cache) survives a load. The active set is
derived from those blocks in the history, so nothing else stores it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ayder_cli.core.config import CONFIG_DIR
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError
from ayder_cli.log import get_logger

logger = get_logger("core")

# Layer roots. Module globals so tests can point them at temporary
# directories (tests/conftest.py does this for every test).
PACKAGED_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
USER_SKILLS_DIR = CONFIG_DIR / "skills"

SKILL_FILE = "SKILL.md"
MAX_SKILL_BYTES = 64 * 1024
LINK_PROBLEM = "it links outside its skills directory"

LOADED_MARKER = "### SKILL LOADED: "
END_MARKER = "### END SKILL: "
UNLOADED_MARKER = "### SKILL UNLOADED: "
RESUPPLY_HEADER = "### SKILLS LOADED EARLIER (context only; do not load again)"

_UNLOADED_RE = re.compile(r"^### SKILL UNLOADED: (\S+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class SkillInfo:
    """One discovered skill. ``name`` is its directory name."""

    name: str
    path: Path  # the SKILL.md file
    description: str = ""
    layer: str = "project"
    problem: str = ""  # why it cannot load ("empty", ...); "" when loadable


@dataclass(frozen=True)
class SkillLoad:
    """An active skill: its name, the history index of its block, the block."""

    name: str
    index: int
    block: str


# -- Frontmatter ---------------------------------------------------------------


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split optional leading ``---`` frontmatter from a SKILL.md text.

    Only ``key: value`` lines are understood (PyYAML is not a dependency).
    Blank lines and ``#`` comments are skipped; one surrounding pair of
    quotes is removed from a value. A block that is unterminated or holds a
    line without a colon is malformed: the result is no fields and the text
    unchanged, so the body is delivered whole.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text
    fields: dict[str, str] = {}
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition(":")
        if not sep or not key.strip():
            return {}, text
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    body = "\n".join(lines[end + 1 :]).strip("\n")
    return fields, body


def _first_body_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _read_text(path: Path) -> tuple[str, str]:
    """Return (text, problem). ``problem`` is "" when the file is loadable."""
    try:
        if path.stat().st_size > MAX_SKILL_BYTES:
            return "", "over 64 KB"
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "", "not UTF-8"
    except OSError:
        return "", "unreadable"
    if not text.strip():
        return "", "empty"
    return text, ""


def read_skill_info(skill_dir: Path, layer: str) -> SkillInfo:
    """Describe the skill in ``skill_dir`` (which must hold SKILL.md)."""
    path = skill_dir / SKILL_FILE
    text, problem = _read_text(path)
    fields, body = parse_frontmatter(text)
    declared = fields.get("name")
    if declared and declared != skill_dir.name:
        logger.debug(
            "Skill directory {!r} declares name {!r}; the directory name is used",
            skill_dir.name,
            declared,
        )
    description = fields.get("description") or _first_body_line(body)
    return SkillInfo(
        name=skill_dir.name,
        path=path,
        description=description,
        layer=layer,
        problem=problem,
    )


# -- Discovery -------------------------------------------------------------------


def builtin_skills_root() -> Path:
    """Directory the builtin layer is read from. MR C replaces this body."""
    return PACKAGED_SKILLS_DIR


def layer_roots(project_root: Path) -> list[tuple[str, Path]]:
    """The layers in lookup order; a later layer overrides an earlier one."""
    return [
        ("builtin", builtin_skills_root()),
        ("user", USER_SKILLS_DIR),
        ("project", Path(project_root) / ".ayder" / "skills"),
    ]


def _links_outside(skill_dir: Path, root: Path) -> bool:
    """True when the skill directory, or its SKILL.md, resolves outside.

    The boundary is the layer directory, not the skill directory: a symlinked
    skill directory would otherwise become its own trusted boundary.
    """
    real_root = os.path.realpath(root)
    real_dir = os.path.realpath(skill_dir)
    real_file = os.path.realpath(skill_dir / SKILL_FILE)
    return (
        os.path.commonpath([real_root, real_dir]) != real_root
        or os.path.commonpath([real_dir, real_file]) != real_dir
    )


def discover_all(project_root: Path) -> list[SkillInfo]:
    """Every skill in every layer, overrides applied, sorted by name.

    A skill that links outside its layer directory is listed with a problem
    and is never read.
    """
    merged: dict[str, SkillInfo] = {}
    for layer, root in layer_roots(project_root):
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir()):
            if not (skill_dir.is_dir() and (skill_dir / SKILL_FILE).is_file()):
                continue
            if _links_outside(skill_dir, root):
                merged[skill_dir.name] = SkillInfo(
                    name=skill_dir.name,
                    path=skill_dir / SKILL_FILE,
                    layer=layer,
                    problem=LINK_PROBLEM,
                )
            else:
                merged[skill_dir.name] = read_skill_info(skill_dir, layer)
    return [merged[name] for name in sorted(merged)]


def find_skill(project_root: Path, name: str) -> SkillInfo | None:
    return next((info for info in discover_all(project_root) if info.name == name), None)


def list_line(info: SkillInfo) -> str:
    """One ``skill(list)`` line: name, layer, description, any load problem."""
    line = f"- {info.name} ({info.layer})"
    if info.description:
        line += f": {info.description}"
    if info.problem:
        line += f" [cannot load: {info.problem}]"
    return line


# -- Scope -------------------------------------------------------------------------


@dataclass
class SkillScope:
    """What one session or agent may use, and the history it reads.

    ``enabled`` None means every discovered skill (MR A). MR C resolves the
    ``skills`` setting to a concrete set. ``messages`` is bound by ChatLoop
    to the list it sends, so the active set always reflects that history.
    """

    project_root: Path
    enabled: frozenset[str] | None = None
    messages: list[dict[str, Any]] | None = None

    def enabled_skills(self) -> list[SkillInfo]:
        return [
            info
            for info in discover_all(self.project_root)
            if self.enabled is None or info.name in self.enabled
        ]

    def find(self, name: str) -> SkillInfo | None:
        """An enabled skill by name."""
        return next((info for info in self.enabled_skills() if info.name == name), None)

    def active(self) -> list[SkillLoad]:
        return active_skills(self.messages or [])


# -- Delivery blocks -------------------------------------------------------------


def skill_resources(info: SkillInfo) -> list[str]:
    """Relative paths of the skill's other files, sorted."""
    skill_dir = info.path.parent
    return sorted(
        path.relative_to(skill_dir).as_posix()
        for path in skill_dir.rglob("*")
        if path.is_file() and path != info.path and "__pycache__" not in path.parts
    )


def render_skill_block(info: SkillInfo) -> str | ToolError:
    """The text a load appends: header, source, file list, body, end marker."""
    if info.problem:
        return ToolError(
            f"SKILL.md for '{info.name}' cannot be loaded: {info.problem}.", "validation"
        )
    text, problem = _read_text(info.path)
    if problem:
        return ToolError(
            f"SKILL.md for '{info.name}' cannot be loaded: {problem}.", "validation"
        )
    _, body = parse_frontmatter(text)
    lines = [
        f"{LOADED_MARKER}{info.name}",
        f"Source: {info.layer} ({info.path.parent})",
    ]
    resources = skill_resources(info)
    if resources:
        lines.append(
            "Files: "
            + ", ".join(resources)
            + f' (read with skill(action="read", name="{info.name}", path=...))'
        )
    return "\n".join(lines) + "\n\n" + body.strip() + f"\n\n{END_MARKER}{info.name}"


def unload_notice(names: list[str]) -> str:
    markers = "\n".join(f"{UNLOADED_MARKER}{name}" for name in names)
    return markers + "\nStop following the instructions of the skill(s) named above."


def resolve_resource(info: SkillInfo, rel_path: str) -> Path:
    """Path of a resource file inside the skill directory.

    Raises:
        ValueError: the path is absolute, names SKILL.md, or resolves outside
            the skill directory (including through a symlink).
        FileNotFoundError: no such file.
    """
    if info.problem == LINK_PROBLEM:
        raise ValueError(f"Security Alert: skill '{info.name}' {LINK_PROBLEM}")
    skill_dir = info.path.parent
    candidate = Path(rel_path)
    if candidate.is_absolute():
        raise ValueError(f"Security Alert: '{rel_path}' is absolute")
    target = skill_dir / candidate
    ProjectContext.within(skill_dir, target)
    if os.path.realpath(target) == os.path.realpath(info.path):
        raise ValueError(f'SKILL.md is not a resource; use skill(action="load", name="{info.name}")')
    if not target.is_file():
        raise FileNotFoundError(rel_path)
    return target


# -- Active set ------------------------------------------------------------------


def _block_name(content: str, marker: str) -> str:
    return content[len(marker) :].split("\n", 1)[0].strip()


def active_skills(messages: list[dict[str, Any]]) -> list[SkillLoad]:
    """Skills loaded and not unloaded, in load order.

    A load is a tool or user message whose content starts with
    LOADED_MARKER; an unload is one that starts with UNLOADED_MARKER (it may
    name several skills, one marker line each). A later load of the same
    name, after an unload, counts from its own index.
    """
    active: dict[str, SkillLoad] = {}
    for index, message in enumerate(messages):
        if message.get("role") not in ("tool", "user"):
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        if content.startswith(LOADED_MARKER):
            name = _block_name(content, LOADED_MARKER)
            end_marker = f"{END_MARKER}{name}"
            end = content.find(end_marker)
            block = content if end < 0 else content[: end + len(end_marker)]
            active.pop(name, None)
            active[name] = SkillLoad(name=name, index=index, block=block)
        elif content.startswith(UNLOADED_MARKER):
            for name in _UNLOADED_RE.findall(content):
                active.pop(name, None)
    return sorted(active.values(), key=lambda load: load.index)
