"""Tests for temporal_workflow tool (Phase 05)."""

import json

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.temporal import temporal_workflow


def _valid_contract_payload() -> dict:
    return {
        "contract_version": "1.0",
        "execution_mode": "workspace",
        "status": "PASS",
        "summary": "Completed",
        "notes": "Done",
        "next_recommendation": "qa-team",
        "action": None,
        "origin_queue": "dev-team",
        "branch_name": "none",
        "commit_sha": "none",
        "report_path": "reports/dev.md",
        "artifacts": ["src/x.py"],
    }


def test_temporal_workflow_disabled_returns_error(monkeypatch):
    from ayder_cli.core.config import Config, TemporalConfig

    cfg = Config(temporal=TemporalConfig(enabled=False))
    monkeypatch.setattr(
        "ayder_cli.services.temporal_workflow_service.load_config", lambda: cfg
    )

    result = temporal_workflow(action="query_workflow", workflow_id="wf-1")

    assert isinstance(result, ToolError)
    assert "disabled" in str(result).lower()


def test_temporal_workflow_invalid_action(monkeypatch):
    from ayder_cli.core.config import Config, TemporalConfig

    cfg = Config(temporal=TemporalConfig(enabled=True))
    monkeypatch.setattr(
        "ayder_cli.services.temporal_workflow_service.load_config", lambda: cfg
    )

    result = temporal_workflow(action="unknown_action")

    assert isinstance(result, ToolError)
    assert "unsupported temporal action" in str(result).lower()


def test_temporal_workflow_report_phase_result_valid(monkeypatch):
    from ayder_cli.core.config import Config, TemporalConfig

    cfg = Config(temporal=TemporalConfig(enabled=True))
    monkeypatch.setattr(
        "ayder_cli.services.temporal_workflow_service.load_config", lambda: cfg
    )

    result = temporal_workflow(
        action="report_phase_result",
        workflow_id="wf-1",
        payload=_valid_contract_payload(),
    )

    assert isinstance(result, ToolSuccess)
    body = json.loads(result)
    assert body["accepted"] is True
    assert body["action"] == "report_phase_result"


def test_temporal_workflow_report_phase_result_invalid_payload(monkeypatch):
    from ayder_cli.core.config import Config, TemporalConfig

    cfg = Config(temporal=TemporalConfig(enabled=True))
    monkeypatch.setattr(
        "ayder_cli.services.temporal_workflow_service.load_config", lambda: cfg
    )

    bad_payload = _valid_contract_payload()
    bad_payload["execution_mode"] = "git"
    bad_payload["branch_name"] = "none"

    result = temporal_workflow(
        action="report_phase_result",
        workflow_id="wf-1",
        payload=bad_payload,
    )

    assert isinstance(result, ToolError)
    assert "validation error" in str(result).lower()


def test_temporal_workflow_ack_stub_for_non_report_action(monkeypatch):
    from ayder_cli.core.config import Config, TemporalConfig

    cfg = Config(temporal=TemporalConfig(enabled=True))
    monkeypatch.setattr(
        "ayder_cli.services.temporal_workflow_service.load_config", lambda: cfg
    )
    monkeypatch.setattr(
        "ayder_cli.services.temporal_workflow_service.TemporalClientAdapter.get_client",
        lambda self: object(),
    )

    result = temporal_workflow(
        action="start_workflow",
        workflow_id="wf-22",
        queue_name="dev-team",
    )

    assert isinstance(result, ToolSuccess)
    body = json.loads(result)
    assert body["ok"] is True
    assert body["stub"] is True
    assert body["action"] == "start_workflow"
    assert body["workflow_id"] == "wf-22"
    assert body["queue_name"] == "dev-team"
