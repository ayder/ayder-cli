"""
Note management for ayder-cli.

Creates markdown notes in .ayder/notes/ for investigation findings and documentation.
Imports from core/result.py (NOT from tools/) to avoid circular imports.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

logger = logging.getLogger(__name__)


def _get_notes_dir(project_ctx: ProjectContext) -> Path:
    """Return the notes directory path for the current project context."""
    return project_ctx.root / ".ayder" / "notes"


def _title_to_slug(title: str) -> str:
    """Convert title to kebab-case slug for filenames."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > 50:
        truncated = slug[:50].rsplit("-", 1)[0]
        slug = truncated if truncated else slug[:50]
    return slug or "untitled"


def _yaml_scalar(value: object) -> str:
    """Render a value as a safely double-quoted YAML scalar.

    json.dumps escapes quotes, backslashes, newlines, tabs, and control
    characters, and a JSON string is a valid YAML 1.2 flow scalar.
    """
    return json.dumps(str(value), ensure_ascii=False)


def _write_note(
    notes_dir: Path, filename: str, frontmatter: list[str], body: str, *, exclusive: bool = False
) -> Path:
    """Write YAML frontmatter + body. When exclusive, never overwrite —
    append a numeric suffix on collision. Returns the written path.
    """
    notes_dir.mkdir(parents=True, exist_ok=True)
    content = "\n".join(["---", *frontmatter, "---"]) + f"\n\n{body}\n"
    if not exclusive:
        path = notes_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
    stem = filename[:-3] if filename.endswith(".md") else filename
    candidate = notes_dir / f"{stem}.md"
    n = 2
    while True:
        try:
            with open(candidate, "x", encoding="utf-8") as f:  # exclusive create
                f.write(content)
            return candidate
        except FileExistsError:
            candidate = notes_dir / f"{stem}-{n}.md"
            n += 1


def write_agent_note(
    project_ctx: ProjectContext,
    *,
    agent_name: str,
    run_id: int,
    generation: int,
    status: str,
    task: str,
    content: str,
    timestamp: str,
    error: str | None = None,
) -> str | None:
    """Persist an agent's final deliverable to .ayder/notes/runs/. Best-effort.

    Agent run logs live in a ``runs/`` subdirectory so they stay separate from
    caller-named notes: the non-recursive ``note(action="list")`` and the
    ``/notes`` viewer glob only the top-level ``.ayder/notes/`` and never
    intermingle these per-run logs with addressable notes. Non-overwriting and
    YAML-safe. Returns the project-relative path, or None if writing fails
    (a note failure must never fail the agent run).
    """
    try:
        notes_dir = _get_notes_dir(project_ctx) / "runs"
        slug = _title_to_slug(agent_name)
        filename = f"{timestamp}-{slug}-run{run_id}.md"
        frontmatter = [
            f"title: {_yaml_scalar(f'{agent_name} run {run_id}')}",
            f"date: {_yaml_scalar(timestamp)}",
            f"agent: {_yaml_scalar(agent_name)}",
            f"run_id: {run_id}",
            f"generation: {generation}",
            f"status: {_yaml_scalar(status)}",
            "tags: [agent-result]",
        ]
        body = f"## Task\n{task}\n\n## Result\n{content}"
        if error is not None:
            body += f"\n\n## Error\n{error}"
        path = _write_note(notes_dir, filename, frontmatter, body, exclusive=True)
        return project_ctx.to_relative(path)
    except Exception as e:
        logger.warning("write_agent_note failed for agent '%s' run %d: %s", agent_name, run_id, e)
        return None


def create_note(
    project_ctx: ProjectContext, title: str, content: str, tags: str | None = None
) -> str:
    """Create a markdown note in .ayder/notes/.

    Args:
        project_ctx: Project context for path resolution.
        title: The title of the note.
        content: The markdown content of the note.
        tags: Optional comma-separated tags string.

    Returns:
        ToolSuccess or ToolError.
    """
    try:
        notes_dir = _get_notes_dir(project_ctx)
        notes_dir.mkdir(parents=True, exist_ok=True)

        slug = _title_to_slug(title)
        filename = f"{slug}.md"
        path = notes_dir / filename

        # Parse tags
        tag_list = []
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build YAML frontmatter
        frontmatter_lines = [
            "---",
            f'title: "{title}"',
            f"date: {now}",
        ]
        if tag_list:
            frontmatter_lines.append(f"tags: [{', '.join(tag_list)}]")
        frontmatter_lines.append("---")

        note_content = "\n".join(frontmatter_lines) + f"\n\n{content}\n"

        path.write_text(note_content, encoding="utf-8")

        rel_path = project_ctx.to_relative(path)
        return ToolSuccess(f"Note created: {rel_path}")

    except Exception as e:
        return ToolError(f"Error creating note: {str(e)}", "execution")


def _render_note(slug: str, content: str, tags: str | None) -> str:
    """Frontmatter + body, matching the /notes viewer's expectations."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fm = [f"title: {_yaml_scalar(slug)}", f"date: {_yaml_scalar(now)}"]
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if tag_list:
        fm.append(f"tags: [{', '.join(tag_list)}]")
    return "---\n" + "\n".join(fm) + "\n---\n\n" + content.strip("\n") + "\n"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter-block-incl-fences, body). ('', text) if no frontmatter."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[: i + 1]), "\n".join(lines[i + 1 :]).strip("\n")
    return "", text.strip("\n")


def write_note_file(
    project_ctx: ProjectContext,
    note_id: str,
    content: str,
    *,
    tags: str | None = None,
    exclusive: bool = True,
) -> str:
    """Write a caller-named note. Returns the canonical slug id written.

    exclusive=True: O_EXCL, raises FileExistsError on collision (backs LLM create).
    exclusive=False: suffix-resolves (slug, slug-2, …), never raises (backs mint).
    """
    notes_dir = _get_notes_dir(project_ctx)
    notes_dir.mkdir(parents=True, exist_ok=True)
    slug = _title_to_slug(note_id)
    rendered = _render_note(slug, content, tags)
    if exclusive:
        path = notes_dir / f"{slug}.md"
        with open(path, "x", encoding="utf-8") as fh:  # raises FileExistsError
            fh.write(rendered)
        return slug
    candidate, n = notes_dir / f"{slug}.md", 2
    while True:
        try:
            with open(candidate, "x", encoding="utf-8") as fh:
                fh.write(rendered)
            return candidate.stem
        except FileExistsError:
            candidate = notes_dir / f"{slug}-{n}.md"
            n += 1


def read_note_file(project_ctx: ProjectContext, note_id: str) -> str | None:
    """Return the note body (frontmatter stripped), or None if absent."""
    path = _get_notes_dir(project_ctx) / f"{_title_to_slug(note_id)}.md"
    if not path.exists():
        return None
    return _split_frontmatter(path.read_text(encoding="utf-8"))[1]


def update_note_file(
    project_ctx: ProjectContext, note_id: str, content: str, *, mode: str = "append"
) -> bool:
    """Append a dated entry (default) or replace the body. False if absent."""
    path = _get_notes_dir(project_ctx) / f"{_title_to_slug(note_id)}.md"
    if not path.exists():
        return False
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    if mode == "replace":
        new_body = content.strip("\n")
    else:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_body = body.rstrip("\n") + f"\n\n## {now}\n\n" + content.strip("\n")
    prefix = fm + "\n\n" if fm else ""
    path.write_text(prefix + new_body + "\n", encoding="utf-8")
    return True


def list_note_ids(project_ctx: ProjectContext, prefix: str | None = None) -> list[str]:
    """Sorted note slug ids, optionally filtered by normalized prefix."""
    notes_dir = _get_notes_dir(project_ctx)
    if not notes_dir.exists():
        return []
    ids = sorted(p.stem for p in notes_dir.glob("*.md"))
    if prefix:
        norm = _title_to_slug(prefix)
        ids = [i for i in ids if i.startswith(norm)]
    return ids


def delete_note_file(project_ctx: ProjectContext, note_id: str) -> bool:
    """Delete a note. False if absent."""
    path = _get_notes_dir(project_ctx) / f"{_title_to_slug(note_id)}.md"
    if not path.exists():
        return False
    path.unlink()
    return True


def mint_note(
    project_ctx: ProjectContext, base_id: str, content: str, *, tags: str | None = None
) -> str:
    """Harness-facing: write a deliverable note that never collides. Returns its id."""
    return write_note_file(project_ctx, base_id, content, tags=tags, exclusive=False)
