"""Additional tests for config.py to reach 100% coverage.

This module tests the remaining uncovered lines in config.py:
- Line 49: validate_num_ctx raises ValueError for non-positive values
- Line 57: validate_base_url raises ValueError for invalid URL scheme
"""

import pytest
from pydantic import ValidationError

from ayder_cli.core.config import Config


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


class TestConfigValidationLoggingLevel:
    """Tests for logging_level normalization and validation."""

    def test_logging_level_defaults_to_none(self):
        cfg = Config()
        assert cfg.logging_level is None

    def test_logging_level_normalized_to_upper(self):
        cfg = Config(logging_level="debug")
        assert cfg.logging_level == "DEBUG"

    def test_logging_level_blank_becomes_none(self):
        cfg = Config(logging_level="   ")
        assert cfg.logging_level is None

    def test_logging_level_invalid_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Config(logging_level="TRACE")
        assert "logging_level must be one of NONE, ERROR, WARNING, INFO, DEBUG" in str(
            exc_info.value
        )


class TestConfigValidationTemporal:
    """Tests for temporal nested validation rules."""

    def test_temporal_timeout_non_positive_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Config(
                temporal={
                    "timeouts": {
                        "workflow_schedule_to_close_seconds": 0,
                    }
                }
            )
        assert "temporal timeout values must be positive" in str(exc_info.value)

    def test_temporal_retry_backoff_invalid_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Config(
                temporal={
                    "retry": {
                        "backoff_coefficient": 0.5,
                    }
                }
            )
        assert "backoff_coefficient must be >= 1.0" in str(exc_info.value)

    def test_temporal_required_strings_non_empty(self):
        with pytest.raises(ValidationError) as exc_info:
            Config(temporal={"host": "  "})
        assert "temporal host/namespace/metadata_dir must be non-empty" in str(
            exc_info.value
        )


class TestConfigMaxHistoryDefault:
    """H2: max_history_messages default must be 30 directly, no model_validator magic."""

    def test_default_is_30_not_minus_one(self):
        """H2: The field default itself is 30, not -1 converted by a model_validator."""
        from ayder_cli.core.config import Config as C
        default_val = C.model_fields["max_history_messages"].default
        assert default_val == 30, (
            f"max_history_messages default is {default_val!r}, expected 30 — "
            "the sentinel -1 pattern should be eliminated"
        )

    def test_config_default_resolves_to_30(self):
        """H2: Config() without specifying max_history_messages gives 30."""
        config = Config()
        assert config.max_history_messages == 30
