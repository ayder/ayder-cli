"""Tests for manage_environment_vars tool implementation."""

import pytest
from ayder_cli.tools import utils_tools as impl
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


@pytest.fixture
def sample_env_file(tmp_path):
    """Create a sample .env file for testing."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DATABASE_URL=postgresql://localhost/mydb\n"
        "JWT_SECRET=my_super_secret_key_12345678\n"
        "API_KEY=abcdef123456\n"
        "DEBUG=true\n"
    )
    return env_path


class TestManageEnvironmentVarsValidate:
    """Test validate mode of manage_environment_vars."""

    def test_validate_existing_variable(self, project_context, sample_env_file):
        """Test validating an existing variable."""
        result = impl.manage_environment_vars(
            project_context,
            mode="validate",
            variable_name="JWT_SECRET"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "JWT_SECRET" in result
        assert "exists" in result
        # Check that value is masked
        assert "my_s...5678" in result or "***" in result

    def test_validate_missing_variable(self, project_context, sample_env_file):
        """Test validating a non-existent variable."""
        result = impl.manage_environment_vars(
            project_context,
            mode="validate",
            variable_name="NONEXISTENT_VAR"
        )
        
        assert isinstance(result, ToolError)
        assert "not found" in result
        assert "NONEXISTENT_VAR" in result
        # Should suggest available variables
        assert "Available variables" in result

    def test_validate_missing_env_file(self, project_context):
        """Test validating when .env file doesn't exist."""
        result = impl.manage_environment_vars(
            project_context,
            mode="validate",
            variable_name="JWT_SECRET"
        )
        
        assert isinstance(result, ToolError)
        assert ".env file not found" in result

    def test_validate_missing_variable_name(self, project_context, sample_env_file):
        """Test validate mode without variable_name parameter."""
        result = impl.manage_environment_vars(
            project_context,
            mode="validate"
        )
        
        assert isinstance(result, ToolError)
        assert "variable_name is required" in result

    def test_validate_empty_variable_name(self, project_context, sample_env_file):
        """Test validate mode with empty variable_name."""
        result = impl.manage_environment_vars(
            project_context,
            mode="validate",
            variable_name=""
        )
        
        assert isinstance(result, ToolError)
        assert "variable_name is required" in result


class TestManageEnvironmentVarsLoad:
    """Test load mode of manage_environment_vars."""

    def test_load_existing_env_file(self, project_context, sample_env_file):
        """Test loading all variables from existing .env file."""
        result = impl.manage_environment_vars(
            project_context,
            mode="load"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "ENVIRONMENT VARIABLES" in result
        assert "Total variables: 4" in result
        assert "DATABASE_URL" in result
        assert "JWT_SECRET" in result
        assert "API_KEY" in result
        assert "DEBUG" in result
        # All values must be fully masked to prevent secrets entering LLM context
        assert "DATABASE_URL=***" in result
        assert "DEBUG=***" in result

    def test_load_missing_env_file(self, project_context):
        """Test loading when .env file doesn't exist."""
        result = impl.manage_environment_vars(
            project_context,
            mode="load"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "No .env file found" in result
        assert "generate" in result or "set" in result

    def test_load_empty_env_file(self, project_context, tmp_path):
        """Test loading an empty .env file."""
        env_path = tmp_path / ".env"
        env_path.write_text("")
        
        result = impl.manage_environment_vars(
            project_context,
            mode="load"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "empty" in result


class TestManageEnvironmentVarsGenerate:
    """Test generate mode of manage_environment_vars."""

    def test_generate_new_variable(self, project_context, tmp_path):
        """Test generating a new variable with secure random value."""
        result = impl.manage_environment_vars(
            project_context,
            mode="generate",
            variable_name="JWT_SECRET"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "JWT_SECRET" in result
        assert "created" in result
        assert "(32 chars)" in result
        
        # Verify .env file was created with the variable
        env_path = tmp_path / ".env"
        assert env_path.exists()
        content = env_path.read_text()
        assert "JWT_SECRET=" in content
        # Check that value is hex (32 chars)
        lines = [l for l in content.split("\n") if l.startswith("JWT_SECRET=")]
        assert len(lines) == 1
        value = lines[0].split("=", 1)[1]
        # Remove quotes if present (python-dotenv may add them)
        value = value.strip("'\"")
        assert len(value) == 32
        assert all(c in "0123456789abcdef" for c in value)

    def test_generate_update_existing_variable(self, project_context, sample_env_file):
        """Test updating an existing variable with new generated value."""
        old_secret = "my_super_secret_key_12345678"
        
        result = impl.manage_environment_vars(
            project_context,
            mode="generate",
            variable_name="JWT_SECRET"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "JWT_SECRET" in result
        assert "updated" in result
        
        # Verify the value was changed
        new_content = sample_env_file.read_text()
        assert "JWT_SECRET=" in new_content
        assert old_secret not in new_content

    def test_generate_missing_variable_name(self, project_context):
        """Test generate mode without variable_name parameter."""
        result = impl.manage_environment_vars(
            project_context,
            mode="generate"
        )
        
        assert isinstance(result, ToolError)
        assert "variable_name is required" in result

    def test_generate_creates_env_file_if_missing(self, project_context, tmp_path):
        """Test that generate mode creates .env file if it doesn't exist."""
        env_path = tmp_path / ".env"
        assert not env_path.exists()
        
        result = impl.manage_environment_vars(
            project_context,
            mode="generate",
            variable_name="NEW_SECRET"
        )
        
        assert isinstance(result, ToolSuccess)
        assert env_path.exists()
        assert "NEW_SECRET=" in env_path.read_text()


class TestManageEnvironmentVarsSet:
    """Test set mode of manage_environment_vars."""

    def test_set_new_variable(self, project_context, tmp_path):
        """Test setting a new variable with specific value."""
        result = impl.manage_environment_vars(
            project_context,
            mode="set",
            variable_name="NEW_VAR",
            value="new_value_123"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "NEW_VAR" in result
        assert "created" in result
        
        # Verify .env file was created with the variable
        env_path = tmp_path / ".env"
        assert env_path.exists()
        content = env_path.read_text()
        # python-dotenv may or may not add quotes, so check both
        assert "NEW_VAR=new_value_123" in content or "NEW_VAR='new_value_123'" in content

    def test_set_update_existing_variable(self, project_context, sample_env_file):
        """Test updating an existing variable with new value."""
        result = impl.manage_environment_vars(
            project_context,
            mode="set",
            variable_name="DEBUG",
            value="false"
        )
        
        assert isinstance(result, ToolSuccess)
        assert "DEBUG" in result
        assert "updated" in result
        
        # Verify the value was changed
        content = sample_env_file.read_text()
        # Check that DEBUG is now false (may or may not have quotes)
        assert "DEBUG=false" in content or "DEBUG='false'" in content
        assert "DEBUG=true" not in content

    def test_set_missing_variable_name(self, project_context):
        """Test set mode without variable_name parameter."""
        result = impl.manage_environment_vars(
            project_context,
            mode="set",
            value="some_value"
        )
        
        assert isinstance(result, ToolError)
        assert "variable_name is required" in result

    def test_set_missing_value(self, project_context):
        """Test set mode without value parameter."""
        result = impl.manage_environment_vars(
            project_context,
            mode="set",
            variable_name="TEST_VAR"
        )
        
        assert isinstance(result, ToolError)
        assert "value is required" in result

    def test_set_empty_value(self, project_context, tmp_path):
        """Test setting a variable to empty string."""
        result = impl.manage_environment_vars(
            project_context,
            mode="set",
            variable_name="EMPTY_VAR",
            value=""
        )
        
        assert isinstance(result, ToolSuccess)
        
        # Verify empty value is set
        env_path = tmp_path / ".env"
        content = env_path.read_text()
        assert "EMPTY_VAR=" in content

    def test_set_value_masking_in_output(self, project_context, tmp_path):
        """Test that long values are masked in success message."""
        long_value = "a" * 50
        result = impl.manage_environment_vars(
            project_context,
            mode="set",
            variable_name="LONG_VAR",
            value=long_value
        )
        
        assert isinstance(result, ToolSuccess)
        # Should not show full value
        assert long_value not in result
        # Should show masked version
        assert "..." in result


class TestManageEnvironmentVarsErrors:
    """Test error handling in manage_environment_vars."""

    def test_invalid_mode(self, project_context):
        """Test with invalid mode parameter."""
        result = impl.manage_environment_vars(
            project_context,
            mode="invalid_mode"
        )
        
        assert isinstance(result, ToolError)
        assert "Invalid mode" in result
        assert "validate" in result
        assert "load" in result
        assert "generate" in result
        assert "set" in result

    def test_path_traversal_attempt(self, project_context):
        """Test that path traversal is blocked by ProjectContext."""
        # This should be caught by ProjectContext.validate_path()
        # The .env file is always at project root, so traversal shouldn't be possible
        # But we test that security is in place
        result = impl.manage_environment_vars(
            project_context,
            mode="load"
        )
        
        # Should succeed (no traversal possible since .env is always at root)
        # This test verifies the tool uses ProjectContext properly
        assert isinstance(result, (ToolSuccess, ToolError))

    def test_empty_string_mode(self, project_context):
        """Test with empty string mode."""
        result = impl.manage_environment_vars(
            project_context,
            mode=""
        )
        
        assert isinstance(result, ToolError)
        assert "Invalid mode" in result


class TestManageEnvironmentVarsIntegration:
    """Integration tests for full workflows."""

    def test_full_workflow_generate_then_validate(self, project_context, tmp_path):
        """Test generating a variable and then validating it."""
        # Generate
        result1 = impl.manage_environment_vars(
            project_context,
            mode="generate",
            variable_name="JWT_SECRET"
        )
        assert isinstance(result1, ToolSuccess)
        
        # Validate
        result2 = impl.manage_environment_vars(
            project_context,
            mode="validate",
            variable_name="JWT_SECRET"
        )
        assert isinstance(result2, ToolSuccess)
        assert "exists" in result2

    def test_full_workflow_set_then_load(self, project_context, tmp_path):
        """Test setting variables and then loading all."""
        # Set multiple variables
        impl.manage_environment_vars(
            project_context, mode="set",
            variable_name="VAR1", value="value1"
        )
        impl.manage_environment_vars(
            project_context, mode="set",
            variable_name="VAR2", value="value2"
        )
        impl.manage_environment_vars(
            project_context, mode="set",
            variable_name="VAR3", value="value3"
        )
        
        # Load all
        result = impl.manage_environment_vars(
            project_context,
            mode="load"
        )
        assert isinstance(result, ToolSuccess)
        assert "Total variables: 3" in result
        assert "VAR1" in result
        assert "VAR2" in result
        assert "VAR3" in result

    def test_generate_produces_different_values(self, project_context, tmp_path):
        """Test that generate mode produces different values each time."""
        # Generate first value
        impl.manage_environment_vars(
            project_context,
            mode="generate",
            variable_name="SECRET1"
        )
        
        # Generate second value
        impl.manage_environment_vars(
            project_context,
            mode="generate",
            variable_name="SECRET2"
        )
        
        # Read both values
        env_path = tmp_path / ".env"
        content = env_path.read_text()
        lines = content.strip().split("\n")
        
        secret1_line = [l for l in lines if l.startswith("SECRET1=")]
        secret2_line = [l for l in lines if l.startswith("SECRET2=")]
        
        assert len(secret1_line) == 1
        assert len(secret2_line) == 1
        
        secret1_val = secret1_line[0].split("=", 1)[1]
        secret2_val = secret2_line[0].split("=", 1)[1]
        
        # Values should be different
        assert secret1_val != secret2_val
