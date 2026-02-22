"""Centralized Validation Authority — Phase 05.

Single validation path — no CLI/TUI divergence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from ayder_cli.application.checkpoint_orchestrator import RuntimeContext


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class ToolRequest:
    """A request to validate a tool invocation."""

    name: str
    arguments: dict


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@dataclass
class ValidationError:
    """Structured validation error with stable fields."""

    tool_name: str
    message: str
    field: str = ""

    def __str__(self) -> str:
        return f"Validation error for '{self.tool_name}': {self.message}"

    def to_dict(self) -> dict:
        return {"tool_name": self.tool_name, "field": self.field, "message": self.message}


# ---------------------------------------------------------------------------
# Validation stages
# ---------------------------------------------------------------------------


class ValidationStage(Enum):
    SCHEMA = "schema"


# ---------------------------------------------------------------------------
# Built-in validators
# ---------------------------------------------------------------------------

class SchemaValidator:
    """Validates tool name, required argument presence, and argument types."""

    def validate(self, request: ToolRequest) -> tuple[bool, Any]:
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

        if request.name not in TOOL_DEFINITIONS_BY_NAME:
            return False, ValidationError(
                tool_name=request.name,
                message=f"unknown tool: '{request.name}' not found in registry",
            )
        td = TOOL_DEFINITIONS_BY_NAME[request.name]
        params = td.parameters

        # Required parameter check
        required = params.get("required", [])
        for arg in required:
            if arg not in request.arguments or request.arguments[arg] is None:
                return False, ValidationError(
                    tool_name=request.name,
                    field=arg,
                    message=f"required argument '{arg}' is missing or empty",
                )

        # Type validation (moved from validate_tool_call in execution.py)
        properties = params.get("properties", {})
        for param_name, value in request.arguments.items():
            if param_name not in properties:
                continue
            expected_type = properties[param_name].get("type")
            if expected_type == "integer" and not isinstance(value, int):
                return False, ValidationError(
                    tool_name=request.name,
                    field=param_name,
                    message=f"'{param_name}' must be integer, got {type(value).__name__}",
                )
            if expected_type == "string" and not isinstance(value, str):
                return False, ValidationError(
                    tool_name=request.name,
                    field=param_name,
                    message=f"'{param_name}' must be string, got {type(value).__name__}",
                )

        return True, None


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


class ValidationAuthority:
    """Single validation authority — no interface-specific logic.

    Does not branch on interface type; context is accepted but ignored.
    """

    _DEFAULT_ORDER = [ValidationStage.SCHEMA]

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {
            "schema": SchemaValidator(),
        }
        self._ordered_stages: list[tuple[str, Any]] = []

    def get_authority(self, type_name: str) -> Any:
        return self._registry[type_name]

    def register(self, stage: str, validator: Any) -> None:
        """Register a validator for a stage (used in tests for custom validators)."""
        self._ordered_stages.append((stage, validator))

    def register_duplicate(self, type_name: str, validator: Any) -> None:
        """Registering a duplicate type is not allowed."""
        raise ValueError(f"Duplicate validator for '{type_name}' is not allowed.")

    def validate(
        self,
        request: ToolRequest,
        context: Optional[RuntimeContext] = None,
    ) -> tuple[bool, Any]:
        """Run validators in order; exit early on first failure."""
        # If custom stages were registered via register(), use those
        if self._ordered_stages:
            for _stage_name, validator in self._ordered_stages:
                ok, err = validator.validate(request)
                if not ok:
                    return False, err
            return True, None

        # Default built-in validation pipeline
        for stage in self._DEFAULT_ORDER:
            validator = self._registry.get(stage.value)
            if validator is None:
                continue
            ok, err = validator.validate(request)
            if not ok:
                return False, err
        return True, None

    @staticmethod
    def get_validation_order() -> list[ValidationStage]:
        """Return the canonical validation stage order — stable and interface-agnostic."""
        return list(ValidationAuthority._DEFAULT_ORDER)
