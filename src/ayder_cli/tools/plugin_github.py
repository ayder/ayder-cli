"""GitHub URL parsing and plugin download via GitHub API."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitHubPluginSource:
    """Parsed GitHub plugin source."""

    owner: str
    repo: str
    path: str  # empty string for repo root


def parse_github_url(url: str) -> GitHubPluginSource:
    """Parse a GitHub URL into owner, repo, and subdirectory path.

    Algorithm: first two path segments after github.com are always
    owner/repo. Everything after is the subdirectory path.
    Strips /tree/<branch>/ and /blob/<branch>/ from the path.
    """
    parsed = urlparse(url)
    if not parsed.hostname or "github.com" not in parsed.hostname:
        raise ValueError(f"Not a GitHub URL: {url}")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(
            f"GitHub URL must include at least owner/repo: {url}"
        )

    owner = parts[0]
    repo = parts[1]
    rest = parts[2:]

    # Strip /tree/<branch>/ or /blob/<branch>/
    if len(rest) >= 2 and rest[0] in ("tree", "blob"):
        rest = rest[2:]  # skip "tree"/"blob" and branch name

    path = "/".join(rest)
    return GitHubPluginSource(owner=owner, repo=repo, path=path)


def _github_api_request(endpoint: str) -> dict | list:
    """Make an authenticated GitHub API request."""
    url = f"https://api.github.com{endpoint}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(f"Plugin not found at {url}") from e
        if e.code == 403:
            raise PermissionError(
                "GitHub API rate limited. Set GITHUB_TOKEN for higher limits."
            ) from e
        raise


def download_plugin(source: GitHubPluginSource, dest_dir: Path) -> str:
    """Download a plugin from GitHub to dest_dir. Returns commit SHA."""
    from ayder_cli.tools.plugin_manager import PluginError

    # 1. Get default branch
    repo_info = _github_api_request(f"/repos/{source.owner}/{source.repo}")
    if not isinstance(repo_info, dict):
        raise PluginError(
            f"Unexpected response type from GitHub API: {type(repo_info)}"
        )
    branch = repo_info["default_branch"]

    # 2. Get latest commit SHA
    commit_info = _github_api_request(
        f"/repos/{source.owner}/{source.repo}/commits/{branch}"
    )
    if not isinstance(commit_info, dict):
        raise PluginError(
            f"Unexpected response type from GitHub API: {type(commit_info)}"
        )
    commit_sha = commit_info["sha"]
    logger.info(f"Downloading '{source.repo}' at {commit_sha[:7]}")

    # 3. Download directory contents recursively
    content_path = source.path or ""
    _download_directory(source, branch, content_path, dest_dir)

    return commit_sha


def _download_directory(
    source: GitHubPluginSource,
    branch: str,
    path: str,
    dest_dir: Path,
) -> None:
    """Recursively download a directory from GitHub."""
    endpoint = f"/repos/{source.owner}/{source.repo}/contents/{path}"
    if branch:
        endpoint += f"?ref={branch}"

    items = _github_api_request(endpoint)
    if not isinstance(items, list):
        # Single file, not a directory
        items = [items]

    dest_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        name = item["name"]
        if item["type"] == "file":
            _download_file(item["download_url"], dest_dir / name)
        elif item["type"] == "dir":
            _download_directory(source, branch, item["path"], dest_dir / name)


def _download_file(url: str, dest: Path) -> None:
    """Download a single file from a URL."""
    logger.debug(f"Downloading {dest.name}")
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
    except HTTPError as e:
        raise FileNotFoundError(f"Failed to download file at {url}") from e
