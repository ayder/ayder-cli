"""
Cross-session memory storage for ayder-cli.

Stores memories as JSON Lines (.jsonl) in .ayder/memory/memories.jsonl.
Imports from core/result.py (NOT from tools/) to avoid circular imports.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


def _get_memory_dir(project_ctx: ProjectContext) -> Path:
    """Return the memory directory path for the current project context."""
    return project_ctx.root / ".ayder" / "memory"


def _get_memory_file(project_ctx: ProjectContext) -> Path:
    """Return the memories JSONL file path."""
    return _get_memory_dir(project_ctx) / "memories.jsonl"


def save_memory(project_ctx: ProjectContext, content: str, category: str = None, tags: str = None) -> str:
    """Save a piece of context to persistent cross-session memory.

    Args:
        project_ctx: Project context for path resolution.
        content: The content to remember.
        category: Optional category for organization.
        tags: Optional comma-separated tags string.

    Returns:
        ToolSuccess or ToolError.
    """
    try:
        memory_dir = _get_memory_dir(project_ctx)
        memory_dir.mkdir(parents=True, exist_ok=True)

        memory_file = _get_memory_file(project_ctx)

        # Parse tags
        tag_list = []
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        entry = {
            "id": str(uuid.uuid4()),
            "content": content,
            "category": category,
            "tags": tag_list,
            "timestamp": datetime.now().isoformat(),
        }

        with open(memory_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

        return ToolSuccess(f"Memory saved (id: {entry['id'][:8]}...)")

    except Exception as e:
        return ToolError(f"Error saving memory: {str(e)}", "execution")


def load_memory(project_ctx: ProjectContext, category: str = None, query: str = None, limit: int = 10) -> str:
    """Load saved memories from persistent cross-session storage.

    Args:
        project_ctx: Project context for path resolution.
        category: Optional category filter.
        query: Optional search query to filter by content.
        limit: Maximum number of memories to return (default: 10).

    Returns:
        ToolSuccess with JSON array of memories, or ToolError.
    """
    try:
        memory_file = _get_memory_file(project_ctx)

        if not memory_file.exists():
            return ToolSuccess("[]")

        memories = []
        with open(memory_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Apply filters
                if category and entry.get("category") != category:
                    continue
                if query and query.lower() not in entry.get("content", "").lower():
                    continue

                memories.append(entry)

        # Return most recent first, limited
        memories.reverse()
        memories = memories[:limit]

        return ToolSuccess(json.dumps(memories, indent=2))

    except Exception as e:
        return ToolError(f"Error loading memories: {str(e)}", "execution")
