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
    """Persist an agent's final deliverable to .ayder/notes/. Best-effort.

    Non-overwriting and YAML-safe. Returns the project-relative path, or None
    if writing fails (a note failure must never fail the agent run).
    """
    try:
        notes_dir = _get_notes_dir(project_ctx)
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
