"""Tests for config.py module."""

from pathlib import Path
import pytest
from unittest import mock

from ayder_cli.config import (
    DEFAULTS,
    _DEFAULT_TOML,
    CONFIG_DIR,
    CONFIG_PATH,
    load_config,
)


class TestDefaultValues:
    """Test default configuration values."""

    def test_defaults_dictionary(self):
        """Test that DEFAULTS contains expected keys and values."""
        assert DEFAULTS["base_url"] == "http://localhost:11434/v1"
        assert DEFAULTS["api_key"] == "ollama"
        assert DEFAULTS["model"] == "qwen3-coder:latest"
        assert DEFAULTS["num_ctx"] == 65536
        assert DEFAULTS["editor"] == "vim"
        assert DEFAULTS["verbose"] is False

    def test_defaults_contains_all_keys(self):
        """Test that DEFAULTS has all required configuration keys."""
        required_keys = ["base_url", "api_key", "model", "num_ctx", "editor", "verbose"]
        for key in required_keys:
            assert key in DEFAULTS

    def test_default_toml_template(self):
        """Test that _DEFAULT_TOML template contains expected sections."""
        assert "[llm]" in _DEFAULT_TOML
        assert "[editor]" in _DEFAULT_TOML
        assert "[ui]" in _DEFAULT_TOML
        assert "{base_url}" in _DEFAULT_TOML
        assert "{api_key}" in _DEFAULT_TOML
        assert "{model}" in _DEFAULT_TOML
        assert "{num_ctx}" in _DEFAULT_TOML
        assert "{editor}" in _DEFAULT_TOML
        assert "{verbose_str}" in _DEFAULT_TOML

    def test_config_paths_defined(self):
        """Test that CONFIG_DIR and CONFIG_PATH are defined."""
        assert isinstance(CONFIG_DIR, Path)
        assert isinstance(CONFIG_PATH, Path)
        assert CONFIG_DIR.name == ".ayder"
        assert CONFIG_PATH.name == "config.toml"
        assert CONFIG_DIR in CONFIG_PATH.parents or CONFIG_PATH.parent == CONFIG_DIR


class TestLoadConfigFirstRun:
    """Test load_config() when config file doesn't exist (first run)."""

    def test_config_creation_when_file_missing(self, tmp_path, monkeypatch):
        """Test config file creation when it doesn't exist."""
        # Mock config paths to use temp directory
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        # Ensure file doesn't exist
        assert not mock_config_path.exists()
        
        # Load config
        config = load_config()
        
        # Verify file was created
        assert mock_config_path.exists()
        
        # Verify content is written
        content = mock_config_path.read_text()
        assert "[llm]" in content
        assert "[editor]" in content
        assert "[ui]" in content

    def test_default_values_returned_on_first_run(self, tmp_path, monkeypatch):
        """Test that default values are returned when creating new config."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        # Verify defaults are returned
        assert config == DEFAULTS

    def test_config_directory_creation(self, tmp_path, monkeypatch):
        """Test that config directory is created if it doesn't exist."""
        mock_config_dir = tmp_path / ".ayder" / "nested" / "path"
        mock_config_path = mock_config_dir / "config.toml"
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        # Ensure directory doesn't exist
        assert not mock_config_dir.exists()
        
        load_config()
        
        # Verify directory was created
        assert mock_config_dir.exists()
        assert mock_config_dir.is_dir()

    def test_default_toml_has_correct_values(self, tmp_path, monkeypatch):
        """Test that created config file has correct default values."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        load_config()
        
        content = mock_config_path.read_text()
        
        # Verify actual values in file
        assert 'base_url = "http://localhost:11434/v1"' in content
        assert 'api_key = "ollama"' in content
        assert 'model = "qwen3-coder:latest"' in content
        assert "num_ctx = 65536" in content
        assert 'editor = "vim"' in content
        assert "verbose = false" in content


class TestLoadConfigExistingConfig:
    """Test load_config() with existing config file."""

    def test_loading_existing_valid_config(self, tmp_path, monkeypatch):
        """Test loading a fully populated existing config file."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        # Create config file with custom values
        config_content = """\
[llm]
base_url = "https://api.example.com/v1"
api_key = "my-secret-key"
model = "gpt-4"
num_ctx = 128000

[editor]
editor = "nano"

[ui]
verbose = true
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        # Verify custom values are loaded
        assert config["base_url"] == "https://api.example.com/v1"
        assert config["api_key"] == "my-secret-key"
        assert config["model"] == "gpt-4"
        assert config["num_ctx"] == 128000
        assert config["editor"] == "nano"
        assert config["verbose"] is True

    def test_partial_config_llm_only(self, tmp_path, monkeypatch):
        """Test loading config with only llm section defined."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        config_content = """\
[llm]
base_url = "https://custom.api.com"
model = "custom-model"
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        # Verify llm values loaded
        assert config["base_url"] == "https://custom.api.com"
        assert config["model"] == "custom-model"
        # Verify defaults for missing sections
        assert config["api_key"] == DEFAULTS["api_key"]
        assert config["num_ctx"] == DEFAULTS["num_ctx"]
        assert config["editor"] == DEFAULTS["editor"]
        assert config["verbose"] == DEFAULTS["verbose"]

    def test_partial_config_editor_only(self, tmp_path, monkeypatch):
        """Test loading config with only editor section defined."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        config_content = """\
[editor]
editor = "emacs"
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        # Verify editor value loaded
        assert config["editor"] == "emacs"
        # Verify defaults for llm
        assert config["base_url"] == DEFAULTS["base_url"]
        assert config["api_key"] == DEFAULTS["api_key"]
        assert config["model"] == DEFAULTS["model"]
        assert config["num_ctx"] == DEFAULTS["num_ctx"]
        assert config["verbose"] == DEFAULTS["verbose"]

    def test_partial_config_ui_only(self, tmp_path, monkeypatch):
        """Test loading config with only ui section defined."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        config_content = """\
[ui]
verbose = true
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        # Verify ui value loaded
        assert config["verbose"] is True
        # Verify defaults for other sections
        assert config["base_url"] == DEFAULTS["base_url"]
        assert config["api_key"] == DEFAULTS["api_key"]
        assert config["model"] == DEFAULTS["model"]
        assert config["num_ctx"] == DEFAULTS["num_ctx"]
        assert config["editor"] == DEFAULTS["editor"]

    def test_partial_config_missing_keys_in_llm(self, tmp_path, monkeypatch):
        """Test that missing keys in llm section fall back to defaults."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        config_content = """\
[llm]
model = "only-model-defined"
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        assert config["model"] == "only-model-defined"
        assert config["base_url"] == DEFAULTS["base_url"]
        assert config["api_key"] == DEFAULTS["api_key"]
        assert config["num_ctx"] == DEFAULTS["num_ctx"]

    def test_verbose_boolean_conversion_true(self, tmp_path, monkeypatch):
        """Test that verbose value is properly converted to boolean (true)."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        config_content = """\
[ui]
verbose = true
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        assert config["verbose"] is True
        assert isinstance(config["verbose"], bool)

    def test_verbose_boolean_conversion_false(self, tmp_path, monkeypatch):
        """Test that verbose value is properly converted to boolean (false)."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        config_content = """\
[ui]
verbose = false
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        assert config["verbose"] is False
        assert isinstance(config["verbose"], bool)

    def test_empty_config_file_uses_all_defaults(self, tmp_path, monkeypatch):
        """Test that empty config file uses all default values."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        # Create empty config
        mock_config_path.write_text("")
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        # All values should be defaults
        assert config == DEFAULTS

    def test_num_ctx_integer_type(self, tmp_path, monkeypatch):
        """Test that num_ctx is loaded as integer."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        config_content = """\
[llm]
num_ctx = 32768
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()
        
        assert config["num_ctx"] == 32768
        assert isinstance(config["num_ctx"], int)
