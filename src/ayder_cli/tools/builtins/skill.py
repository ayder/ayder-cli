"""The ``skill`` tool: list, load, read and unload skills.

Kept from the old file, unchanged, so the log-argument baseline (keyed by
qualname) does not move: ``_set_status_skill`` and ``_new_agent_generation``
with their logger calls and broad handlers. Their callers pass a display
string instead of one skill name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ayder_cli.core.context import PathOutsideSandboxError, ProjectContext
from ayder_cli.core.context_manager import truncate_tool_result
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.core.skills import (
    SkillInfo,
    SkillScope,
    discover_all,
    list_line,
    render_skill_block,
    resolve_resource,
    unload_notice,
)
from ayder_cli.log import get_logger

logger = get_logger("tool")

__all__ = ["SkillInfo", "discover_skills", "skill", "status_text"]


def discover_skills(project_ctx: ProjectContext) -> list[SkillInfo]:
    """Every discovered skill, unfiltered (the user's ``/skill`` view)."""
    return discover_all(Path(project_ctx.root))


def status_text(names: list[str]) -> str | None:
    """Status-bar text for the active skills, or None when there are none."""
    return ", ".join(names) or None


def _set_status_skill(app: Any, skill_name: str | None) -> None:
    try:
        from ayder_cli.tui.widgets import StatusBar

        app.query_one("#status-bar", StatusBar).set_skill(skill_name)
    except Exception:  # noqa: BLE001 - TUI status-bar update: a widget lookup failure must not fail the skill invocation
        logger.opt(exception=True).debug("Failed to update status bar skill indicator")


def _new_agent_generation(app: Any) -> None:
    agent_registry = getattr(app, "_agent_registry", None)
    if agent_registry is not None:
        try:
            agent_registry.new_generation()
        except Exception:  # noqa: BLE001 - agent registry callback: failing to advance the generation must not fail the skill invocation
            logger.opt(exception=True).warning("Failed to advance agent generation")


def _after_change(app: Any, active_names: list[str]) -> None:
    if app is None:
        return
    _new_agent_generation(app)
    _set_status_skill(app, status_text(active_names))


def _default_scope(project_ctx: ProjectContext, app: Any) -> SkillScope:
    """Scope for a call without an injected one (direct calls and tests)."""
    return SkillScope(
        project_root=Path(project_ctx.root),
        messages=getattr(app, "messages", None),
    )


def _not_found(scope: SkillScope, name: str) -> ToolError:
    enabled = ", ".join(info.name for info in scope.enabled_skills())
    suffix = f" Enabled: {enabled}" if enabled else " No skills are enabled."
    return ToolError(f"Unknown or disabled skill: '{name}'.{suffix}", "validation")


def skill(
    project_ctx: ProjectContext,
    action: str,
    name: str | None = None,
    path: str | None = None,
    app: Any = None,
    skill_scope: SkillScope | None = None,
) -> ToolSuccess | ToolError:
    """List, load, read or unload skills."""
    scope = skill_scope if skill_scope is not None else _default_scope(project_ctx, app)
    name = name.strip() if name else None
    active_names = [load.name for load in scope.active()]

    match action:
        case "list":
            skills = scope.enabled_skills()
            if not skills:
                return ToolSuccess("No skills are enabled for this session.")
            return ToolSuccess("Available skills:\n" + "\n".join(list_line(s) for s in skills))

        case "load":
            if not name:
                return ToolError("Skill name is required for action=load.", "validation")
            if name in active_names:
                return ToolSuccess(f"Skill '{name}' is already active.")
            info = scope.find(name)
            if info is None:
                return _not_found(scope, name)
            block = render_skill_block(info)
            if isinstance(block, ToolError):
                return block
            _after_change(app, active_names + [name])
            return ToolSuccess(block)

        case "read":
            if not name or not path:
                return ToolError("action=read needs both name and path.", "validation")
            info = scope.find(name)
            if info is None and name in active_names:
                # Loaded by the user with /skill, which the filter does not limit.
                info = next((s for s in discover_all(scope.project_root) if s.name == name), None)
            if info is None:
                return _not_found(scope, name)
            try:
                target = resolve_resource(info, path)
            except PathOutsideSandboxError as exc:
                return ToolError(f"Security Error: {exc}", "security")
            except ValueError as exc:
                return ToolError(f"Error: {exc}", "validation")
            except FileNotFoundError:
                return ToolError(f"Skill '{name}' has no file '{path}'.", "validation")
            try:
                content = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                return ToolError(f"Error reading '{path}' of skill '{name}': {exc}", "execution")
            return ToolSuccess(truncate_tool_result(content))

        case "unload":
            if name and name not in active_names:
                return ToolSuccess(f"Skill '{name}' is not active.")
            targets = [name] if name else active_names
            if not targets:
                return ToolSuccess("No active skill to unload.")
            _after_change(app, [n for n in active_names if n not in targets])
            return ToolSuccess(unload_notice(targets))

        case _:
            return ToolError(
                "Unknown skill action. Expected one of: list, load, read, unload.",
                "validation",
            )
