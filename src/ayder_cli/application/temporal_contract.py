"""Temporal activity contract model and validation helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TemporalActivityContract(BaseModel):
    """Validated activity output contract for temporal workflows."""

    model_config = ConfigDict(frozen=True)

    contract_version: str = Field(default="1.0")
    execution_mode: str
    status: str
    summary: str
    notes: str
    next_recommendation: str | None = None
    action: str | None = None
    origin_queue: str
    branch_name: str
    commit_sha: str
    report_path: str
    artifacts: list[str] = Field(default_factory=list)

    @field_validator("contract_version")
    @classmethod
    def validate_contract_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError("contract_version must be '1.0'")
        return v

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, v: str) -> str:
        if v not in {"git", "workspace"}:
            raise ValueError("execution_mode must be 'git' or 'workspace'")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"PASS", "FAIL", "NEEDS_CLARIFICATION"}
        if v not in allowed:
            raise ValueError(
                "status must be one of PASS, FAIL, NEEDS_CLARIFICATION"
            )
        return v

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in {"hold", "escalate"}:
            raise ValueError("action must be hold, escalate, or null")
        return v

    @field_validator(
        "summary",
        "notes",
        "origin_queue",
        "branch_name",
        "commit_sha",
        "report_path",
    )
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("required string fields must be non-empty")
        return v

    @field_validator("report_path")
    @classmethod
    def validate_report_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("report_path must be repository-relative")
        return v

    @field_validator("artifacts")
    @classmethod
    def validate_artifacts(cls, v: list[str]) -> list[str]:
        if any(not isinstance(path, str) or not path.strip() for path in v):
            raise ValueError("artifacts must contain non-empty string paths")
        return v

    @model_validator(mode="after")
    def validate_routing_and_mode_rules(self) -> "TemporalActivityContract":
        if self.action is not None and self.next_recommendation is not None:
            raise ValueError(
                "next_recommendation must be null when action is hold/escalate"
            )

        if self.execution_mode == "git":
            if self.branch_name == "none" or self.commit_sha == "none":
                raise ValueError(
                    "git mode requires non-'none' branch_name and commit_sha"
                )
        else:
            if self.branch_name != "none" or self.commit_sha != "none":
                raise ValueError(
                    "workspace mode requires branch_name and commit_sha to be 'none'"
                )

        return self


def validate_temporal_activity_contract(
    payload: dict,
) -> TemporalActivityContract:
    """Validate and return a temporal activity contract object."""
    return TemporalActivityContract(**payload)
