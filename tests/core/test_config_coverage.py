"""Additional tests for config.py to reach 100% coverage.

This module tests the remaining uncovered lines in config.py:
- Line 49: validate_num_ctx raises ValueError for non-positive values
- Line 57: validate_base_url raises ValueError for invalid URL scheme
"""

import pytest
from pydantic import ValidationError

from ayder_cli.core.config import Config, load_config


class TestConfigValidationNumCtx:
    """Tests for num_ctx validation - Line 49."""

    def test_num_ctx_zero_raises_error(self):
        """Test that num_ctx=0 raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config(num_ctx=0)
        assert "num_ctx must be positive" in str(exc_info.value)

    def test_num_ctx_negative_raises_error(self):
        """Test that negative num_ctx raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config(num_ctx=-1)
        assert "num_ctx must be positive" in str(exc_info.value)

    def test_num_ctx_negative_large_raises_error(self):
        """Test that large negative num_ctx raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config(num_ctx=-65536)
        assert "num_ctx must be positive" in str(exc_info.value)

    def test_num_ctx_positive_passes(self):
        """Test that positive num_ctx is accepted."""
        config = Config(num_ctx=1)
        assert config.num_ctx == 1

    def test_num_ctx_one_passes(self):
        """Test that num_ctx=1 is accepted."""
        config = Config(num_ctx=1)
        assert config.num_ctx == 1


class TestConfigValidationBaseUrl:
    """Tests for base_url validation - Line 57."""

    def test_base_url_without_scheme_raises_error(self):
        """Test that base_url without http/https raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config(base_url="localhost:11434/v1")
        assert "base_url must start with http:// or https://" in str(exc_info.value)

    def test_base_url_ftp_scheme_raises_error(self):
        """Test that ftp:// scheme raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config(base_url="ftp://example.com/v1")
        assert "base_url must start with http:// or https://" in str(exc_info.value)

    def test_base_url_file_scheme_raises_error(self):
        """Test that file:// scheme raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config(base_url="file:///path/to/api")
        assert "base_url must start with http:// or https://" in str(exc_info.value)

    def test_base_url_empty_raises_error(self):
        """Test that empty base_url raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Config(base_url="")
        assert "base_url must start with http:// or https://" in str(exc_info.value)

    def test_base_url_http_passes(self):
        """Test that http:// scheme is accepted."""
        config = Config(base_url="http://localhost:11434/v1")
        assert config.base_url == "http://localhost:11434/v1"

    def test_base_url_https_passes(self):
        """Test that https:// scheme is accepted."""
        config = Config(base_url="https://api.example.com/v1")
        assert config.base_url == "https://api.example.com/v1"

    def test_base_url_http_localhost_with_port(self):
        """Test http:// with localhost and port."""
        config = Config(base_url="http://127.0.0.1:8080/api")
        assert config.base_url == "http://127.0.0.1:8080/api"


class TestConfigCombinedValidation:
    """Tests for combined validation scenarios."""

    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are reported."""
        with pytest.raises(ValidationError) as exc_info:
            Config(num_ctx=-100, base_url="invalid-url")
        error_msg = str(exc_info.value)
        # Should have both validation errors
        assert "num_ctx must be positive" in error_msg
        assert "base_url must start with http:// or https://" in error_msg

    def test_valid_config_with_all_custom_values(self):
        """Test creating config with all valid custom values."""
        config = Config(
            base_url="https://api.openai.com/v1",
            api_key="sk-test-key",
            model="gpt-4",
            num_ctx=8192,
            editor="code",
            verbose=True
        )
        assert config.base_url == "https://api.openai.com/v1"
        assert config.api_key == "sk-test-key"
        assert config.model == "gpt-4"
        assert config.num_ctx == 8192
        assert config.editor == "code"
        assert config.verbose is True


class TestConfigValidationMaxIterations:
    """Tests for max_iterations validation."""

    def test_default_value(self):
        cfg = Config()
        assert cfg.max_iterations == 50

    def test_valid_value(self):
        cfg = Config(max_iterations=25)
        assert cfg.max_iterations == 25

    def test_zero_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Config(max_iterations=0)
        assert "max_iterations must be between 1 and 100" in str(exc_info.value)

    def test_negative_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Config(max_iterations=-1)
        assert "max_iterations must be between 1 and 100" in str(exc_info.value)

    def test_too_large_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Config(max_iterations=101)
        assert "max_iterations must be between 1 and 100" in str(exc_info.value)

    def test_boundary_min(self):
        cfg = Config(max_iterations=1)
        assert cfg.max_iterations == 1

    def test_boundary_max(self):
        cfg = Config(max_iterations=100)
        assert cfg.max_iterations == 100

    def test_agent_section_flattened_from_toml(self):
        """Test that [agent] section is properly flattened."""
        data = {"agent": {"max_iterations": 30}}
        cfg = Config(**data)
        assert cfg.max_iterations == 30
