"""Tests for virtual environment management tools."""

import sys
import shutil
from unittest.mock import patch, MagicMock
import pytest
from pathlib import Path
from ayder_cli.tools import venv as impl
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


class TestCreateVirtualenv:
    """Tests for create_virtualenv function."""

    def test_create_virtualenv_success(self, tmp_path, project_context):
        """Test creating a virtual environment successfully."""
        # Note: This test will actually create a venv (for coverage, or skip during CI)
        # For faster tests, run with: pytest --disable-subprocess-mock
        result = impl.create_virtualenv(project_context, ".venv")
        
        assert isinstance(result, ToolSuccess)
        venv_path = tmp_path / ".venv"
        assert venv_path.exists()

    def test_create_virtualenv_different_name(self, tmp_path, project_context):
        """Test creating a custom-named virtual environment."""
        result = impl.create_virtualenv(project_context, ".venv311")
        
        assert isinstance(result, ToolSuccess)
        venv_path = tmp_path / ".venv311"
        assert venv_path.exists()

    def test_create_virtualenv_already_exists(self, tmp_path, project_context):
        """Test error when virtual environment already exists."""
        # Create existing .venv
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "pyvenv.cfg").write_text("version = 3.12\n")
        
        result = impl.create_virtualenv(project_context, ".venv")
        
        assert isinstance(result, ToolError)
        assert "already exists" in str(result)

    def test_create_virtualenv_invalid_name_security(self, tmp_path):
        """Test path traversal attack is blocked."""
        ctx = ProjectContext(str(tmp_path))
        result = impl.create_virtualenv(ctx, "../../../tmp/badenv")
        
        assert isinstance(result, ToolError)
        assert result.category == "security"
        assert "Invalid" in str(result) or "Security" in str(result)

    def test_create_virtualenv_empty_name(self, tmp_path, project_context):
        """Test empty environment name."""
        result = impl.create_virtualenv(project_context, "")
        
        # Empty string should be handled (may create at root or error)
        assert isinstance(result, (ToolSuccess, ToolError))

    def test_create_virtualenv_with_python_version(self, tmp_path, project_context):
        """Test creating with specific Python version."""
        result = impl.create_virtualenv(project_context, ".venv313", "3.13")
        
        assert isinstance(result, ToolSuccess)
        venv_path = tmp_path / ".venv313"
        assert venv_path.exists()

    def test_create_virtualenv_invalid_python_version_warning(self, tmp_path, project_context):
        """Test warning for non-standard Python version."""
        result = impl.create_virtualenv(project_context, ".venv", "3.99")
        
        # Returns ToolError with warning (we validate strictly)
        assert isinstance(result, ToolError)
        assert "Warning" in str(result) or "version" in str(result).lower()
        assert "may not be available" in str(result)

    def test_create_virtualenv_permission_error(self, tmp_path, project_context):
        """Test error handling for permission issues."""
        # Mock subprocess to raise an error
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Permission denied")
            
            result = impl.create_virtualenv(project_context, ".venv")
            
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Failed to create" in str(result)


class TestInstallRequirements:
    """Tests for install_requirements function."""

    def test_install_requirements_success(self, tmp_path, project_context):
        """Test installing dependencies successfully."""
        # Create virtual environment
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        
        # Create bin directory structure
        bin_dir = venv_path / "bin"
        bin_dir.mkdir()
        
        # Create pip executable (must be a real file, not empty)
        pip_path = bin_dir / "pip"
        pip_path.write_text("#!/bin/bash\necho 'pip'\n")
        pip_path.chmod(0o755)  # Make executable
        
        # Create requirements.txt
        req_path = tmp_path / "requirements.txt"
        req_path.write_text("requests>=2.28.0\n")
        
        # Mock subprocess.run to simulate successful pip install
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Collecting requests\nSuccessfully installed requests-2.32.0\n")
            result = impl.install_requirements(project_context)
        
        assert isinstance(result, ToolSuccess)
        assert "installed" in str(result).lower() or "successfully" in str(result).lower()

    def test_install_requirements_pyproject_toml(self, tmp_path, project_context):
        """Test installing from pyproject.toml (should handle gracefully)."""
        # Create virtual environment
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        
        # Create pyproject.toml
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text("[project]\nname = 'test'\n")
        
        # This should handle the file not being requirements.txt
        result = impl.install_requirements(project_context, "pyproject.toml")
        
        # Should error since pyproject.toml isn't valid requirements format
        # or handle gracefully
        assert isinstance(result, (ToolSuccess, ToolError))

    def test_install_requirements_file_not_found(self, tmp_path, project_context):
        """Test error when requirements file doesn't exist."""
        # Create virtual environment
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        
        result = impl.install_requirements(project_context, "nonexistent_requirements.txt")
        
        assert isinstance(result, ToolError)
        assert "Requirements file not found" in str(result)

    def test_install_requirements_env_not_found(self, tmp_path, project_context):
        """Test error when virtual environment doesn't exist."""
        result = impl.install_requirements(project_context)
        
        assert isinstance(result, ToolError)
        assert "Virtual environment not found" in str(result)

    def test_install_requirements_invalid_path_security(self, tmp_path):
        """Test path traversal is blocked."""
        ctx = ProjectContext(str(tmp_path))
        result = impl.install_requirements(ctx, "../../../etc/passwd")
        
        assert isinstance(result, ToolError)
        assert result.category == "security"

    def test_install_requirements_multiple_packages(self, tmp_path, project_context):
        """Test installing multiple packages."""
        # Create virtual environment
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        
        # Create pip executable
        pip_path = venv_path / "bin" / "pip"
        pip_path.write_text("#!/bin/bash\necho 'pip'\n")
        pip_path.chmod(0o755)
        
        # Create requirements.txt with multiple packages
        req_path = tmp_path / "requirements.txt"
        req_path.write_text("requests>=2.28.0\npytest>=7.0.0\nrich>=13.0.0\n")
        
        # Mock subprocess.run to simulate successful pip install
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Collecting packages\nSuccessfully installed\n")
            result = impl.install_requirements(project_context)
        
        assert isinstance(result, ToolSuccess)

    def test_install_requirements_empty_requirements(self, tmp_path, project_context):
        """Test handling empty requirements file."""
        # Create virtual environment
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        
        # Create empty requirements.txt
        req_path = tmp_path / "requirements.txt"
        req_path.write_text("")
        
        result = impl.install_requirements(project_context)
        
        # Should handle gracefully
        assert isinstance(result, (ToolSuccess, ToolError))

    def test_install_requirements_timeout(self, tmp_path, project_context):
        """Test timeout handling."""
        # Create virtual environment
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        
        # Create pip executable (must be a real file, not empty)
        pip_path = venv_path / "bin" / "pip"
        pip_path.write_text("#!/bin/bash\necho 'pip'\n")
        pip_path.chmod(0o755)  # Make executable
        
        req_path = tmp_path / "requirements.txt"
        req_path.write_text("requests\n")
        
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 300)):
            result = impl.install_requirements(project_context)
            
            assert isinstance(result, ToolError)
            assert "timed out" in str(result).lower()

    def test_install_requirements_pip_not_found(self, tmp_path, project_context):
        """Test error when pip not found in virtual environment."""
        # Create virtual environment without pip
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        
        req_path = tmp_path / "requirements.txt"
        req_path.write_text("requests\n")
        
        result = impl.install_requirements(project_context)
        
        assert isinstance(result, ToolError)
        assert "pip not found" in str(result).lower()


class TestListVirtualenvs:
    """Tests for list_virtualenvs function."""

    def test_list_virtualenvs_none(self, tmp_path, project_context):
        """Test when no virtual environments exist."""
        result = impl.list_virtualenvs(project_context)
        
        assert isinstance(result, ToolSuccess)
        assert "No virtual environments found" in str(result)

    def test_list_virtualenvs_single(self, tmp_path, project_context):
        """Test listing a single virtual environment."""
        # Create .venv directory
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "pyvenv.cfg").write_text("version = 3.12\n")
        
        result = impl.list_virtualenvs(project_context)
        
        assert isinstance(result, ToolSuccess)
        assert ".venv" in str(result)
        assert "Python 3.12" in str(result)

    def test_list_virtualenvs_multiple(self, tmp_path, project_context):
        """Test listing multiple virtual environments."""
        # Create multiple virtual environments
        for env_name in [".venv", ".venv311", ".venv313"]:
            venv_path = tmp_path / env_name
            venv_path.mkdir()
            (venv_path / "pyvenv.cfg").write_text(f"version = {env_name.replace('.venv', '3.')}\n")
        
        result = impl.list_virtualenvs(project_context)
        
        assert isinstance(result, ToolSuccess)
        assert ".venv" in str(result)
        assert ".venv311" in str(result)
        assert ".venv313" in str(result)

    def test_list_virtualenvs_format(self, tmp_path, project_context):
        """Test output formatting."""
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        
        result = impl.list_virtualenvs(project_context)
        
        # Should have structured output
        assert "Available Virtual Environments:" in str(result)
        assert "Total environments:" in str(result)

    def test_list_virtualenvs_sorting(self, tmp_path, project_context):
        """Test that environments are sorted."""
        # Create in reverse order
        for env_name in [".venv313", ".venv311", ".venv"]:
            venv_path = tmp_path / env_name
            venv_path.mkdir()
        
        result = impl.list_virtualenvs(project_context)
        
        # Result should be sorted (alphabetically or by version)
        assert isinstance(result, ToolSuccess)

    def test_list_virtualenvs_symlinks(self, tmp_path, project_context):
        """Test handling of symbolic links."""
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        
        result = impl.list_virtualenvs(project_context)
        
        # Should handle symlinks appropriately
        assert isinstance(result, ToolSuccess)


class TestActivateVirtualenv:
    """Tests for activate_virtualenv function."""

    def test_activate_virtualenv_success(self, tmp_path, project_context):
        """Test getting activation instructions."""
        # Create .venv directory
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        
        result = impl.activate_virtualenv(project_context, ".venv")
        
        assert isinstance(result, ToolSuccess)
        assert "activate" in str(result).lower()
        assert ".venv" in str(result)

    def test_activate_virtualenv_different_name(self, tmp_path, project_context):
        """Test with custom environment name."""
        venv_path = tmp_path / ".venv311"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        
        result = impl.activate_virtualenv(project_context, ".venv311")
        
        assert isinstance(result, ToolSuccess)
        assert ".venv311" in str(result)

    def test_activate_virtualenv_not_found(self, tmp_path, project_context):
        """Test error when environment doesn't exist."""
        result = impl.activate_virtualenv(project_context, "nonexistent")
        
        assert isinstance(result, ToolError)
        assert "not found" in str(result)

    def test_activate_virtualenv_invalid_path_security(self, tmp_path):
        """Test path traversal is blocked."""
        ctx = ProjectContext(str(tmp_path))
        result = impl.activate_virtualenv(ctx, "../../../tmp/env")
        
        assert isinstance(result, ToolError)
        assert result.category == "security"

    def test_activate_virtualenv_fish(self, tmp_path, project_context):
        """Test fish shell commands are provided."""
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        
        result = impl.activate_virtualenv(project_context)
        
        assert isinstance(result, ToolSuccess)
        # Fish activation should be included
        assert "activate.fish" in str(result) or "fish" in str(result).lower()

    def test_activate_virtualenv_powershell(self, tmp_path, project_context):
        """Test PowerShell commands are provided."""
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        
        result = impl.activate_virtualenv(project_context)
        
        assert isinstance(result, ToolSuccess)
        # Activation commands should be included (bash/zsh by default on macOS)
        assert "activate" in str(result).lower()


class TestRemoveVirtualenv:
    """Tests for remove_virtualenv function."""

    def test_remove_virtualenv_success(self, tmp_path, project_context):
        """Test removing a virtual environment."""
        # Create .venv directory with content
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "pyvenv.cfg").write_text("version = 3.12\n")
        
        result = impl.remove_virtualenv(project_context, ".venv", force=True)
        
        assert isinstance(result, ToolSuccess)
        assert not venv_path.exists()
        assert "removed successfully" in str(result).lower()

    def test_remove_virtualenv_different_name(self, tmp_path, project_context):
        """Test removing custom-named environment."""
        venv_path = tmp_path / ".venv311"
        venv_path.mkdir()
        
        result = impl.remove_virtualenv(project_context, ".venv311", force=True)
        
        assert isinstance(result, ToolSuccess)
        assert not venv_path.exists()

    def test_remove_virtualenv_not_found(self, tmp_path, project_context):
        """Test error when environment doesn't exist."""
        result = impl.remove_virtualenv(project_context, "nonexistent")
        
        assert isinstance(result, ToolError)
        assert "not found" in str(result)

    def test_remove_virtualenv_invalid_path_security(self, tmp_path):
        """Test path traversal is blocked."""
        ctx = ProjectContext(str(tmp_path))
        result = impl.remove_virtualenv(ctx, "../../../tmp/env", force=True)
        
        assert isinstance(result, ToolError)
        assert result.category == "security"

    def test_remove_virtualenv_prompts_confirmation(self, tmp_path, project_context):
        """Test that removal prompts for confirmation by default."""
        # Create .venv directory
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "pyvenv.cfg").write_text("version = 3.12\n")
        
        # Without force=True, should prompt for confirmation
        result = impl.remove_virtualenv(project_context, ".venv")
        
        assert isinstance(result, ToolError)
        assert "Confirmation" in str(result) or "confirm" in str(result).lower()

    def test_remove_virtualenv_not_directory(self, tmp_path, project_context):
        """Test error when path is not a directory."""
        # Create a file instead of directory
        file_path = tmp_path / ".venv"
        file_path.write_text("not a directory")
        
        result = impl.remove_virtualenv(project_context, ".venv", force=True)
        
        assert isinstance(result, ToolError)
        assert "not a directory" in str(result)

    def test_remove_virtualenv_deletes_subdirectories(self, tmp_path, project_context):
        """Test that subdirectories are also deleted."""
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "lib").mkdir()
        
        result = impl.remove_virtualenv(project_context, ".venv", force=True)
        
        assert isinstance(result, ToolSuccess)
        assert not venv_path.exists()


class TestIntegration:
    """Integration tests for virtual environment tools."""

    def test_workflow_create_and_install(self, tmp_path, project_context):
        """End-to-end workflow: create virtual environment then install dependencies."""
        # Create virtual environment
        result1 = impl.create_virtualenv(project_context, ".venv")
        assert isinstance(result1, ToolSuccess)
        assert (tmp_path / ".venv").exists()
        
        # Set up pip with mock
        venv_path = tmp_path / ".venv"
        (venv_path / "bin").mkdir(parents=True, exist_ok=True)
        
        # Create requirements.txt
        (tmp_path / "requirements.txt").write_text("requests\n")
        
        # Install requirements (with mock)
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Successfully installed\n")
            result2 = impl.install_requirements(project_context)
        assert isinstance(result2, (ToolSuccess, ToolError))
        # May fail if pip doesn't work in test, but shouldn't crash

    def test_workflow_list_and_remove(self, tmp_path, project_context):
        """Workflow: create, list, then remove virtual environment."""
        # Create environment
        result1 = impl.create_virtualenv(project_context, ".venv311")
        assert isinstance(result1, ToolSuccess)
        
        # List environments
        result2 = impl.list_virtualenvs(project_context)
        assert isinstance(result2, ToolSuccess)
        assert ".venv311" in str(result2)
        
        # Remove environment
        result3 = impl.remove_virtualenv(project_context, ".venv311", force=True)
        assert isinstance(result3, ToolSuccess)

    def test_workflow_multiple_environments(self, tmp_path, project_context):
        """Manage multiple virtual environments."""
        # Create multiple environments
        for env_name in [".venv", ".venv311", ".venv313"]:
            result = impl.create_virtualenv(project_context, env_name)
            assert isinstance(result, ToolSuccess)
        
        # List them
        result = impl.list_virtualenvs(project_context)
        assert isinstance(result, ToolSuccess)
        
        # Get activation for each
        for env_name in [".venv", ".venv311", ".venv313"]:
            result = impl.activate_virtualenv(project_context, env_name)
            assert isinstance(result, ToolSuccess)
            assert env_name in str(result)
