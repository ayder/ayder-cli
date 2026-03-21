# External Plugin System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract venv, temporal, python, and dbs tool plugins to an external repo (`ayder-plugins`) and add CLI commands to install/uninstall/update/list plugins from GitHub or local paths.

**Architecture:** Two-phase plugin loading — global plugins discovered at import time, project-local plugins loaded at runtime via `register_dynamic_tool()`. Plugins are downloaded via GitHub API or copied from local directories. Each plugin has a `plugin.toml` manifest declaring name, version, API compatibility, and dependencies.

**Tech Stack:** Python 3.12, stdlib `urllib.request` for GitHub API, `tomllib` (stdlib 3.11+) for TOML parsing, Textual for TUI multi-select widget.

**Spec:** `docs/superpowers/specs/2026-03-21-external-plugin-system-design.md`

---

## File Structure

### New Files (ayder-cli)

| File | Responsibility |
|------|---------------|
| `src/ayder_cli/tools/plugin_api.py` | API version constants |
| `src/ayder_cli/tools/plugin_manager.py` | Install, uninstall, update, list, load plugins |
| `src/ayder_cli/tools/plugin_github.py` | GitHub URL parsing + API download |
| `tests/tools/test_plugin_api.py` | API version compatibility tests |
| `tests/tools/test_plugin_manager.py` | Plugin manager unit tests |
| `tests/tools/test_plugin_github.py` | URL parsing + download tests |
| `tests/tools/test_plugin_loading.py` | Integration test for plugin discovery |
| `tests/tui/test_multi_select_screen.py` | Multi-select widget tests |

### Modified Files (ayder-cli)

| File | Change |
|------|--------|
| `src/ayder_cli/tools/definition.py` | Add `_discover_global_plugins()`, merge into `TOOL_DEFINITIONS` |
| `src/ayder_cli/tools/registry.py` | `create_default_registry()` loads project plugins, uses `_plugin_handlers` |
| `src/ayder_cli/cli.py` | Add plugin subcommands, conditional `--temporal-task-queue` |
| `src/ayder_cli/cli_runner.py` | Refactor `_run_temporal_queue_cli()` for dynamic temporal import |
| `src/ayder_cli/tui/screens.py` | Add `CLIMultiSelectScreen` class |
| `src/ayder_cli/tui/commands.py` | `handle_plugin()` uses `CLIMultiSelectScreen` |

### New Files (ayder-plugins repo)

| File | Responsibility |
|------|---------------|
| `dbs-tools/plugin.toml` | Plugin manifest |
| `dbs-tools/dbs_tool_definitions.py` | Tool definitions (adapted from builtin) |
| `dbs-tools/dbs_tool.py` | Tool implementation (copied from builtin) |
| `venv-tools/plugin.toml` | Plugin manifest |
| `venv-tools/venv_definitions.py` | Tool definitions |
| `venv-tools/venv.py` | Tool implementation |
| `python-tools/plugin.toml` | Plugin manifest |
| `python-tools/python_editor_definitions.py` | Tool definitions |
| `python-tools/python_editor.py` | Tool implementation |
| `temporal-tools/plugin.toml` | Plugin manifest |
| `temporal-tools/temporal_definitions.py` | Tool definitions |
| `temporal-tools/temporal.py` | Tool wrapper |
| `temporal-tools/temporal_workflow_service.py` | Service layer (refactored imports) |
| `temporal-tools/temporal_client.py` | Client adapter (refactored imports) |
| `temporal-tools/temporal_worker.py` | Worker runtime (refactored imports) |
| `temporal-tools/temporal_contract.py` | Activity contract (no changes) |
| `temporal-tools/temporal_metadata.py` | Metadata persistence (no changes) |

---

## Task 1: Plugin API Version Constants

**Files:**
- Create: `src/ayder_cli/tools/plugin_api.py`
- Test: `tests/tools/test_plugin_api.py`

- [ ] **Step 1: Write the test**

```python
# tests/tools/test_plugin_api.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_plugin_api.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/ayder_cli/tools/plugin_api.py
"""Plugin API version constants and compatibility checks."""

PLUGIN_API_VERSION: int = 1
PLUGIN_API_MIN_VERSION: int = 1


def check_api_compatibility(plugin_api_version: int) -> str | None:
    """Check if a plugin's API version is compatible.

    Returns None if compatible, or an error message string if not.
    """
    if plugin_api_version > PLUGIN_API_VERSION:
        return (
            f"Plugin requires API v{plugin_api_version}, "
            f"but ayder supports v{PLUGIN_API_VERSION}. Update ayder."
        )
    if plugin_api_version < PLUGIN_API_MIN_VERSION:
        return (
            f"Plugin targets API v{plugin_api_version}, "
            f"minimum supported is v{PLUGIN_API_MIN_VERSION}. Update the plugin."
        )
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_plugin_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/plugin_api.py tests/tools/test_plugin_api.py
git commit -m "feat(plugins): add plugin API version constants and compatibility check"
```

---

## Task 2: Plugin TOML Parser and Validator

**Files:**
- Create: `src/ayder_cli/tools/plugin_manager.py` (first part — TOML parsing)
- Test: `tests/tools/test_plugin_manager.py` (first part)

- [ ] **Step 1: Write the test**

```python
# tests/tools/test_plugin_manager.py
"""Tests for plugin manager — TOML parsing and validation."""

import os
import tempfile
from pathlib import Path

import pytest

from ayder_cli.tools.plugin_manager import (
    PluginManifest,
    parse_plugin_toml,
    PluginError,
)


@pytest.fixture
def plugin_dir(tmp_path):
    """Create a minimal valid plugin directory."""
    toml_content = """\
[plugin]
name = "test-plugin"
version = "1.0.0"
api_version = 1
description = "A test plugin"
author = "test"

[tools]
definitions = "test_definitions.py"
"""
    (tmp_path / "plugin.toml").write_text(toml_content)
    return tmp_path


def test_parse_valid_plugin_toml(plugin_dir):
    manifest = parse_plugin_toml(plugin_dir)
    assert manifest.name == "test-plugin"
    assert manifest.version == "1.0.0"
    assert manifest.api_version == 1
    assert manifest.description == "A test plugin"
    assert manifest.definitions_file == "test_definitions.py"
    assert manifest.dependencies == {}


def test_parse_with_dependencies(tmp_path):
    toml_content = """\
[plugin]
name = "dep-plugin"
version = "0.1.0"
api_version = 1
description = "Plugin with deps"
author = "test"

[dependencies]
libcst = ">=1.0"
requests = ">=2.28"

[tools]
definitions = "defs.py"
"""
    (tmp_path / "plugin.toml").write_text(toml_content)
    manifest = parse_plugin_toml(tmp_path)
    assert manifest.dependencies == {"libcst": ">=1.0", "requests": ">=2.28"}


def test_parse_missing_toml(tmp_path):
    with pytest.raises(PluginError, match="plugin.toml not found"):
        parse_plugin_toml(tmp_path)


def test_parse_missing_required_field(tmp_path):
    toml_content = """\
[plugin]
name = "bad-plugin"
"""
    (tmp_path / "plugin.toml").write_text(toml_content)
    with pytest.raises(PluginError, match="version"):
        parse_plugin_toml(tmp_path)


def test_parse_api_version_not_int(tmp_path):
    toml_content = """\
[plugin]
name = "bad-api"
version = "1.0.0"
api_version = "1"
description = "Bad api version type"
author = "test"

[tools]
definitions = "defs.py"
"""
    (tmp_path / "plugin.toml").write_text(toml_content)
    with pytest.raises(PluginError, match="api_version.*integer"):
        parse_plugin_toml(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_plugin_manager.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/ayder_cli/tools/plugin_manager.py
"""Plugin manager — install, uninstall, update, list, and load external plugins."""

from __future__ import annotations

import json
import logging
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ayder_cli.tools.plugin_api import check_api_compatibility

logger = logging.getLogger(__name__)

# Plugin directories
GLOBAL_PLUGINS_DIR = Path.home() / ".ayder" / "plugins"
PROJECT_PLUGINS_DIR_NAME = ".ayder/plugins"


class PluginError(Exception):
    """Raised for plugin-related errors."""


@dataclass(frozen=True)
class PluginManifest:
    """Parsed plugin.toml manifest."""

    name: str
    version: str
    api_version: int
    description: str
    author: str
    definitions_file: str
    dependencies: dict[str, str] = field(default_factory=dict)
    source_dir: Path = field(default=Path("."))


def parse_plugin_toml(plugin_dir: Path) -> PluginManifest:
    """Parse and validate a plugin.toml file."""
    toml_path = plugin_dir / "plugin.toml"
    if not toml_path.exists():
        raise PluginError(f"plugin.toml not found in {plugin_dir}")

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    plugin = data.get("plugin", {})

    # Validate required fields
    required = ("name", "version", "api_version", "description", "author")
    for field_name in required:
        if field_name not in plugin:
            raise PluginError(
                f"Missing required field '{field_name}' in plugin.toml"
            )

    if not isinstance(plugin["api_version"], int):
        raise PluginError(
            "api_version must be an integer in plugin.toml, "
            f"got {type(plugin['api_version']).__name__}"
        )

    tools = data.get("tools", {})
    definitions_file = tools.get("definitions")
    if not definitions_file:
        raise PluginError("Missing [tools] definitions in plugin.toml")

    dependencies = {
        str(k): str(v) for k, v in data.get("dependencies", {}).items()
    }

    return PluginManifest(
        name=plugin["name"],
        version=plugin["version"],
        api_version=plugin["api_version"],
        description=plugin["description"],
        author=plugin["author"],
        definitions_file=definitions_file,
        dependencies=dependencies,
        source_dir=plugin_dir,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_plugin_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/plugin_manager.py tests/tools/test_plugin_manager.py
git commit -m "feat(plugins): add plugin.toml parser and validator"
```

---

## Task 3: Plugin Install and Uninstall (Local Path)

**Files:**
- Modify: `src/ayder_cli/tools/plugin_manager.py`
- Test: `tests/tools/test_plugin_manager.py` (append)

- [ ] **Step 1: Write the test**

Append to `tests/tools/test_plugin_manager.py`:

```python
from ayder_cli.tools.plugin_manager import (
    install_plugin_from_local,
    uninstall_plugin,
    list_installed_plugins,
    read_plugins_json,
)


@pytest.fixture
def global_plugins_dir(tmp_path, monkeypatch):
    """Override global plugins directory to temp."""
    plugins_dir = tmp_path / "global_plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr(
        "ayder_cli.tools.plugin_manager.GLOBAL_PLUGINS_DIR", plugins_dir
    )
    return plugins_dir


@pytest.fixture
def source_plugin(tmp_path):
    """Create a source plugin directory to install from."""
    src = tmp_path / "source" / "test-plugin"
    src.mkdir(parents=True)
    (src / "plugin.toml").write_text("""\
[plugin]
name = "test-plugin"
version = "1.0.0"
api_version = 1
description = "A test plugin"
author = "test"

[tools]
definitions = "test_definitions.py"
""")
    (src / "test_definitions.py").write_text("TOOL_DEFINITIONS = ()")
    (src / "test_impl.py").write_text("pass")
    return src


def test_install_from_local(global_plugins_dir, source_plugin):
    install_plugin_from_local(source_plugin, project_local=False)
    installed = global_plugins_dir / "test-plugin"
    assert installed.exists()
    assert (installed / "plugin.toml").exists()
    assert (installed / "test_definitions.py").exists()
    plugins = read_plugins_json(global_plugins_dir)
    assert "test-plugin" in plugins["plugins"]
    assert plugins["plugins"]["test-plugin"]["source_type"] == "local"


def test_install_duplicate_fails(global_plugins_dir, source_plugin):
    install_plugin_from_local(source_plugin, project_local=False)
    with pytest.raises(PluginError, match="already installed"):
        install_plugin_from_local(source_plugin, project_local=False)


def test_install_force_overwrites(global_plugins_dir, source_plugin):
    install_plugin_from_local(source_plugin, project_local=False)
    install_plugin_from_local(source_plugin, project_local=False, force=True)
    assert (global_plugins_dir / "test-plugin").exists()


def test_uninstall_plugin(global_plugins_dir, source_plugin):
    install_plugin_from_local(source_plugin, project_local=False)
    uninstall_plugin("test-plugin")
    assert not (global_plugins_dir / "test-plugin").exists()
    plugins = read_plugins_json(global_plugins_dir)
    assert "test-plugin" not in plugins["plugins"]


def test_uninstall_nonexistent(global_plugins_dir):
    with pytest.raises(PluginError, match="not found"):
        uninstall_plugin("nonexistent")


def test_list_installed_plugins(global_plugins_dir, source_plugin):
    assert list_installed_plugins() == []
    install_plugin_from_local(source_plugin, project_local=False)
    plugins = list_installed_plugins()
    assert len(plugins) == 1
    assert plugins[0]["name"] == "test-plugin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_plugin_manager.py -v -k "install or uninstall or list_installed"`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

Add to `src/ayder_cli/tools/plugin_manager.py`:

```python
def read_plugins_json(plugins_dir: Path) -> dict[str, Any]:
    """Read the plugins.json manifest from a plugins directory."""
    manifest_path = plugins_dir / "plugins.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return {"plugins": {}}


def _write_plugins_json(plugins_dir: Path, data: dict[str, Any]) -> None:
    """Write the plugins.json manifest."""
    plugins_dir.mkdir(parents=True, exist_ok=True)
    (plugins_dir / "plugins.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def _get_plugins_dir(project_local: bool, project_path: Path | None = None) -> Path:
    """Get the appropriate plugins directory."""
    if project_local:
        if project_path is None:
            raise PluginError("project_path required for project-local install")
        return project_path / PROJECT_PLUGINS_DIR_NAME
    return GLOBAL_PLUGINS_DIR


def install_plugin_from_local(
    source_dir: Path,
    project_local: bool = False,
    project_path: Path | None = None,
    force: bool = False,
) -> PluginManifest:
    """Install a plugin from a local directory by copying."""
    manifest = parse_plugin_toml(source_dir)

    # Check API compatibility
    err = check_api_compatibility(manifest.api_version)
    if err:
        raise PluginError(err)

    plugins_dir = _get_plugins_dir(project_local, project_path)
    target_dir = plugins_dir / manifest.name

    if target_dir.exists() and not force:
        raise PluginError(
            f"Plugin '{manifest.name}' already installed at {target_dir}. "
            "Use --force to overwrite."
        )

    # Copy plugin files
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)

    # Update plugins.json
    from datetime import datetime, timezone

    data = read_plugins_json(plugins_dir)
    data["plugins"][manifest.name] = {
        "version": manifest.version,
        "api_version": manifest.api_version,
        "source": str(source_dir.resolve()),
        "source_type": "local",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": None,
    }
    _write_plugins_json(plugins_dir, data)

    logger.info(f"Installed plugin '{manifest.name}' v{manifest.version}")
    return manifest


def uninstall_plugin(
    name: str,
    project_path: Path | None = None,
) -> None:
    """Uninstall a plugin by name."""
    # Search global first, then project-local
    for plugins_dir in _search_plugin_dirs(project_path):
        target_dir = plugins_dir / name
        if target_dir.exists():
            shutil.rmtree(target_dir)
            data = read_plugins_json(plugins_dir)
            data["plugins"].pop(name, None)
            _write_plugins_json(plugins_dir, data)
            logger.info(f"Uninstalled plugin '{name}'")
            return
    raise PluginError(f"Plugin '{name}' not found")


def _search_plugin_dirs(project_path: Path | None = None) -> list[Path]:
    """Return plugin directories to search, global first."""
    dirs = [GLOBAL_PLUGINS_DIR]
    if project_path:
        dirs.append(project_path / PROJECT_PLUGINS_DIR_NAME)
    return dirs


def list_installed_plugins(
    project_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List all installed plugins across global and project-local."""
    result = []
    for plugins_dir in _search_plugin_dirs(project_path):
        data = read_plugins_json(plugins_dir)
        scope = "project" if PROJECT_PLUGINS_DIR_NAME in str(plugins_dir) else "global"
        for name, info in data.get("plugins", {}).items():
            result.append({"name": name, "scope": scope, **info})
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_plugin_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/plugin_manager.py tests/tools/test_plugin_manager.py
git commit -m "feat(plugins): add local install, uninstall, and list operations"
```

---

## Task 4: GitHub URL Parser and Downloader

**Files:**
- Create: `src/ayder_cli/tools/plugin_github.py`
- Test: `tests/tools/test_plugin_github.py`

- [ ] **Step 1: Write the test**

```python
# tests/tools/test_plugin_github.py
"""Tests for GitHub URL parsing and download logic."""

import pytest

from ayder_cli.tools.plugin_github import parse_github_url, GitHubPluginSource


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_plugin_github.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/ayder_cli/tools/plugin_github.py
"""GitHub URL parsing and plugin download via GitHub API."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
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
    from urllib.parse import urlparse

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


def _github_api_request(endpoint: str) -> dict:
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
    # 1. Get default branch
    repo_info = _github_api_request(f"/repos/{source.owner}/{source.repo}")
    branch = repo_info["default_branch"]

    # 2. Get latest commit SHA
    commit_info = _github_api_request(
        f"/repos/{source.owner}/{source.repo}/commits/{branch}"
    )
    commit_sha = commit_info["sha"]

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
    headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_plugin_github.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/plugin_github.py tests/tools/test_plugin_github.py
git commit -m "feat(plugins): add GitHub URL parser and download mechanism"
```

---

## Task 5: GitHub Install + Update Plugin

**Files:**
- Modify: `src/ayder_cli/tools/plugin_manager.py`
- Test: `tests/tools/test_plugin_manager.py` (append)

- [ ] **Step 1: Write the test**

Append to `tests/tools/test_plugin_manager.py`:

```python
from unittest.mock import patch, MagicMock
from ayder_cli.tools.plugin_manager import (
    install_plugin_from_github,
    update_plugin,
    detect_source_type,
)


def test_detect_source_type_github():
    assert detect_source_type("https://github.com/user/repo/plugin") == "github"


def test_detect_source_type_local():
    assert detect_source_type("/tmp/my-plugin") == "local"
    assert detect_source_type("../relative/path") == "local"


@patch("ayder_cli.tools.plugin_manager.download_plugin")
@patch("ayder_cli.tools.plugin_manager.parse_github_url")
def test_install_from_github(mock_parse, mock_download, global_plugins_dir, tmp_path):
    from ayder_cli.tools.plugin_github import GitHubPluginSource

    mock_parse.return_value = GitHubPluginSource(
        owner="ayder", repo="ayder-plugins", path="test-plugin"
    )

    # download_plugin should copy files to dest_dir
    def fake_download(source, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "plugin.toml").write_text("""\
[plugin]
name = "test-plugin"
version = "1.0.0"
api_version = 1
description = "Test"
author = "test"

[tools]
definitions = "test_defs.py"
""")
        (dest_dir / "test_defs.py").write_text("TOOL_DEFINITIONS = ()")
        return "abc123"

    mock_download.side_effect = fake_download

    install_plugin_from_github(
        "https://github.com/ayder/ayder-plugins/test-plugin",
        project_local=False,
    )
    assert (global_plugins_dir / "test-plugin" / "plugin.toml").exists()
    plugins = read_plugins_json(global_plugins_dir)
    assert plugins["plugins"]["test-plugin"]["source_type"] == "github"
    assert plugins["plugins"]["test-plugin"]["commit_sha"] == "abc123"


def test_update_local_plugin(global_plugins_dir, source_plugin):
    install_plugin_from_local(source_plugin, project_local=False)
    # Modify source
    (source_plugin / "new_file.py").write_text("# new")
    update_plugin("test-plugin")
    assert (global_plugins_dir / "test-plugin" / "new_file.py").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_plugin_manager.py -v -k "github or update or detect"`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

Add to `src/ayder_cli/tools/plugin_manager.py`:

```python
from ayder_cli.tools.plugin_github import (
    parse_github_url,
    download_plugin,
)


def detect_source_type(source: str) -> str:
    """Detect whether source is a GitHub URL or local path."""
    if source.startswith("https://github.com"):
        return "github"
    return "local"


def install_plugin_from_github(
    url: str,
    project_local: bool = False,
    project_path: Path | None = None,
    force: bool = False,
) -> PluginManifest:
    """Install a plugin from a GitHub URL."""
    import tempfile

    source = parse_github_url(url)
    plugins_dir = _get_plugins_dir(project_local, project_path)

    # Download to temp directory first
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "plugin"
        commit_sha = download_plugin(source, tmp_path)
        manifest = parse_plugin_toml(tmp_path)

        # Check API compatibility
        err = check_api_compatibility(manifest.api_version)
        if err:
            raise PluginError(err)

        target_dir = plugins_dir / manifest.name
        if target_dir.exists() and not force:
            raise PluginError(
                f"Plugin '{manifest.name}' already installed. "
                "Use --force to overwrite."
            )

        # Copy to final location
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(tmp_path, target_dir)

    # Update plugins.json
    from datetime import datetime, timezone

    data = read_plugins_json(plugins_dir)
    data["plugins"][manifest.name] = {
        "version": manifest.version,
        "api_version": manifest.api_version,
        "source": url,
        "source_type": "github",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit_sha,
    }
    _write_plugins_json(plugins_dir, data)

    logger.info(f"Installed plugin '{manifest.name}' v{manifest.version}")
    return manifest


def install_plugin(
    source: str,
    project_local: bool = False,
    project_path: Path | None = None,
    force: bool = False,
) -> PluginManifest:
    """Install a plugin from either a GitHub URL or local path."""
    if detect_source_type(source) == "github":
        return install_plugin_from_github(
            source, project_local, project_path, force
        )
    return install_plugin_from_local(
        Path(source).resolve(), project_local, project_path, force
    )


def update_plugin(
    name: str | None = None,
    project_path: Path | None = None,
) -> list[str]:
    """Update one or all installed plugins. Returns list of updated names."""
    updated = []
    for plugins_dir in _search_plugin_dirs(project_path):
        data = read_plugins_json(plugins_dir)
        plugins_to_update = (
            {name: data["plugins"][name]}
            if name and name in data["plugins"]
            else data.get("plugins", {})
        )

        for pname, info in plugins_to_update.items():
            source_type = info["source_type"]
            source = info["source"]

            if source_type == "local":
                source_path = Path(source)
                if not source_path.exists():
                    logger.warning(
                        f"Source path for '{pname}' no longer exists: {source}"
                    )
                    continue
                install_plugin_from_local(
                    source_path,
                    project_local=PROJECT_PLUGINS_DIR_NAME in str(plugins_dir),
                    project_path=project_path,
                    force=True,
                )
            elif source_type == "github":
                install_plugin_from_github(
                    source,
                    project_local=PROJECT_PLUGINS_DIR_NAME in str(plugins_dir),
                    project_path=project_path,
                    force=True,
                )
            updated.append(pname)

    if name and not updated:
        raise PluginError(f"Plugin '{name}' not found")
    return updated


def _find_plugin_module(plugin_name: str, module_name: str):
    """Import a module from an installed plugin directory."""
    for plugins_dir in _search_plugin_dirs():
        plugin_dir = plugins_dir / plugin_name
        if plugin_dir.exists():
            plugin_path = str(plugin_dir)
            sys.path.insert(0, plugin_path)
            try:
                sys.modules.pop(module_name, None)
                return importlib.import_module(module_name)
            finally:
                if plugin_path in sys.path:
                    sys.path.remove(plugin_path)
    raise PluginError(f"Plugin '{plugin_name}' not found")


def _get_builtin_tags() -> set[str]:
    """Get the set of builtin tool tags to prevent conflicts."""
    try:
        from ayder_cli.tools.definition import _BUILTIN_DEFINITIONS
        tags: set[str] = set()
        for td in _BUILTIN_DEFINITIONS:
            tags.update(td.tags)
        return tags
    except ImportError:
        return {"core", "metadata"}
```

Note: `_find_plugin_module` is used by `cli_runner.py` and `handle_temporal` to dynamically import from installed plugins. `_get_builtin_tags` is used in install functions to reject plugin names that conflict with builtin tags.

Update `install_plugin_from_local` and `install_plugin_from_github` — add this check before copying:

```python
    # Check for builtin tag conflict
    builtin_tags = _get_builtin_tags()
    if manifest.name in builtin_tags:
        raise PluginError(
            f"Plugin name '{manifest.name}' conflicts with builtin tag"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_plugin_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ayder_cli/tools/plugin_manager.py tests/tools/test_plugin_manager.py
git commit -m "feat(plugins): add GitHub install, unified install, and update operations"
```

---

## Task 6: Plugin Loading into Tool Registry

**Files:**
- Modify: `src/ayder_cli/tools/plugin_manager.py` (add load functions)
- Modify: `src/ayder_cli/tools/definition.py:69-163` (merge global plugins)
- Modify: `src/ayder_cli/tools/registry.py:117-125` (load project plugins)
- Test: `tests/tools/test_plugin_loading.py`

- [ ] **Step 1: Write the test**

```python
# tests/tools/test_plugin_loading.py
"""Integration tests for external plugin loading into the tool registry."""

import sys
from pathlib import Path

import pytest

from ayder_cli.tools.plugin_manager import (
    load_plugin_definitions,
    PluginError,
)


@pytest.fixture
def valid_plugin(tmp_path):
    """Create a valid plugin with definitions and implementation."""
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()

    (plugin_dir / "plugin.toml").write_text("""\
[plugin]
name = "test-plugin"
version = "1.0.0"
api_version = 1
description = "Test"
author = "test"

[tools]
definitions = "test_defs.py"
""")
    (plugin_dir / "test_defs.py").write_text("""\
from ayder_cli.tools.definition import ToolDefinition

TOOL_DEFINITIONS = (
    ToolDefinition(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        tags=("test",),
        func_ref="test_impl:test_func",
    ),
)
""")
    (plugin_dir / "test_impl.py").write_text("""\
from ayder_cli.core.result import ToolSuccess

def test_func():
    return ToolSuccess("ok")
""")
    return plugin_dir


def test_load_plugin_definitions(valid_plugin):
    defs, handlers = load_plugin_definitions(valid_plugin)
    assert len(defs) == 1
    assert defs[0].name == "test_tool"
    assert "test_tool" in handlers
    assert callable(handlers["test_tool"])


def test_load_plugin_cleans_sys_path(valid_plugin):
    original_path = sys.path.copy()
    load_plugin_definitions(valid_plugin)
    assert str(valid_plugin) not in sys.path
    assert len(sys.path) == len(original_path)


def test_load_plugin_incompatible_api(tmp_path):
    plugin_dir = tmp_path / "bad-api"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.toml").write_text("""\
[plugin]
name = "bad-api"
version = "1.0.0"
api_version = 999
description = "Future plugin"
author = "test"

[tools]
definitions = "defs.py"
""")
    (plugin_dir / "defs.py").write_text("TOOL_DEFINITIONS = ()")
    with pytest.raises(PluginError, match="API"):
        load_plugin_definitions(plugin_dir)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_plugin_loading.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `load_plugin_definitions` in plugin_manager.py**

Add to `src/ayder_cli/tools/plugin_manager.py`:

```python
import importlib
import sys
from typing import Callable, Tuple

from ayder_cli.tools.definition import ToolDefinition


def load_plugin_definitions(
    plugin_dir: Path,
) -> tuple[tuple[ToolDefinition, ...], dict[str, Callable]]:
    """Load tool definitions and resolve handlers from a plugin directory.

    Adds plugin_dir to sys.path temporarily, imports the definitions module,
    resolves all func_refs eagerly, then removes from sys.path.

    Returns:
        (definitions_tuple, {tool_name: callable} handlers dict)
    """
    manifest = parse_plugin_toml(plugin_dir)

    # Check API compatibility
    err = check_api_compatibility(manifest.api_version)
    if err:
        raise PluginError(err)

    plugin_path = str(plugin_dir)
    sys.path.insert(0, plugin_path)
    try:
        # Import definitions module
        defs_module_name = manifest.definitions_file.removesuffix(".py")
        # Remove from cache if previously loaded (for updates)
        sys.modules.pop(defs_module_name, None)
        module = importlib.import_module(defs_module_name)

        if not hasattr(module, "TOOL_DEFINITIONS"):
            raise PluginError(
                f"Plugin '{manifest.name}': {manifest.definitions_file} "
                "missing TOOL_DEFINITIONS"
            )

        defs: tuple[ToolDefinition, ...] = module.TOOL_DEFINITIONS

        # Eagerly resolve func_refs
        handlers: dict[str, Callable] = {}
        for td in defs:
            if td.func_ref:
                mod_path, func_name = td.func_ref.split(":")
                sys.modules.pop(mod_path, None)
                impl_module = importlib.import_module(mod_path)
                handlers[td.name] = getattr(impl_module, func_name)

        return defs, handlers
    finally:
        if plugin_path in sys.path:
            sys.path.remove(plugin_path)
```

- [ ] **Step 4: Write `_discover_global_plugins` and update `definition.py`**

Add a new function to `src/ayder_cli/tools/plugin_manager.py`:

```python
def discover_global_plugins() -> tuple[
    tuple[ToolDefinition, ...], dict[str, Callable]
]:
    """Discover and load all globally installed plugins.

    Called at import time by definition.py. Returns merged definitions
    and handlers from all compatible global plugins.
    """
    all_defs: list[ToolDefinition] = []
    all_handlers: dict[str, Callable] = {}

    if not GLOBAL_PLUGINS_DIR.exists():
        return (), {}

    for plugin_dir in sorted(GLOBAL_PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name == "plugins.json":
            continue
        toml_path = plugin_dir / "plugin.toml"
        if not toml_path.exists():
            continue
        try:
            defs, handlers = load_plugin_definitions(plugin_dir)
            all_defs.extend(defs)
            all_handlers.update(handlers)
            logger.info(
                f"Loaded global plugin '{plugin_dir.name}' "
                f"({len(defs)} tools)"
            )
        except PluginError as e:
            logger.warning(f"Skipping plugin '{plugin_dir.name}': {e}")

    return tuple(all_defs), all_handlers
```

Modify `src/ayder_cli/tools/definition.py` at lines 160-163. Replace:

```python
TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = _discover_definitions()
```

With:

```python
_BUILTIN_DEFINITIONS: Tuple[ToolDefinition, ...] = _discover_definitions()

# Phase 1: Merge global plugins at import time
try:
    from ayder_cli.tools.plugin_manager import discover_global_plugins

    _GLOBAL_PLUGIN_DEFS, _PLUGIN_HANDLERS = discover_global_plugins()
except Exception as e:
    logger.warning(f"Failed to load global plugins: {e}")
    _GLOBAL_PLUGIN_DEFS = ()
    _PLUGIN_HANDLERS: dict = {}

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    _BUILTIN_DEFINITIONS + _GLOBAL_PLUGIN_DEFS
)
```

- [ ] **Step 5: Update `create_default_registry` in registry.py**

Modify `src/ayder_cli/tools/registry.py` lines 117-125. Replace `create_default_registry`:

```python
def create_default_registry(
    project_ctx: ProjectContext, process_manager: Any = None
) -> ToolRegistry:
    """Create a ToolRegistry with all tools from TOOL_DEFINITIONS auto-registered."""
    from ayder_cli.tools.definition import _PLUGIN_HANDLERS

    reg = ToolRegistry(project_ctx, process_manager=process_manager)
    for td in TOOL_DEFINITIONS:
        if td.name in _PLUGIN_HANDLERS:
            # External plugin — use pre-resolved handler
            reg.register(td.name, _PLUGIN_HANDLERS[td.name])
        else:
            # Builtin — resolve func_ref as before
            func = _resolve_func_ref(td.func_ref)
            reg.register(td.name, func)

    # Phase 2: Load project-local plugins
    project_path = project_ctx.project_root
    _load_project_plugins(reg, project_path)

    return reg


def _load_project_plugins(reg: ToolRegistry, project_path: Path) -> None:
    """Load project-local plugins and register them dynamically."""
    from ayder_cli.tools.plugin_manager import (
        load_plugin_definitions,
        PROJECT_PLUGINS_DIR_NAME,
    )

    plugins_dir = project_path / PROJECT_PLUGINS_DIR_NAME
    if not plugins_dir.exists():
        return

    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name == "plugins.json":
            continue
        toml_path = plugin_dir / "plugin.toml"
        if not toml_path.exists():
            continue

        try:
            from ayder_cli.tools.plugin_manager import (
                load_plugin_definitions,
                GLOBAL_PLUGINS_DIR,
            )

            # Check for plugin-name conflict with global plugins
            if GLOBAL_PLUGINS_DIR.exists() and (GLOBAL_PLUGINS_DIR / plugin_dir.name).exists():
                raise ValueError(
                    f"Plugin name conflict: '{plugin_dir.name}' exists in both "
                    f"global and project-local plugins"
                )

            defs, handlers = load_plugin_definitions(plugin_dir)

            # Check for tool-name conflicts
            existing_names = set(reg.get_registered_tools())
            for td in defs:
                if td.name in existing_names:
                    raise ValueError(
                        f"Tool name conflict: '{td.name}' from project plugin "
                        f"'{plugin_dir.name}' conflicts with an existing tool"
                    )
                reg.register_dynamic_tool(td, handlers[td.name])

            logger.info(
                f"Loaded project plugin '{plugin_dir.name}' ({len(defs)} tools)"
            )
        except Exception as e:
            logger.warning(f"Skipping project plugin '{plugin_dir.name}': {e}")
```

- [ ] **Step 6: Run tests to verify**

Run: `uv run pytest tests/tools/test_plugin_loading.py tests/tools/test_plugin_api.py -v`
Expected: PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `uv run poe test`
Expected: All existing tests pass

- [ ] **Step 8: Commit**

```bash
git add src/ayder_cli/tools/plugin_manager.py src/ayder_cli/tools/definition.py src/ayder_cli/tools/registry.py tests/tools/test_plugin_loading.py
git commit -m "feat(plugins): add plugin loading into tool registry with two-phase discovery"
```

---

## Task 7: CLI Subcommands

**Files:**
- Modify: `src/ayder_cli/cli.py:13-113` (add subcommands)
- Modify: `src/ayder_cli/cli.py:116-208` (dispatch subcommands)

- [ ] **Step 1: Add subparser to `create_parser()`**

In `src/ayder_cli/cli.py`, add subparsers after the main parser is created (after line 17, before task arguments):

```python
    subparsers = parser.add_subparsers(dest="subcommand")

    # Plugin management subcommands
    install_parser = subparsers.add_parser(
        "install-plugin", help="Install a plugin from GitHub or local path"
    )
    install_parser.add_argument("source", help="GitHub URL or local path")
    install_parser.add_argument(
        "--project", action="store_true",
        help="Install to project-local .ayder/plugins/ instead of global",
    )
    install_parser.add_argument(
        "--force", action="store_true", help="Overwrite if already installed"
    )

    uninstall_parser = subparsers.add_parser(
        "uninstall-plugin", help="Uninstall a plugin by name"
    )
    uninstall_parser.add_argument("name", help="Plugin name to uninstall")

    subparsers.add_parser("list-plugins", help="List installed plugins")

    update_parser = subparsers.add_parser(
        "update-plugin", help="Update one or all plugins"
    )
    update_parser.add_argument(
        "name", nargs="?", default=None, help="Plugin name (omit for all)"
    )
```

- [ ] **Step 2: Add dispatch in `main()`**

In `src/ayder_cli/cli.py`, add subcommand dispatch after `args = parser.parse_args()` and before the task-related CLI options:

```python
    # Handle plugin subcommands
    if args.subcommand == "install-plugin":
        from ayder_cli.tools.plugin_manager import install_plugin, uninstall_plugin, PluginError
        try:
            manifest = install_plugin(
                args.source,
                project_local=args.project,
                project_path=Path.cwd() if args.project else None,
                force=args.force,
            )
            # Handle dependencies
            if manifest.dependencies:
                print(f"Plugin '{manifest.name}' requires dependencies:")
                for dep, version in manifest.dependencies.items():
                    print(f"  {dep} {version}")
                confirm = input("Install dependencies? [y/N] ")
                if confirm.lower() == "y":
                    try:
                        _install_plugin_deps(manifest.dependencies)
                    except Exception as e:
                        # Rollback: remove the installed plugin
                        uninstall_plugin(
                            manifest.name,
                            project_path=Path.cwd() if args.project else None,
                        )
                        print(f"Error installing dependencies: {e}", file=sys.stderr)
                        print(f"Plugin '{manifest.name}' removed (rollback).", file=sys.stderr)
                        sys.exit(1)
            print(f"Plugin '{manifest.name}' v{manifest.version} installed.")
        except PluginError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.subcommand == "uninstall-plugin":
        from ayder_cli.tools.plugin_manager import uninstall_plugin, PluginError
        try:
            uninstall_plugin(args.name, project_path=Path.cwd())
            print(f"Plugin '{args.name}' uninstalled.")
        except PluginError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.subcommand == "list-plugins":
        from ayder_cli.tools.plugin_manager import list_installed_plugins
        plugins = list_installed_plugins(project_path=Path.cwd())
        if not plugins:
            print("No plugins installed.")
        else:
            print("Installed plugins:")
            for p in plugins:
                source_info = p.get("source", "unknown")
                scope = p.get("scope", "global")
                print(f"  {p['name']:20s} v{p['version']:10s} ({scope}: {source_info})")
        return

    if args.subcommand == "update-plugin":
        from ayder_cli.tools.plugin_manager import update_plugin, PluginError
        try:
            updated = update_plugin(args.name, project_path=Path.cwd())
            if updated:
                print(f"Updated: {', '.join(updated)}")
            else:
                print("No plugins to update.")
        except PluginError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return
```

Add helper at end of file:

```python
def _install_plugin_deps(dependencies: dict[str, str]) -> None:
    """Install plugin pip dependencies via uv pip or pip fallback."""
    import subprocess
    pkgs = [f"{name}{ver}" for name, ver in dependencies.items()]
    # Try uv pip first, fall back to pip
    for cmd in (["uv", "pip", "install"], ["pip", "install"]):
        try:
            subprocess.run([*cmd, *pkgs], check=True)
            return
        except FileNotFoundError:
            continue
    print("Warning: Could not find uv or pip to install dependencies.")
```

- [ ] **Step 3: Make `--temporal-task-queue` conditional**

In `create_parser()`, wrap the temporal argument (lines 36-41) with a check:

```python
    # Conditional: only add --temporal-task-queue if temporal plugin is loaded
    try:
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME
        if "temporal_workflow" in TOOL_DEFINITIONS_BY_NAME:
            parser.add_argument(
                "--temporal-task-queue",
                type=str,
                metavar="QUEUE",
                default=None,
                help="Start Temporal worker bound to the given task queue",
            )
    except ImportError:
        pass
```

- [ ] **Step 4: Update `cli_runner.py` for dynamic temporal import**

Modify `src/ayder_cli/cli_runner.py` at lines 258-272 — replace the import to use plugin path:

```python
def _run_temporal_queue_cli(
    queue_name: str,
    prompt_path: str | None = None,
    permissions=None,
) -> int:
    """Start a Temporal worker queue session."""
    try:
        from ayder_cli.tools.plugin_manager import _find_plugin_module
        temporal_worker = _find_plugin_module("temporal-tools", "temporal_worker")
        TemporalWorker = getattr(temporal_worker, "TemporalWorker")
        TemporalWorkerConfig = getattr(temporal_worker, "TemporalWorkerConfig")
    except Exception:
        # Fallback to direct import for backwards compatibility
        from ayder_cli.services.temporal_worker import TemporalWorker, TemporalWorkerConfig

    worker_config = TemporalWorkerConfig(
        queue_name=queue_name,
        prompt_path=prompt_path,
        permissions=set(permissions or {"r"}),
    )
    worker = TemporalWorker(worker_config)
    return worker.run()
```

- [ ] **Step 5: Update `handle_temporal` in commands.py for dynamic import**

Modify `src/ayder_cli/tui/commands.py` at line 723-725 — replace the direct import:

```python
def handle_temporal(app: AyderApp, args: str, chat_view: ChatView) -> None:
    """Handle /temporal command - start/status local temporal queue runner."""
    try:
        from ayder_cli.tools.plugin_manager import _find_plugin_module
        temporal_worker = _find_plugin_module("temporal-tools", "temporal_worker")
        TemporalWorker = getattr(temporal_worker, "TemporalWorker")
        TemporalWorkerConfig = getattr(temporal_worker, "TemporalWorkerConfig")
    except Exception:
        chat_view.add_system_message(
            "Temporal plugin not installed. Install with: "
            "ayder install-plugin <path-to-temporal-tools>"
        )
        return
```

The rest of `handle_temporal` remains the same but uses the dynamically imported classes.

- [ ] **Step 6: Run existing CLI tests + manual smoke test**

Run: `uv run poe test`
Run manually: `uv run ayder list-plugins`
Expected: PASS, "No plugins installed."

- [ ] **Step 7: Commit**

```bash
git add src/ayder_cli/cli.py src/ayder_cli/cli_runner.py src/ayder_cli/tui/commands.py
git commit -m "feat(plugins): add install-plugin, uninstall-plugin, list-plugins, update-plugin CLI commands"
```

---

## Task 8: Multi-Select Plugin Screen

**Files:**
- Modify: `src/ayder_cli/tui/screens.py:277-400` (add new class after `CLISelectScreen`)
- Modify: `src/ayder_cli/tui/commands.py:863-922` (use new screen)
- Test: `tests/tui/test_multi_select_screen.py`

- [ ] **Step 1: Write the test**

```python
# tests/tui/test_multi_select_screen.py
"""Tests for CLIMultiSelectScreen widget."""

import pytest
from ayder_cli.tui.screens import CLIMultiSelectScreen


def test_multi_select_screen_init():
    items = [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]
    selected = {"a", "c"}
    screen = CLIMultiSelectScreen(
        title="Test", items=items, selected=selected
    )
    assert screen.selected == {"a", "c"}
    assert screen.selected_index == 0


def test_multi_select_toggle():
    items = [("a", "Alpha"), ("b", "Beta")]
    selected = {"a"}
    screen = CLIMultiSelectScreen(
        title="Test", items=items, selected=selected
    )
    # Toggle 'a' off
    screen._toggle_current()
    assert "a" not in screen.selected
    # Toggle 'a' back on
    screen._toggle_current()
    assert "a" in screen.selected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tui/test_multi_select_screen.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `CLIMultiSelectScreen`**

Add to `src/ayder_cli/tui/screens.py` after the `CLISelectScreen` class (after line 400):

```python
class CLIMultiSelectScreen(ModalScreen[set[str] | None]):
    """
    CLI-style multi-selection screen with toggle support.
    Returns a set of selected values on confirm, or None on cancel.
    """

    def __init__(
        self,
        title: str,
        items: list[tuple[str, str]],
        selected: set[str] | None = None,
        description: str = "",
    ):
        super().__init__()
        self.title_text = title
        self.items = items
        self.selected = set(selected) if selected else set()
        self.description = description
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"? {self.title_text}", classes="prompt", markup=False)
            if self.description:
                yield Label(self.description, classes="description", markup=False)
            list_content = self._render_list()
            yield Static(list_content, id="select-list", classes="select-list")
            yield Label(
                "↑↓ navigate, Space to toggle, Enter to confirm, Esc to cancel",
                classes="hint",
            )

    MAX_VISIBLE = 15

    def _render_list(self) -> Text:
        result = Text()
        total = len(self.items)
        half = self.MAX_VISIBLE // 2
        start = max(0, self.selected_index - half)
        end = min(total, start + self.MAX_VISIBLE)
        start = max(0, end - self.MAX_VISIBLE)

        if start > 0:
            result.append(f"  ↑ {start} more above\n", style="dim")

        for i in range(start, end):
            value, display = self.items[i]
            is_highlighted = i == self.selected_index
            is_checked = value in self.selected
            mark = "x" if is_checked else " "

            if is_highlighted:
                result.append(" → ", style="bold cyan")
                result.append(f"[{mark}] {display}", style="bold white")
            else:
                result.append("   ", style="dim")
                result.append(f"[{mark}] {display}", style="white")
            result.append("\n")

        remaining = total - end
        if remaining > 0:
            result.append(f"  ↓ {remaining} more below\n", style="dim")

        return result

    def _update_display(self) -> None:
        list_widget = self.query_one("#select-list", Static)
        list_widget.update(self._render_list())

    def _toggle_current(self) -> None:
        if not self.items:
            return
        value = self.items[self.selected_index][0]
        if value in self.selected:
            self.selected.discard(value)
        else:
            self.selected.add(value)

    def on_key(self, event) -> None:
        key = event.key.lower()
        if key in ("up", "k"):
            event.stop()
            self.selected_index = max(0, self.selected_index - 1)
            self._update_display()
        elif key in ("down", "j"):
            event.stop()
            self.selected_index = min(
                len(self.items) - 1, self.selected_index + 1
            )
            self._update_display()
        elif key == "space":
            event.stop()
            self._toggle_current()
            self._update_display()
        elif key in ("enter", "return"):
            event.stop()
            self.dismiss(self.selected.copy())
        elif key in ("escape", "q"):
            event.stop()
            self.dismiss(None)
```

- [ ] **Step 4: Update `handle_plugin` in commands.py**

Modify `src/ayder_cli/tui/commands.py` at lines 863-922. Replace the screen push section:

```python
def handle_plugin(app: "AyderApp", args: str, chat_view: ChatView) -> None:
    """Toggle dynamic tool plugins (e.g. venv, http, background, temporal)."""
    from ayder_cli.tools.definition import TOOL_DEFINITIONS
    from ayder_cli.tui.screens import CLIMultiSelectScreen

    # Discover available non-core tags
    available_plugins = set()
    for td in TOOL_DEFINITIONS:
        for tag in td.tags:
            if tag not in ("core", "metadata"):
                available_plugins.add(tag)

    available_plugins_list = sorted(list(available_plugins))

    # Initialize tool_tags if needed
    if app.chat_loop.config.tool_tags is None:
        app.chat_loop.config.tool_tags = frozenset({"core", "metadata"})

    current_tags = set(app.chat_loop.config.tool_tags)

    if args.strip():
        plugin_name = args.strip().lower()
        if plugin_name not in available_plugins_list:
            chat_view.add_system_message(
                f"Unknown plugin: '{plugin_name}'. "
                f"Available: {', '.join(available_plugins_list)}"
            )
            return

        if plugin_name in current_tags:
            current_tags.remove(plugin_name)
            status = "disabled"
        else:
            current_tags.add(plugin_name)
            status = "enabled"

        app.chat_loop.config.tool_tags = frozenset(current_tags)
        chat_view.add_system_message(f"Plugin '{plugin_name}' {status}.")
    else:
        # Show multi-select screen
        items = []
        for p in available_plugins_list:
            items.append((p, p))

        currently_selected = {
            p for p in available_plugins_list if p in current_tags
        }

        def on_plugins_confirmed(result: set[str] | None) -> None:
            if result is None:
                return  # Cancelled
            # Apply the new set of enabled plugins
            base_tags = {"core", "metadata"}
            new_tags = base_tags | result
            app.chat_loop.config.tool_tags = frozenset(new_tags)
            enabled = sorted(result)
            chat_view.add_system_message(
                f"Plugins updated: {', '.join(enabled) if enabled else 'none enabled'}"
            )

        app.push_screen(
            CLIMultiSelectScreen(
                title="Toggle Tool Plugins",
                items=items,
                selected=currently_selected,
                description="Space to toggle, Enter to confirm, Esc to cancel",
            ),
            on_plugins_confirmed,
        )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/tui/test_multi_select_screen.py -v`
Expected: PASS

Run: `uv run poe test`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/ayder_cli/tui/screens.py src/ayder_cli/tui/commands.py tests/tui/test_multi_select_screen.py
git commit -m "feat(plugins): add multi-select plugin screen and update /plugin handler"
```

---

## Task 9: Extract Plugins to ayder-plugins Repo

**Files:**
- Create: All plugin files in `/Users/sinanalyuruk/Vscode/ayder-plugins/`
- Remove: Builtin files from `src/ayder_cli/tools/builtins/` and `services/` and `application/`

This task works in the `ayder-plugins` directory at `/Users/sinanalyuruk/Vscode/ayder-plugins/`.

- [ ] **Step 1: Create dbs-tools plugin**

Copy `src/ayder_cli/tools/builtins/dbs_tool.py` to `ayder-plugins/dbs-tools/dbs_tool.py`. No import changes needed (only imports `ayder_cli.core.result`).

Copy `src/ayder_cli/tools/builtins/dbs_tool_definitions.py` to `ayder-plugins/dbs-tools/dbs_tool_definitions.py`. Change:
- `from ..definition import ToolDefinition` → `from ayder_cli.tools.definition import ToolDefinition`
- `func_ref="ayder_cli.tools.builtins.dbs_tool:dbs_tool"` → `func_ref="dbs_tool:dbs_tool"`

Create `ayder-plugins/dbs-tools/plugin.toml`:
```toml
[plugin]
name = "dbs-tools"
version = "1.0.0"
api_version = 1
description = "Database inspection and query tools"
author = "ayder"

[tools]
definitions = "dbs_tool_definitions.py"
```

- [ ] **Step 2: Create venv-tools plugin**

Copy `src/ayder_cli/tools/builtins/venv.py` to `ayder-plugins/venv-tools/venv.py`. No import changes needed.

Copy `src/ayder_cli/tools/builtins/venv_definitions.py` to `ayder-plugins/venv-tools/venv_definitions.py`. Change:
- `from ..definition import ToolDefinition` → `from ayder_cli.tools.definition import ToolDefinition`
- All `func_ref="ayder_cli.tools.builtins.venv:..."` → `func_ref="venv:..."`

Create `ayder-plugins/venv-tools/plugin.toml`:
```toml
[plugin]
name = "venv-tools"
version = "1.0.0"
api_version = 1
description = "Python virtual environment management tools"
author = "ayder"

[tools]
definitions = "venv_definitions.py"
```

- [ ] **Step 3: Create python-tools plugin**

Copy `src/ayder_cli/tools/builtins/python_editor.py` to `ayder-plugins/python-tools/python_editor.py`. No import changes needed.

Copy `src/ayder_cli/tools/builtins/python_editor_definitions.py` to `ayder-plugins/python-tools/python_editor_definitions.py`. Change:
- `from ..definition import ToolDefinition` → `from ayder_cli.tools.definition import ToolDefinition`
- All `func_ref="ayder_cli.tools.builtins.python_editor:..."` → `func_ref="python_editor:..."`

Create `ayder-plugins/python-tools/plugin.toml`:
```toml
[plugin]
name = "python-tools"
version = "1.0.0"
api_version = 1
description = "Python code editing tools using CST"
author = "ayder"

[dependencies]
libcst = ">=1.0"

[tools]
definitions = "python_editor_definitions.py"
```

- [ ] **Step 4: Create temporal-tools plugin**

Copy these files to `ayder-plugins/temporal-tools/`:
- `tools/builtins/temporal.py` → `temporal.py` — change import: `from ayder_cli.services.temporal_workflow_service` → `from temporal_workflow_service`
- `tools/builtins/temporal_definitions.py` → `temporal_definitions.py` — change `from ..definition` → `from ayder_cli.tools.definition`, update `func_ref`
- `services/temporal_workflow_service.py` → `temporal_workflow_service.py` — change imports to intra-plugin (`from temporal_contract`, `from temporal_client`)
- `services/temporal_client.py` → `temporal_client.py` — imports from `ayder_cli.core.config` (stable API, no change needed)
- `services/temporal_worker.py` → `temporal_worker.py` — change `from ayder_cli.services.temporal_client` → `from temporal_client`
- `application/temporal_contract.py` → `temporal_contract.py` — no changes (only uses pydantic)
- `application/temporal_metadata.py` → `temporal_metadata.py` — no changes (only uses stable API)

Create `ayder-plugins/temporal-tools/plugin.toml`:
```toml
[plugin]
name = "temporal-tools"
version = "1.0.0"
api_version = 1
description = "Temporal workflow orchestration tools"
author = "ayder"

[dependencies]
temporalio = ">=1.22.0,<1.23.0"
pydantic = ">=2.0"

[tools]
definitions = "temporal_definitions.py"
```

- [ ] **Step 5: Verify plugin structure**

```bash
ls -la /Users/sinanalyuruk/Vscode/ayder-plugins/*/plugin.toml
```

Expected: 4 plugin.toml files

- [ ] **Step 6: Test local install of each plugin**

```bash
cd /Users/sinanalyuruk/Vscode/ayder-cli
uv run ayder install-plugin /Users/sinanalyuruk/Vscode/ayder-plugins/dbs-tools
uv run ayder list-plugins
```

Expected: dbs-tools shows as installed

- [ ] **Step 7: Initialize and commit ayder-plugins**

```bash
cd /Users/sinanalyuruk/Vscode/ayder-plugins
git init
git add -A
git commit -m "feat: initial plugin extraction — dbs, venv, python, temporal tools"
```

---

## Task 10: Remove Extracted Files from ayder-cli

**Files:**
- Remove: `src/ayder_cli/tools/builtins/dbs_tool.py`
- Remove: `src/ayder_cli/tools/builtins/dbs_tool_definitions.py`
- Remove: `src/ayder_cli/tools/builtins/venv.py`
- Remove: `src/ayder_cli/tools/builtins/venv_definitions.py`
- Remove: `src/ayder_cli/tools/builtins/python_editor.py`
- Remove: `src/ayder_cli/tools/builtins/python_editor_definitions.py`
- Remove: `src/ayder_cli/tools/builtins/temporal.py`
- Remove: `src/ayder_cli/tools/builtins/temporal_definitions.py`
- Remove: `src/ayder_cli/services/temporal_workflow_service.py`
- Remove: `src/ayder_cli/services/temporal_client.py`
- Remove: `src/ayder_cli/services/temporal_worker.py`
- Remove: `src/ayder_cli/application/temporal_contract.py`
- Remove: `src/ayder_cli/application/temporal_metadata.py`
- Modify: `src/ayder_cli/services/__init__.py` (remove temporal imports)
- Modify: `src/ayder_cli/application/__init__.py` (remove temporal imports)
- Modify: `pyproject.toml` (remove temporal optional dep)

- [ ] **Step 1: Remove builtin plugin files**

```bash
cd /Users/sinanalyuruk/Vscode/ayder-cli
rm src/ayder_cli/tools/builtins/dbs_tool.py
rm src/ayder_cli/tools/builtins/dbs_tool_definitions.py
rm src/ayder_cli/tools/builtins/venv.py
rm src/ayder_cli/tools/builtins/venv_definitions.py
rm src/ayder_cli/tools/builtins/python_editor.py
rm src/ayder_cli/tools/builtins/python_editor_definitions.py
rm src/ayder_cli/tools/builtins/temporal.py
rm src/ayder_cli/tools/builtins/temporal_definitions.py
```

- [ ] **Step 2: Remove temporal service/application files**

```bash
rm src/ayder_cli/services/temporal_workflow_service.py
rm src/ayder_cli/services/temporal_client.py
rm src/ayder_cli/services/temporal_worker.py
rm src/ayder_cli/application/temporal_contract.py
rm src/ayder_cli/application/temporal_metadata.py
```

- [ ] **Step 3: Remove temporal imports from `__init__.py` files**

Modify `src/ayder_cli/services/__init__.py` — remove the temporal import line:
```python
from ayder_cli.services.temporal_client import (
    TemporalClientAdapter,
    TemporalClientUnavailableError,
)
```

Modify `src/ayder_cli/application/__init__.py` — remove temporal imports:
```python
from ayder_cli.application.temporal_contract import (
    TemporalActivityContract,
    validate_temporal_activity_contract,
)
```

Also remove these names from any `__all__` lists in these files.

- [ ] **Step 4: Remove temporal optional dependency from pyproject.toml**

Remove lines 36-39 from `pyproject.toml`:
```toml
[project.optional-dependencies]
temporal = [
    "temporalio>=1.22.0,<1.23.0; python_version < '3.13'",
]
```

- [ ] **Step 5: Update/remove tests that directly import extracted tools**

Move or add skip conditions to:
- `tests/tools/test_dbs_tool.py` — add `pytest.importorskip` or move to plugin repo
- `tests/tools/test_python_editor.py` — same
- `tests/tools/test_virtualenv.py` — same (venv tool tests)
- `tests/tools/test_temporal_tool.py` — same
- `tests/tools/test_impl_coverage.py` — remove venv/dbs/python_editor/temporal references
- `tests/services/test_temporal_workflow_service.py` — same
- `tests/services/test_temporal_client.py` — same
- `tests/services/test_temporal_worker.py` — same
- `tests/application/test_temporal_contract.py` — same
- `tests/convergence/test_temporal_runtime_wiring.py` — same
- `tests/ui/test_tui_temporal_command.py` — same
- `tests/test_tasks.py` — remove `persist_temporal_run_metadata` and `update_task_temporal_metadata` tests

For each test file, add at the top:

```python
pytest.importorskip("module_name", reason="Plugin not installed")
```

Or remove entirely if moving to plugin repo.

- [ ] **Step 6: Run full test suite**

Run: `uv run poe test`
Expected: All remaining tests pass (extracted tool tests skipped)

- [ ] **Step 7: Commit**

```bash
git add -u  # stages all deletions and modifications
git commit -m "refactor: remove extracted plugin files (moved to ayder-plugins repo)"
```

---

## Task 11: End-to-End Smoke Test

- [ ] **Step 1: Install dbs-tools from local path**

```bash
uv run ayder install-plugin /Users/sinanalyuruk/Vscode/ayder-plugins/dbs-tools
uv run ayder list-plugins
```

Expected: Shows `dbs-tools v1.0.0 (local: ...)`

- [ ] **Step 2: Verify tool loads at runtime**

Start ayder TUI and run `/plugin` — should show `dbs` as an available tag.

- [ ] **Step 3: Uninstall and verify**

```bash
uv run ayder uninstall-plugin dbs-tools
uv run ayder list-plugins
```

Expected: No plugins installed, `/plugin` no longer shows `dbs`.

- [ ] **Step 4: Install all 4 plugins**

```bash
uv run ayder install-plugin /Users/sinanalyuruk/Vscode/ayder-plugins/dbs-tools
uv run ayder install-plugin /Users/sinanalyuruk/Vscode/ayder-plugins/venv-tools
uv run ayder install-plugin /Users/sinanalyuruk/Vscode/ayder-plugins/python-tools
uv run ayder install-plugin /Users/sinanalyuruk/Vscode/ayder-plugins/temporal-tools
uv run ayder list-plugins
```

Expected: All 4 listed

- [ ] **Step 5: Update all plugins**

```bash
uv run ayder update-plugin
```

Expected: All 4 updated

- [ ] **Step 6: Run full test suite one final time**

```bash
uv run poe test
```

Expected: All tests pass

- [ ] **Step 7: Final commit if any fixups needed**

```bash
git add -A && git commit -m "fix: address smoke test findings"
```
