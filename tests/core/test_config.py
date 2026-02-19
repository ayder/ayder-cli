"""Tests for config.py module."""

from pathlib import Path
import pytest

from ayder_cli.core.config import (
    DEFAULTS,
    _DEFAULT_TOML,
    CONFIG_DIR,
    CONFIG_PATH,
    Config,
    load_config,
)


class TestDefaultValues:
    """Test default configuration values."""

    def test_defaults_dictionary(self):
        """Test that DEFAULTS contains expected provider sections and values."""
        assert DEFAULTS["provider"] == "openai"
        assert DEFAULTS["openai"]["base_url"] == "http://localhost:11434/v1"
        assert DEFAULTS["openai"]["api_key"] == "ollama"
        assert DEFAULTS["openai"]["model"] == "qwen3-coder:latest"
        assert DEFAULTS["openai"]["num_ctx"] == 65536
        assert DEFAULTS["anthropic"]["model"] == "claude-sonnet-4-5-20250929"
        assert DEFAULTS["gemini"]["model"] == "gemini-3-flash"
        assert DEFAULTS["editor"] == "vim"
        assert DEFAULTS["verbose"] is False
        assert DEFAULTS["logging"]["file_enabled"] is True
        assert DEFAULTS["logging"]["file_path"] == ".ayder/log/ayder.log"
        assert DEFAULTS["temporal"]["enabled"] is False
        assert DEFAULTS["temporal"]["host"] == "localhost:7233"
        assert DEFAULTS["temporal"]["namespace"] == "default"

    def test_defaults_contains_all_keys(self):
        """Test that DEFAULTS has all required configuration keys."""
        required_keys = [
            "provider",
            "openai",
            "anthropic",
            "gemini",
            "editor",
            "verbose",
            "logging",
            "temporal",
        ]
        for key in required_keys:
            assert key in DEFAULTS
        # Each provider section has model and api_key
        for p in ("openai", "anthropic", "gemini"):
            assert "model" in DEFAULTS[p]
            assert "api_key" in DEFAULTS[p]

    def test_default_toml_template(self):
        """Test that _DEFAULT_TOML template contains expected sections."""
        assert 'config_version = "2.0"' in _DEFAULT_TOML
        assert "[app]" in _DEFAULT_TOML
        assert "[llm.openai]" in _DEFAULT_TOML
        assert "[llm.anthropic]" in _DEFAULT_TOML
        assert "[llm.gemini]" in _DEFAULT_TOML
        assert "[logging]" in _DEFAULT_TOML
        assert "[temporal]" in _DEFAULT_TOML
        assert "[temporal.timeouts]" in _DEFAULT_TOML
        assert "[temporal.retry]" in _DEFAULT_TOML
        assert "{provider}" in _DEFAULT_TOML
        assert "{openai_model}" in _DEFAULT_TOML
        assert "{anthropic_model}" in _DEFAULT_TOML
        assert "{gemini_model}" in _DEFAULT_TOML
        assert "{editor}" in _DEFAULT_TOML
        assert "{verbose_str}" in _DEFAULT_TOML
        assert "{logging_file_enabled}" in _DEFAULT_TOML
        assert "{temporal_enabled}" in _DEFAULT_TOML
        assert "{temporal_host}" in _DEFAULT_TOML

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        # Ensure file doesn't exist
        assert not mock_config_path.exists()
        
        # Load config
        load_config()
        
        # Verify file was created
        assert mock_config_path.exists()
        
        # Verify content is written
        content = mock_config_path.read_text()
        assert 'config_version = "2.0"' in content
        assert "[app]" in content
        assert "[llm.openai]" in content
        assert "[llm.anthropic]" in content
        assert "[llm.gemini]" in content
        assert "[logging]" in content
        assert "[temporal]" in content
        assert "[temporal.timeouts]" in content
        assert "[temporal.retry]" in content

    def test_default_values_returned_on_first_run(self, tmp_path, monkeypatch):
        """Test that default values are returned when creating new config."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"

        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config()

        # Verify defaults are returned (active provider is openai)
        assert isinstance(config, Config)
        assert config.base_url == DEFAULTS["openai"]["base_url"]
        assert config.api_key == DEFAULTS["openai"]["api_key"]
        assert config.model == DEFAULTS["openai"]["model"]
        assert config.num_ctx == DEFAULTS["openai"]["num_ctx"]
        assert config.editor == DEFAULTS["editor"]
        assert config.verbose == DEFAULTS["verbose"]
        assert config.logging_level is None

    def test_config_directory_creation(self, tmp_path, monkeypatch):
        """Test that config directory is created if it doesn't exist."""
        mock_config_dir = tmp_path / ".ayder" / "nested" / "path"
        mock_config_path = mock_config_dir / "config.toml"
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        load_config()
        
        content = mock_config_path.read_text()

        # Verify top-level provider
        assert 'provider = "openai"' in content
        # Verify openai section values
        assert 'base_url = "http://localhost:11434/v1"' in content
        assert 'api_key = "ollama"' in content
        assert 'model = "qwen3-coder:latest"' in content
        assert "num_ctx = 65536" in content
        # Verify anthropic section values
        assert 'model = "claude-sonnet-4-5-20250929"' in content
        # Verify gemini section values
        assert 'model = "gemini-3-flash"' in content
        # Verify utility sections
        assert 'editor = "vim"' in content
        assert "verbose = false" in content
        assert "file_enabled = true" in content
        assert "enabled = false" in content
        assert "host = \"localhost:7233\"" in content

    def test_temporal_config_loading(self, tmp_path, monkeypatch):
        """Test loading temporal section from existing config file."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
    [temporal]
    enabled = true
    host = "temporal.example.local:7233"
    namespace = "prod"
    metadata_dir = ".runtime/temporal"

    [temporal.timeouts]
    workflow_schedule_to_close_seconds = 3600
    activity_start_to_close_seconds = 600
    activity_heartbeat_seconds = 20

    [temporal.retry]
    initial_interval_seconds = 2
    backoff_coefficient = 2.5
    maximum_interval_seconds = 45
    maximum_attempts = 4
    """
        mock_config_path.write_text(config_content)

        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config()

        assert config.temporal.enabled is True
        assert config.temporal.host == "temporal.example.local:7233"
        assert config.temporal.namespace == "prod"
        assert config.temporal.metadata_dir == ".runtime/temporal"
        assert config.temporal.timeouts.workflow_schedule_to_close_seconds == 3600
        assert config.temporal.timeouts.activity_start_to_close_seconds == 600
        assert config.temporal.timeouts.activity_heartbeat_seconds == 20
        assert config.temporal.retry.initial_interval_seconds == 2
        assert config.temporal.retry.backoff_coefficient == 2.5
        assert config.temporal.retry.maximum_interval_seconds == 45
        assert config.temporal.retry.maximum_attempts == 4


class TestProviderField:
    """Test provider configuration field."""

    def test_default_provider_is_openai(self):
        """Default provider should be 'openai'."""
        config = Config()
        assert config.provider == "openai"

    def test_invalid_provider_raises(self):
        """Invalid provider value raises ValueError."""
        with pytest.raises(ValueError, match="provider must be"):
            Config(provider="")

    def test_base_url_none_is_valid(self):
        """base_url=None is valid (for Anthropic provider)."""
        config = Config(base_url=None, provider="anthropic")
        assert config.base_url is None

    def test_provider_in_defaults(self):
        """DEFAULTS dict includes provider key."""
        assert "provider" in DEFAULTS
        assert DEFAULTS["provider"] == "openai"

    def test_provider_in_toml_template(self):
        """Default TOML template includes provider field."""
        assert "{provider}" in _DEFAULT_TOML

    def test_non_active_provider_sections_discarded(self):
        """Active llm profile is merged from v2 [llm.<name>] sections."""
        data = {
            "app": {"provider": "anthropic"},
            "llm": {
                "openai": {
                    "driver": "openai",
                    "base_url": "http://localhost",
                    "api_key": "ollama",
                    "model": "qwen",
                },
                "anthropic": {
                    "driver": "anthropic",
                    "api_key": "sk-ant",
                    "model": "claude",
                    "num_ctx": 8192,
                },
                "gemini": {
                    "driver": "google",
                    "api_key": "gem",
                    "model": "gemini",
                },
            },
        }
        config = Config(**data)
        assert config.provider == "anthropic"
        assert config.api_key == "sk-ant"
        assert config.model == "claude"
