"""
Note management for ayder-cli.

Creates markdown notes in .ayder/notes/ for investigation findings and documentation.
Imports from core/result.py (NOT from tools/) to avoid circular imports.
"""

import re
from datetime import datetime
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


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


def create_note(project_ctx: ProjectContext, title: str, content: str, tags: str = None) -> str:
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
            f"title: \"{title}\"",
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
