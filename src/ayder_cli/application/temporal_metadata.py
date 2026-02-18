"""Temporal metadata persistence helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess


def _sanitize_workflow_id(workflow_id: str) -> str:
    """Return filesystem-safe workflow id."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", workflow_id).strip("-")
    return cleaned or "workflow"


def persist_temporal_run_metadata(
    project_ctx: ProjectContext,
    metadata_dir: str,
    workflow_id: str,
    payload: dict[str, Any],
):
    """Persist run metadata as JSON and return relative file path."""
    if not workflow_id.strip():
        return ToolError("Error: workflow_id must be non-empty", "validation")

    try:
        base_dir = project_ctx.validate_path(metadata_dir)
        runs_dir = base_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        safe_id = _sanitize_workflow_id(workflow_id)
        out_path = runs_dir / f"{safe_id}.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return ToolSuccess(project_ctx.to_relative(out_path))
    except ValueError as e:
        return ToolError(f"Security Error: {e}", "security")
    except Exception as e:
        return ToolError(f"Error writing temporal metadata: {e}", "execution")
