"""Validation Path Tests — Phase 05 (TEST-FIRST)

Contract: Validation authority is centralized (single path, no conflicting duplicates).

These tests define expected behavior BEFORE DEV implements centralized validation.
"""

import pytest
from unittest.mock import Mock


class TestNoRedundantValidation:
    """Validation must not be redundantly applied in conflicting ways."""

    def test_single_validation_authority(self):
        """One validation component has authority per validation type."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                SchemaValidator,
                PermissionValidator,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        # Authority registry ensures single owner per validation type
        authority = ValidationAuthority()
        
        schema = authority.get_authority("schema")
        permission = authority.get_authority("permission")
        
        # Different types have different authorities
        assert isinstance(schema, SchemaValidator)
        assert isinstance(permission, PermissionValidator)

    def test_no_duplicate_validators_same_type(self):
        """No two validators handle the same validation type."""
        try:
            from ayder_cli.application.validation import ValidationAuthority
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        # Registering duplicate should fail or replace
        with pytest.raises((ValueError, RuntimeError)):
            authority.register_duplicate("schema", Mock())

    def test_validation_runs_once_per_type(self):
        """Each validation type runs exactly once per tool call."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                ToolRequest,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        mock_validator = Mock()
        mock_validator.validate.return_value = (True, None)
        
        authority.register("schema", mock_validator)
        
        request = ToolRequest(name="read_file", arguments={})
        
        # Validate once
        authority.validate(request)
        
        # Schema validator called once
        mock_validator.validate.assert_called_once()


class TestNoConflictingValidation:
    """No conflicting validation layers."""

    def test_consistent_validation_rules(self):
        """Same validation rules apply regardless of entry point."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                ToolRequest,
                RuntimeContext,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        request = ToolRequest(name="write_file", arguments={"file_path": "/test.txt"})
        
        # Same validation from CLI entry
        cli_valid, cli_error = authority.validate(request, context=RuntimeContext(interface="cli"))
        
        # Same validation from TUI entry
        tui_valid, tui_error = authority.validate(request, context=RuntimeContext(interface="tui"))
        
        # Consistent results
        assert cli_valid == tui_valid
        if cli_error and tui_error:
            assert type(cli_error) == type(tui_error)

    def test_no_path_dependent_validation_rules(self):
        """Validation rules don't depend on code path taken."""
        try:
            from ayder_cli.application.validation import ValidationAuthority
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        import inspect
        
        # Check validation source for path-dependent logic
        source = inspect.getsource(ValidationAuthority)
        
        # Should not branch on interface or path
        assert "if cli" not in source.lower()
        assert "if tui" not in source.lower()
        assert "if interface" not in source.lower()

    def test_normalized_validation_order(self):
        """Validation runs in consistent order."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                ValidationStage,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        # Order is explicit and consistent
        order = authority.get_validation_order()
        
        assert ValidationStage.SCHEMA in order
        assert ValidationStage.PERMISSION in order
        
        # Order doesn't change
        order2 = authority.get_validation_order()
        assert order == order2


class TestUserVisibleErrors:
    """Validation errors remain user-visible and stable."""

    def test_error_messages_clear(self):
        """Validation error messages are clear and actionable."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                ToolRequest,
                ValidationError,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        # Invalid request
        request = ToolRequest(name="unknown_tool", arguments={})
        
        valid, error = authority.validate(request)
        
        assert valid is False
        assert error is not None
        # Clear message
        assert len(str(error)) > 0
        assert "unknown" in str(error).lower() or "not found" in str(error).lower()

    def test_error_includes_context(self):
        """Error includes what was being validated."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                ToolRequest,
                ValidationError,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        request = ToolRequest(name="write_file", arguments={})  # Missing content
        
        valid, error = authority.validate(request)
        
        if not valid:
            # Error mentions the tool and field
            error_str = str(error)
            assert "write_file" in error_str or "content" in error_str.lower()

    def test_stable_error_format(self):
        """Error format is stable for programmatic handling."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                ToolRequest,
                ValidationError,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        request = ToolRequest(name="invalid", arguments={})
        
        valid, error = authority.validate(request)
        
        if not valid and error:
            # Structured error with stable fields
            assert hasattr(error, "tool_name") or hasattr(error, "message")
            assert hasattr(error, "to_dict")  # Programmatic access


class TestValidationCentralization:
    """Validation authority centralization contract."""

    def test_single_validation_entry_point(self):
        """One entry point for all validation."""
        try:
            from ayder_cli.application.validation import ValidationAuthority
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        # Authority is singleton or shared instance
        auth1 = ValidationAuthority()
        auth2 = ValidationAuthority()
        
        # Same authority (or equivalent)
        assert type(auth1) == type(auth2)

    def test_validation_not_bypassed(self):
        """No code path bypasses centralized validation."""
        try:
            from ayder_cli.application.execution_policy import ExecutionPolicy
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        import inspect
        
        # Check that execution uses validation authority
        source = inspect.getsource(ExecutionPolicy)
        
        assert "ValidationAuthority" in source or "validate" in source

    def test_old_bypass_paths_removed(self):
        """Old bypass paths are removed or delegate to authority."""
        try:
            from ayder_cli.tui.chat_loop import TuiChatLoop
            from ayder_cli.services.tools.executor import ToolExecutor
        except ImportError:
            pytest.skip("Implementation not yet available")

        import inspect
        
        # Check TUI doesn't have its own validation
        tui_source = inspect.getsource(TuiChatLoop)
        
        # TUI should delegate, not validate directly
        # (This test will fail if TUI still has inline validation)
        direct_validation = [
            "validate_args" in tui_source,
            "check_permission" in tui_source,
        ]
        
        # If validation exists, it should delegate to authority
        if any(direct_validation):
            assert "ValidationAuthority" in tui_source or "authority" in tui_source.lower()


class TestValidationStageContract:
    """Validation stage ordering and behavior."""

    def test_schema_validation_first(self):
        """Schema validation runs before permission validation."""
        try:
            from ayder_cli.application.validation import (
                ValidationAuthority,
                ValidationStage,
            )
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        order = ValidationAuthority.get_validation_order()
        
        schema_idx = order.index(ValidationStage.SCHEMA)
        permission_idx = order.index(ValidationStage.PERMISSION)
        
        assert schema_idx < permission_idx

    def test_early_exit_on_failure(self):
        """Validation exits early on first failure."""
        try:
            from ayder_cli.application.validation import ValidationAuthority
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        mock_validator1 = Mock()
        mock_validator1.validate.return_value = (False, "First error")
        
        mock_validator2 = Mock()
        mock_validator2.validate.return_value = (True, None)
        
        authority.register("stage1", mock_validator1)
        authority.register("stage2", mock_validator2)
        
        from ayder_cli.application.validation import ToolRequest
        request = ToolRequest(name="test", arguments={})
        
        valid, error = authority.validate(request)
        
        assert valid is False
        assert str(error) == "First error"
        # Second validator not called due to early exit
        mock_validator2.validate.assert_not_called()

    def test_all_stages_run_on_success(self):
        """All validation stages run when validation succeeds."""
        try:
            from ayder_cli.application.validation import ValidationAuthority
        except ImportError:
            pytest.skip("Validation authority not yet implemented")

        authority = ValidationAuthority()
        
        mock_validator1 = Mock()
        mock_validator1.validate.return_value = (True, None)
        
        mock_validator2 = Mock()
        mock_validator2.validate.return_value = (True, None)
        
        authority.register("stage1", mock_validator1)
        authority.register("stage2", mock_validator2)
        
        from ayder_cli.application.validation import ToolRequest
        request = ToolRequest(name="test", arguments={})
        
        valid, _ = authority.validate(request)
        
        assert valid is True
        mock_validator1.validate.assert_called_once()
        mock_validator2.validate.assert_called_once()
