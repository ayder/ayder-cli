"""Project skill discovery, bundling, and activation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess


@dataclass(frozen=True)
class SkillInfo:
    name: str
    path: Path


@dataclass(frozen=True)
class SkillResource:
    path: Path
    content: str


@dataclass(frozen=True)
class SkillBundle:
    name: str
    skill_path: Path
    skill_content: str
    resources: list[SkillResource]


_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_BACKTICK_PATH_RE = re.compile(r"`([^`\n]+)`")


def skills_dir(project_ctx: ProjectContext) -> Path:
    """Return the project skill directory."""
    return project_ctx.root / ".ayder" / "skills"


def discover_skills(project_ctx: ProjectContext) -> list[SkillInfo]:
    """Return skills that have a non-directory SKILL.md file."""
    root = skills_dir(project_ctx)
    if not root.is_dir():
        return []
    return [
        SkillInfo(name=path.name, path=path / "SKILL.md")
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "SKILL.md").is_file()
    ]


def find_skill(project_ctx: ProjectContext, name: str) -> SkillInfo | None:
    """Find a skill by exact directory name."""
    return next(
        (skill_info for skill_info in discover_skills(project_ctx) if skill_info.name == name),
        None,
    )


def _normalize_ref(raw_ref: str) -> str | None:
    ref = raw_ref.strip()
    if not ref:
        return None
    if ref.startswith("<") and ref.endswith(">"):
        ref = ref[1:-1].strip()
    ref = unquote(ref)
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc or ref.startswith("#"):
        return None
    ref = ref.split("#", 1)[0].strip()
    if not ref:
        return None
    if any(ch.isspace() for ch in ref):
        ref = ref.split(None, 1)[0]
    return ref


def _resolve_resource_path(skill_dir: Path, raw_ref: str) -> Path | None:
    ref = _normalize_ref(raw_ref)
    if ref is None:
        return None
    candidate = Path(ref)
    if candidate.is_absolute():
        return None
    try:
        resolved = (skill_dir / candidate).resolve()
        resolved.relative_to(skill_dir.resolve())
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return resolved


def extract_skill_resource_refs(skill_path: Path, content: str) -> list[Path]:
    """Extract direct local file references from a SKILL.md body."""
    skill_dir = skill_path.parent
    refs: list[Path] = []
    seen: set[Path] = set()

    raw_refs = [match.group(1) for match in _MARKDOWN_LINK_RE.finditer(content)]
    raw_refs.extend(match.group(1) for match in _BACKTICK_PATH_RE.finditer(content))

    for raw_ref in raw_refs:
        resolved = _resolve_resource_path(skill_dir, raw_ref)
        if resolved is None or resolved in seen:
            continue
        seen.add(resolved)
        refs.append(resolved)
    return refs


def load_skill_bundle(project_ctx: ProjectContext, name: str) -> SkillBundle | ToolError:
    """Load SKILL.md and its directly referenced local files."""
    skill_info = find_skill(project_ctx, name)
    if skill_info is None:
        available = ", ".join(info.name for info in discover_skills(project_ctx))
        suffix = f" Available: {available}" if available else " No skills found."
        return ToolError(f"Unknown skill: '{name}'.{suffix}", "validation")

    try:
        skill_content = skill_info.path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return ToolError(f"Error reading SKILL.md for '{name}': {exc}", "execution")
    if not skill_content:
        return ToolError(f"SKILL.md for '{name}' is empty, skipping.", "validation")

    resources: list[SkillResource] = []
    for resource_path in extract_skill_resource_refs(skill_info.path, skill_content):
        try:
            content = resource_path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        resources.append(SkillResource(path=resource_path, content=content))

    return SkillBundle(
        name=name,
        skill_path=skill_info.path,
        skill_content=skill_content,
        resources=resources,
    )


def format_skill_bundle(bundle: SkillBundle) -> str:
    """Format a loaded skill bundle for system-message injection."""
    parts = [bundle.skill_content]
    skill_dir = bundle.skill_path.parent
    for resource in bundle.resources:
        rel_path = resource.path.relative_to(skill_dir).as_posix()
        parts.append(f"### Referenced File: {rel_path}\n\n{resource.content}")
    return "\n\n".join(parts)


def _set_status_skill(app: Any, skill_name: str | None) -> None:
    try:
        from ayder_cli.tui.widgets import StatusBar

        app.query_one("#status-bar", StatusBar).set_skill(skill_name)
    except Exception:
        pass


def _new_agent_generation(app: Any) -> None:
    agent_registry = getattr(app, "_agent_registry", None)
    if agent_registry is not None:
        try:
            agent_registry.new_generation()
        except Exception:
            pass


def skill(
    project_ctx: ProjectContext,
    action: str,
    name: str | None = None,
    app: Any = None,
) -> ToolSuccess | ToolError:
    """List, load, or unload project skills."""
    match action:
        case "list":
            skills = discover_skills(project_ctx)
            if not skills:
                return ToolSuccess("No skills found in .ayder/skills/")
            return ToolSuccess(
                "Available skills:\n"
                + "\n".join(f"- {skill_info.name}" for skill_info in skills)
            )
        case "load":
            if not name or not name.strip():
                return ToolError("Skill name is required for action=load.", "validation")
            if app is None:
                return ToolError(
                    "Skill loading requires an active TUI app session.",
                    "unsupported",
                )
            bundle = load_skill_bundle(project_ctx, name.strip())
            if isinstance(bundle, ToolError):
                return bundle

            formatted = format_skill_bundle(bundle)
            app.inject_skill(bundle.name, formatted)
            _new_agent_generation(app)
            _set_status_skill(app, bundle.name)
            if bundle.resources:
                files = ", ".join(
                    resource.path.relative_to(bundle.skill_path.parent).as_posix()
                    for resource in bundle.resources
                )
                return ToolSuccess(
                    f"Activated skill: {bundle.name}\nLoaded referenced files: {files}"
                )
            return ToolSuccess(f"Activated skill: {bundle.name}")
        case "unload":
            if app is None:
                return ToolError(
                    "Skill unloading requires an active TUI app session.",
                    "unsupported",
                )
            previous = app.unload_skill()
            _new_agent_generation(app)
            _set_status_skill(app, None)
            if previous:
                return ToolSuccess(f"Unloaded skill: {previous}")
            return ToolSuccess("No active skill to unload.")
        case _:
            return ToolError(
                "Unknown skill action. Expected one of: list, load, unload.",
                "validation",
            )
