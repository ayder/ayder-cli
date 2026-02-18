"""Tests for config.py module."""

from pathlib import Path
import pytest
from unittest import mock

from ayder_cli.core.config import (
    DEFAULTS,
    _DEFAULT_TOML,
    _PROVIDER_SECTIONS,
    CONFIG_DIR,
    CONFIG_PATH,
    Config,
    load_config,
    load_config_for_provider,
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
        assert "[openai]" in _DEFAULT_TOML
        assert "[anthropic]" in _DEFAULT_TOML
        assert "[gemini]" in _DEFAULT_TOML
        assert "[editor]" in _DEFAULT_TOML
        assert "[ui]" in _DEFAULT_TOML
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
        config = load_config()
        
        # Verify file was created
        assert mock_config_path.exists()
        
        # Verify content is written
        content = mock_config_path.read_text()
        assert "[openai]" in content
        assert "[anthropic]" in content
        assert "[gemini]" in content
        assert "[editor]" in content
        assert "[ui]" in content
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

[logging]
level = "debug"
file_enabled = false
"""
        mock_config_path.write_text(config_content)
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        # Verify custom values are loaded
        assert config.base_url == "https://api.example.com/v1"
        assert config.api_key == "my-secret-key"
        assert config.model == "gpt-4"
        assert config.num_ctx == 128000
        assert config.editor == "nano"
        assert config.verbose is True
        assert config.logging_level == "DEBUG"
        assert config.logging_file_enabled is False

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        # Verify llm values loaded
        assert config.base_url == "https://custom.api.com"
        assert config.model == "custom-model"
        # Verify defaults for missing sections
        assert config.api_key == "ollama"
        assert config.num_ctx == 65536
        assert config.editor == DEFAULTS["editor"]
        assert config.verbose == DEFAULTS["verbose"]
        assert config.logging_level is None

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        # Verify editor value loaded
        assert config.editor == "emacs"
        # Verify defaults for llm fields (openai defaults)
        assert config.base_url == DEFAULTS["openai"]["base_url"]
        assert config.api_key == DEFAULTS["openai"]["api_key"]
        assert config.model == DEFAULTS["openai"]["model"]
        assert config.num_ctx == DEFAULTS["openai"]["num_ctx"]
        assert config.verbose == DEFAULTS["verbose"]
        assert config.logging_level is None

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        # Verify ui value loaded
        assert config.verbose is True
        # Verify defaults for other sections (openai defaults)
        assert config.base_url == DEFAULTS["openai"]["base_url"]
        assert config.api_key == DEFAULTS["openai"]["api_key"]
        assert config.model == DEFAULTS["openai"]["model"]
        assert config.num_ctx == DEFAULTS["openai"]["num_ctx"]
        assert config.editor == DEFAULTS["editor"]
        assert config.logging_level is None

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        assert config.model == "only-model-defined"
        assert config.base_url == DEFAULTS["openai"]["base_url"]
        assert config.api_key == DEFAULTS["openai"]["api_key"]
        assert config.num_ctx == DEFAULTS["openai"]["num_ctx"]

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        assert config.verbose is True
        assert isinstance(config.verbose, bool)

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        assert config.verbose is False
        assert isinstance(config.verbose, bool)

    def test_empty_config_file_uses_all_defaults(self, tmp_path, monkeypatch):
        """Test that empty config file uses all default values."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()
        
        # Create empty config
        mock_config_path.write_text("")
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        # All values should be defaults (openai is default provider)
        assert isinstance(config, Config)
        assert config.base_url == DEFAULTS["openai"]["base_url"]
        assert config.api_key == DEFAULTS["openai"]["api_key"]
        assert config.model == DEFAULTS["openai"]["model"]
        assert config.num_ctx == DEFAULTS["openai"]["num_ctx"]
        assert config.editor == DEFAULTS["editor"]
        assert config.verbose == DEFAULTS["verbose"]
        assert config.logging_level is None

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
        
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)
        
        config = load_config()

        assert config.num_ctx == 32768
        assert isinstance(config.num_ctx, int)


class TestProviderField:
    """Test provider configuration field."""

    def test_default_provider_is_openai(self):
        """Default provider should be 'openai'."""
        config = Config()
        assert config.provider == "openai"

    def test_anthropic_provider_accepted(self):
        """Provider 'anthropic' is valid."""
        config = Config(provider="anthropic")
        assert config.provider == "anthropic"

    def test_gemini_provider_accepted(self):
        """Provider 'gemini' is valid."""
        config = Config(provider="gemini")
        assert config.provider == "gemini"

    def test_invalid_provider_raises(self):
        """Invalid provider value raises ValueError."""
        with pytest.raises(ValueError, match="provider must be"):
            Config(provider="invalid")

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

    def test_provider_loaded_from_toml(self, tmp_path, monkeypatch):
        """Provider field is loaded correctly from new section-based TOML config."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
provider = "anthropic"

[anthropic]
api_key = "sk-ant-test"
model = "claude-sonnet-4-5-20250929"
num_ctx = 8192
"""
        mock_config_path.write_text(config_content)

        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config()
        assert config.provider == "anthropic"
        assert config.api_key == "sk-ant-test"
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.num_ctx == 8192

    def test_openai_section_loaded(self, tmp_path, monkeypatch):
        """OpenAI provider section is loaded when active."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
provider = "openai"

[openai]
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "qwen3-coder:latest"
num_ctx = 65536
"""
        mock_config_path.write_text(config_content)

        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config()
        assert config.provider == "openai"
        assert config.base_url == "http://localhost:11434/v1"
        assert config.api_key == "ollama"
        assert config.model == "qwen3-coder:latest"

    def test_gemini_section_loaded(self, tmp_path, monkeypatch):
        """Gemini provider section is loaded when active."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
provider = "gemini"

[gemini]
api_key = "gemini-key-123"
model = "gemini-2.0-flash"
num_ctx = 65536
"""
        mock_config_path.write_text(config_content)

        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config()
        assert config.provider == "gemini"
        assert config.api_key == "gemini-key-123"
        assert config.model == "gemini-2.0-flash"

    def test_legacy_llm_section_backward_compat(self, tmp_path, monkeypatch):
        """Old [llm] section still works for backward compatibility."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
[llm]
provider = "anthropic"
api_key = "sk-ant-legacy"
model = "claude-sonnet-4-5-20250929"
"""
        mock_config_path.write_text(config_content)

        monkeypatch.setattr("ayder_cli.core.config.CONFIG_DIR", mock_config_dir)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config()
        assert config.provider == "anthropic"
        assert config.api_key == "sk-ant-legacy"

    def test_non_active_provider_sections_discarded(self):
        """Non-active provider sections are discarded, active one is merged."""
        data = {
            "provider": "anthropic",
            "openai": {"base_url": "http://localhost", "api_key": "ollama", "model": "qwen"},
            "anthropic": {"api_key": "sk-ant", "model": "claude", "num_ctx": 8192},
            "gemini": {"api_key": "gem", "model": "gemini"},
        }
        config = Config(**data)
        assert config.provider == "anthropic"
        assert config.api_key == "sk-ant"
        assert config.model == "claude"


class TestLoadConfigForProvider:
    """Test load_config_for_provider() reads real TOML with overridden provider."""

    def test_switch_to_anthropic_reads_toml_values(self, tmp_path, monkeypatch):
        """Switching to anthropic loads api_key from config.toml, not DEFAULTS."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
provider = "openai"

[openai]
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "qwen3-coder:latest"
num_ctx = 65536

[anthropic]
api_key = "sk-ant-real-key"
model = "claude-sonnet-4-5-20250929"
num_ctx = 8192
"""
        mock_config_path.write_text(config_content)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config_for_provider("anthropic")
        assert config.provider == "anthropic"
        assert config.api_key == "sk-ant-real-key"
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.num_ctx == 8192

    def test_switch_to_openai_reads_toml_values(self, tmp_path, monkeypatch):
        """Switching to openai loads base_url/api_key from config.toml."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
provider = "anthropic"

[openai]
base_url = "https://api.openai.com/v1"
api_key = "sk-openai-key"
model = "gpt-4"
num_ctx = 128000

[anthropic]
api_key = "sk-ant-key"
model = "claude-sonnet-4-5-20250929"
num_ctx = 8192
"""
        mock_config_path.write_text(config_content)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config_for_provider("openai")
        assert config.provider == "openai"
        assert config.api_key == "sk-openai-key"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4"

    def test_missing_config_file_returns_defaults(self, tmp_path, monkeypatch):
        """When config.toml doesn't exist, returns defaults for the provider."""
        mock_config_path = tmp_path / "nonexistent" / "config.toml"
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config_for_provider("anthropic")
        assert config.provider == "anthropic"

    def test_preserves_utility_sections(self, tmp_path, monkeypatch):
        """Utility sections (editor, ui, agent) are preserved across switch."""
        mock_config_dir = tmp_path / ".ayder"
        mock_config_path = mock_config_dir / "config.toml"
        mock_config_dir.mkdir()

        config_content = """\
provider = "openai"

[openai]
api_key = "ollama"
model = "qwen3-coder:latest"

[anthropic]
api_key = "sk-ant-key"
model = "claude-sonnet-4-5-20250929"

[editor]
editor = "nano"

[ui]
verbose = true

[logging]
level = "warning"
file_enabled = false

[agent]
max_iterations = 75
"""
        mock_config_path.write_text(config_content)
        monkeypatch.setattr("ayder_cli.core.config.CONFIG_PATH", mock_config_path)

        config = load_config_for_provider("anthropic")
        assert config.provider == "anthropic"
        assert config.api_key == "sk-ant-key"
        assert config.editor == "nano"
        assert config.verbose is True
        assert config.logging_level == "WARNING"
        assert config.logging_file_enabled is False
        assert config.max_iterations == 75
