"""Tests for plugin API version constants."""

from ayder_cli.tools.plugin_api import (
    PLUGIN_API_VERSION,
    PLUGIN_API_MIN_VERSION,
    check_api_compatibility,
)


def test_api_version_is_int():
    assert isinstance(PLUGIN_API_VERSION, int)
    assert isinstance(PLUGIN_API_MIN_VERSION, int)


def test_min_version_not_greater_than_current():
    assert PLUGIN_API_MIN_VERSION <= PLUGIN_API_VERSION


def test_compatible_version():
    result = check_api_compatibility(PLUGIN_API_VERSION)
    assert result is None  # None means compatible


def test_version_too_new():
    result = check_api_compatibility(PLUGIN_API_VERSION + 1)
    assert result is not None
    assert "Update ayder" in result


def test_version_too_old():
    # Only testable when MIN > 0 in future; for now test with 0
    result = check_api_compatibility(0)
    if PLUGIN_API_MIN_VERSION > 0:
        assert result is not None
        assert "too old" in result.lower() or "minimum" in result.lower()


def test_exact_min_version_compatible():
    result = check_api_compatibility(PLUGIN_API_MIN_VERSION)
    assert result is None
