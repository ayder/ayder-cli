"""Tests for TemporalWorkflowService action semantics."""

import json

from ayder_cli.core.config import Config, TemporalConfig
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.services.temporal_workflow_service import TemporalWorkflowService


class _FakeClientAdapter:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls = 0

    def get_client(self):
        self.calls += 1
        if self.should_fail:
            from ayder_cli.services.temporal_client import TemporalClientUnavailableError

            raise TemporalClientUnavailableError("Temporal runtime is disabled in config")
        return object()


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


def test_execute_invalid_action_returns_validation_error():
    service = TemporalWorkflowService(
        config=Config(temporal=TemporalConfig(enabled=True)),
        client_adapter=_FakeClientAdapter(),
    )

    result = service.execute("not_real")

    assert isinstance(result, ToolError)
    assert "unsupported temporal action" in str(result).lower()


def test_execute_non_report_action_uses_client_adapter():
    fake = _FakeClientAdapter()
    service = TemporalWorkflowService(
        config=Config(temporal=TemporalConfig(enabled=True)),
        client_adapter=fake,
    )

    result = service.execute("start_workflow", workflow_id="wf-1", queue_name="dev-team")

    assert isinstance(result, ToolSuccess)
    assert fake.calls == 1
    body = json.loads(result)
    assert body["action"] == "start_workflow"
    assert body["workflow_id"] == "wf-1"


def test_execute_non_report_action_returns_error_when_client_unavailable():
    service = TemporalWorkflowService(
        config=Config(temporal=TemporalConfig(enabled=False)),
        client_adapter=_FakeClientAdapter(should_fail=True),
    )

    result = service.execute("query_workflow", workflow_id="wf-2")

    assert isinstance(result, ToolError)
    assert "disabled" in str(result).lower()


def test_execute_report_phase_result_valid_payload():
    service = TemporalWorkflowService(
        config=Config(temporal=TemporalConfig(enabled=True)),
        client_adapter=_FakeClientAdapter(),
    )

    result = service.execute(
        "report_phase_result",
        workflow_id="wf-3",
        payload=_valid_contract_payload(),
    )

    assert isinstance(result, ToolSuccess)
    body = json.loads(result)
    assert body["accepted"] is True
    assert body["action"] == "report_phase_result"


def test_execute_report_phase_result_invalid_payload():
    service = TemporalWorkflowService(
        config=Config(temporal=TemporalConfig(enabled=True)),
        client_adapter=_FakeClientAdapter(),
    )

    payload = _valid_contract_payload()
    payload["execution_mode"] = "git"
    payload["branch_name"] = "none"

    result = service.execute("report_phase_result", payload=payload)

    assert isinstance(result, ToolError)
    assert "validation error" in str(result).lower()
