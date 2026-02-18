"""Temporal workflow action service."""

from __future__ import annotations

import json

from pydantic import ValidationError

from ayder_cli.application.temporal_contract import validate_temporal_activity_contract
from ayder_cli.core.config import Config, load_config
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.services.temporal_client import TemporalClientAdapter, TemporalClientUnavailableError

_SUPPORTED_ACTIONS = {
    "start_workflow",
    "query_workflow",
    "signal_workflow",
    "escalate",
    "cancel_workflow",
    "report_phase_result",
}


class TemporalWorkflowService:
    """Service-level action dispatcher for temporal workflow operations."""

    def __init__(
        self,
        config: Config | None = None,
        client_adapter: TemporalClientAdapter | None = None,
    ) -> None:
        self._config = config or load_config()
        self._client_adapter = client_adapter or TemporalClientAdapter(config=self._config)

    def execute(
        self,
        action: str,
        workflow_id: str | None = None,
        queue_name: str | None = None,
        signal_name: str | None = None,
        payload: dict | None = None,
    ) -> str:
        """Execute a temporal action and return tool-compatible result."""
        if action not in _SUPPORTED_ACTIONS:
            supported = ", ".join(sorted(_SUPPORTED_ACTIONS))
            return ToolError(
                f"Validation Error: Unsupported temporal action '{action}'. "
                f"Supported actions: {supported}",
                "validation",
            )

        if action == "report_phase_result":
            return self._handle_report_phase_result(action, workflow_id, payload)

        try:
            self._client_adapter.get_client()
        except TemporalClientUnavailableError as e:
            return ToolError(str(e), "validation")

        response = {
            "ok": True,
            "action": action,
            "workflow_id": workflow_id,
            "queue_name": queue_name,
            "signal_name": signal_name,
            "stub": True,
            "message": "Temporal action acknowledged (Phase 07 service stub).",
        }
        return ToolSuccess(json.dumps(response))

    @staticmethod
    def _handle_report_phase_result(
        action: str,
        workflow_id: str | None,
        payload: dict | None,
    ) -> str:
        if not isinstance(payload, dict):
            return ToolError(
                "Validation Error: report_phase_result requires object payload",
                "validation",
            )

        try:
            contract = validate_temporal_activity_contract(payload)
        except ValidationError as e:
            return ToolError(f"Validation Error: {e}", "validation")

        response = {
            "ok": True,
            "action": action,
            "workflow_id": workflow_id,
            "accepted": True,
            "contract_version": contract.contract_version,
            "status": contract.status,
            "next_recommendation": contract.next_recommendation,
            "action_control": contract.action,
        }
        return ToolSuccess(json.dumps(response))
