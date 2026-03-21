"""Tests for GitHub URL parsing and download logic."""

from unittest.mock import patch

import pytest

from ayder_cli.tools.plugin_github import (
    GitHubPluginSource,
    download_plugin,
    parse_github_url,
)
from ayder_cli.tools.plugin_manager import PluginError


class TestParseGitHubUrl:
    def test_repo_with_subdirectory(self):
        result = parse_github_url(
            "https://github.com/ayder/ayder-plugins/dbs-tools"
        )
        assert result.owner == "ayder"
        assert result.repo == "ayder-plugins"
        assert result.path == "dbs-tools"

    def test_repo_with_nested_subdirectory(self):
        result = parse_github_url(
            "https://github.com/ayder/ayder-plugins/tools/dbs-tools"
        )
        assert result.owner == "ayder"
        assert result.repo == "ayder-plugins"
        assert result.path == "tools/dbs-tools"

    def test_repo_root_plugin(self):
        result = parse_github_url(
            "https://github.com/user/my-single-plugin"
        )
        assert result.owner == "user"
        assert result.repo == "my-single-plugin"
        assert result.path == ""

    def test_tree_url_stripped(self):
        result = parse_github_url(
            "https://github.com/ayder/ayder-plugins/tree/main/dbs-tools"
        )
        assert result.owner == "ayder"
        assert result.repo == "ayder-plugins"
        assert result.path == "dbs-tools"

    def test_blob_url_stripped(self):
        result = parse_github_url(
            "https://github.com/ayder/ayder-plugins/blob/v2/tools/dbs"
        )
        assert result.owner == "ayder"
        assert result.repo == "ayder-plugins"
        assert result.path == "tools/dbs"

    def test_invalid_url_not_github(self):
        with pytest.raises(ValueError, match="GitHub"):
            parse_github_url("https://gitlab.com/user/repo/path")

    def test_invalid_url_too_short(self):
        with pytest.raises(ValueError, match="owner.*repo"):
            parse_github_url("https://github.com/user")


def test_download_plugin_api_returns_list(tmp_path):
    source = GitHubPluginSource(owner="user", repo="repo", path="")
    with patch(
        "ayder_cli.tools.plugin_github._github_api_request",
        return_value=["unexpected_list"],
    ):
        with pytest.raises(PluginError, match="Unexpected response type"):
            download_plugin(source, tmp_path)
