"""Tests for temporal activity contract validation."""

import pytest
from pydantic import ValidationError

from ayder_cli.application.temporal_contract import (
    TemporalActivityContract,
    validate_temporal_activity_contract,
)


def _base_payload() -> dict:
    return {
        "contract_version": "1.0",
        "execution_mode": "git",
        "status": "PASS",
        "summary": "Done",
        "notes": "Implemented changes",
        "next_recommendation": "qa-team",
        "action": None,
        "origin_queue": "dev-team",
        "branch_name": "feature/abc",
        "commit_sha": "abc1234",
        "report_path": "reports/dev.md",
        "artifacts": ["src/a.py", "tests/test_a.py"],
    }


class TestTemporalActivityContract:
    def test_valid_git_mode_payload(self):
        payload = _base_payload()
        contract = validate_temporal_activity_contract(payload)

        assert isinstance(contract, TemporalActivityContract)
        assert contract.execution_mode == "git"
        assert contract.commit_sha == "abc1234"

    def test_valid_workspace_mode_payload(self):
        payload = _base_payload()
        payload["execution_mode"] = "workspace"
        payload["branch_name"] = "none"
        payload["commit_sha"] = "none"

        contract = validate_temporal_activity_contract(payload)
        assert contract.execution_mode == "workspace"
        assert contract.branch_name == "none"

    def test_invalid_status_raises_error(self):
        payload = _base_payload()
        payload["status"] = "OK"

        with pytest.raises(ValidationError) as exc_info:
            validate_temporal_activity_contract(payload)
        assert "status must be one of PASS, FAIL, NEEDS_CLARIFICATION" in str(
            exc_info.value
        )

    def test_conflicting_action_and_next_recommendation(self):
        payload = _base_payload()
        payload["action"] = "hold"

        with pytest.raises(ValidationError) as exc_info:
            validate_temporal_activity_contract(payload)
        assert "next_recommendation must be null" in str(exc_info.value)

    def test_git_mode_requires_real_branch_and_commit(self):
        payload = _base_payload()
        payload["branch_name"] = "none"

        with pytest.raises(ValidationError) as exc_info:
            validate_temporal_activity_contract(payload)
        assert "git mode requires non-'none'" in str(exc_info.value)

    def test_workspace_mode_requires_none_branch_and_commit(self):
        payload = _base_payload()
        payload["execution_mode"] = "workspace"

        with pytest.raises(ValidationError) as exc_info:
            validate_temporal_activity_contract(payload)
        assert "workspace mode requires branch_name and commit_sha to be 'none'" in str(
            exc_info.value
        )

    def test_report_path_must_be_relative(self):
        payload = _base_payload()
        payload["report_path"] = "/tmp/report.md"

        with pytest.raises(ValidationError) as exc_info:
            validate_temporal_activity_contract(payload)
        assert "report_path must be repository-relative" in str(exc_info.value)

    def test_invalid_contract_version_raises_error(self):
        payload = _base_payload()
        payload["contract_version"] = "2.0"

        with pytest.raises(ValidationError) as exc_info:
            validate_temporal_activity_contract(payload)
        assert "contract_version must be '1.0'" in str(exc_info.value)
