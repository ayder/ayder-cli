"""Temporal workflow tool implementation."""

from __future__ import annotations

from ayder_cli.services.temporal_workflow_service import TemporalWorkflowService


def temporal_workflow(
    action: str,
    workflow_id: str | None = None,
    queue_name: str | None = None,
    signal_name: str | None = None,
    payload: dict | None = None,
) -> str:
    """Handle Temporal workflow actions via service layer."""
    service = TemporalWorkflowService()
    return service.execute(
        action=action,
        workflow_id=workflow_id,
        queue_name=queue_name,
        signal_name=signal_name,
        payload=payload,
    )
