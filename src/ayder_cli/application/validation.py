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
    PERMISSION = "permission"


# ---------------------------------------------------------------------------
# Built-in validators
# ---------------------------------------------------------------------------

# Known tools and their required arguments.
# All real registry tools are listed here so SchemaValidator is permissive for
# valid tool names. Only tool names absent from this set are treated as unknown.
_KNOWN_TOOLS: dict[str, list[str]] = {
    "list_files": [],
    "read_file": ["file_path"],
    "write_file": ["file_path", "content"],
    "replace_string": ["file_path"],
    "insert_line": ["file_path"],
    "delete_line": ["file_path"],
    "get_file_info": ["file_path"],
    "save_memory": [],
    "load_memory": [],
    "create_note": [],
    "run_background_process": ["command"],
    "get_background_output": [],
    "kill_background_process": [],
    "list_background_processes": [],
    "search_codebase": ["query"],
    "get_project_structure": [],
    "run_shell_command": ["command"],
    "list_tasks": [],
    "show_task": [],
    "manage_environment_vars": [],
    "create_virtualenv": [],
    "install_requirements": [],
    "list_virtualenvs": [],
    "activate_virtualenv": [],
    "remove_virtualenv": [],
}


class SchemaValidator:
    """Validates tool name and required argument presence."""

    def validate(self, request: ToolRequest) -> tuple[bool, Any]:
        if request.name not in _KNOWN_TOOLS:
            return False, ValidationError(
                tool_name=request.name,
                message=f"unknown tool: '{request.name}' not found in registry",
            )
        required = _KNOWN_TOOLS[request.name]
        for arg in required:
            if arg not in request.arguments or request.arguments[arg] is None:
                return False, ValidationError(
                    tool_name=request.name,
                    field=arg,
                    message=f"required argument '{arg}' is missing or empty",
                )
        return True, None


class PermissionValidator:
    """Validates that required permissions are present (stub — policy layer owns this)."""

    def validate(self, request: ToolRequest) -> tuple[bool, Any]:
        return True, None


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


class ValidationAuthority:
    """Single validation authority — no interface-specific logic.

    Does not branch on interface type; context is accepted but ignored.
    """

    _DEFAULT_ORDER = [ValidationStage.SCHEMA, ValidationStage.PERMISSION]

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {
            "schema": SchemaValidator(),
            "permission": PermissionValidator(),
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
