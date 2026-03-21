"""Plugin manager — install, uninstall, update, list, and load external plugins."""

from __future__ import annotations

import importlib
import json
import logging
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ayder_cli.tools.plugin_api import check_api_compatibility
from ayder_cli.tools.plugin_github import (
    parse_github_url,
    download_plugin,
)

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
    source_dir: Path | None = field(default=None)


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


def read_plugins_json(plugins_dir: Path) -> dict[str, Any]:
    """Read the plugins.json manifest from a plugins directory."""
    manifest_path = plugins_dir / "plugins.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
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


def _validate_manifest(manifest: PluginManifest) -> None:
    """Validate API compatibility and builtin tag conflicts."""
    err = check_api_compatibility(manifest.api_version)
    if err:
        raise PluginError(err)
    builtin_tags = _get_builtin_tags()
    if manifest.name in builtin_tags:
        raise PluginError(
            f"Plugin name '{manifest.name}' conflicts with builtin tag"
        )


def install_plugin_from_local(
    source_dir: Path,
    project_local: bool = False,
    project_path: Path | None = None,
    force: bool = False,
) -> PluginManifest:
    """Install a plugin from a local directory by copying."""
    manifest = parse_plugin_toml(source_dir)
    _validate_manifest(manifest)

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
        scope = "global" if plugins_dir.resolve() == GLOBAL_PLUGINS_DIR.resolve() else "project"
        for name, info in data.get("plugins", {}).items():
            result.append({"name": name, "scope": scope, **info})
    return result


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
    source = parse_github_url(url)
    plugins_dir = _get_plugins_dir(project_local, project_path)

    # Download to temp directory first
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "plugin"
        commit_sha = download_plugin(source, tmp_path)
        manifest = parse_plugin_toml(tmp_path)
        _validate_manifest(manifest)

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

        is_project = plugins_dir.resolve() != GLOBAL_PLUGINS_DIR.resolve()
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
                    project_local=is_project,
                    project_path=project_path,
                    force=True,
                )
            elif source_type == "github":
                install_plugin_from_github(
                    source,
                    project_local=is_project,
                    project_path=project_path,
                    force=True,
                )
            updated.append(pname)

    if name and not updated:
        raise PluginError(f"Plugin '{name}' not found")
    return updated


def _find_plugin_module(plugin_name: str, module_name: str, project_path: Path | None = None):
    """Import a module from an installed plugin directory."""
    for plugins_dir in _search_plugin_dirs(project_path):
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


def load_plugin_definitions(
    plugin_dir: Path,
) -> tuple[tuple, dict[str, Callable]]:
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

        defs = module.TOOL_DEFINITIONS

        # Eagerly resolve func_refs
        handlers: dict[str, Callable] = {}
        for td in defs:
            if not td.func_ref:
                raise PluginError(
                    f"ToolDefinition '{td.name}' has no func_ref "
                    "— plugin tools must have a func_ref"
                )
            mod_path, func_name = td.func_ref.split(":")
            sys.modules.pop(mod_path, None)
            impl_module = importlib.import_module(mod_path)
            handlers[td.name] = getattr(impl_module, func_name)

        return defs, handlers
    finally:
        if plugin_path in sys.path:
            sys.path.remove(plugin_path)


def discover_global_plugins() -> tuple[tuple, dict[str, Callable]]:
    """Discover and load all globally installed plugins.

    Called at import time by definition.py. Returns merged definitions
    and handlers from all compatible global plugins.
    """
    all_defs: list = []
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
        except Exception as e:
            logger.warning(f"Skipping plugin '{plugin_dir.name}': {e}")

    return tuple(all_defs), all_handlers
