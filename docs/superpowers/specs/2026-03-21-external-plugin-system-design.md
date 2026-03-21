# External Plugin System Design

## Problem

As the codebase grows, managing all tool plugins in the same repo becomes unwieldy. Builtin tools (core, metadata, background, env, http) must stay, but specialized plugins (venv, temporal, python, dbs) should live in a separate GitHub repo and be installable on demand.

## Approach

GitHub API download — no git dependency for plugin management. Plugins are directories in a GitHub repo (or local filesystem) containing a `plugin.toml` manifest and tool definition/implementation files. ayder downloads only the plugin directory via GitHub's contents API.

## Plugin Contract

### Directory Structure

A plugin is a directory containing:

```
dbs-tools/
├── plugin.toml                # Required: manifest
├── dbs_tool_definitions.py    # TOOL_DEFINITIONS tuple
└── dbs_tool.py                # Tool implementations
```

### plugin.toml Format

```toml
[plugin]
name = "dbs-tools"
version = "1.0.0"
api_version = 1                # minimum ayder plugin API version required (integer)
description = "Database inspection tools"
author = "ayder"

[dependencies]                 # optional pip dependencies
# libcst = ">=1.0"

[tools]
definitions = "dbs_tool_definitions.py"
```

### Tool Interface (unchanged)

Plugins import from the stable plugin API:
- `ayder_cli.core.result` — `ToolSuccess`, `ToolError`
- `ayder_cli.core.context` — `ProjectContext`
- `ayder_cli.tools.definition` — `ToolDefinition`
- `ayder_cli.core.config` — `Config`, `load_config`

All plugin imports must use **absolute imports** (not relative). Builtin tools use `from ..definition import ToolDefinition` — external plugins cannot, since they are not inside the `ayder_cli` package. External plugins use `from ayder_cli.tools.definition import ToolDefinition`.

Tool functions follow the existing signature pattern:

```python
from ayder_cli.core.result import ToolSuccess, ToolError
from ayder_cli.core.context import ProjectContext

def tool_name(project_ctx: ProjectContext, arg1: str) -> str:
    return ToolSuccess("result") or ToolError("message", "category")
```

Definition files export a `TOOL_DEFINITIONS: Tuple[ToolDefinition, ...]` tuple, same as builtins.

### func_ref Convention for External Plugins

External plugins use **bare module names** in `func_ref`, not absolute `ayder_cli.*` paths. The plugin's directory is added to `sys.path` at load time, so the module is importable by its filename.

Example for dbs-tools plugin:
```python
func_ref="dbs_tool:dbs_tool"  # NOT "ayder_cli.tools.builtins.dbs_tool:dbs_tool"
```

To avoid module name collisions between plugins (e.g., two plugins both containing `utils.py`), each plugin's directory is added to `sys.path` individually and removed after its definitions and func_refs are both resolved. Unlike builtins (which defer `func_ref` resolution to `create_default_registry()`), external plugins resolve `func_ref` eagerly during the loading step and store the resolved callable in a side-table (`_plugin_handlers: Dict[str, Callable]`). This allows `sys.path` manipulation to be temporary — the callable is captured before the path is removed.

### Temporal Plugin: Self-Contained with Internal Imports

The temporal plugin has dependencies on `ayder_cli.core.config` (for `Config` and `load_config`). This is part of the stable plugin API surface. The temporal service files (`temporal_workflow_service.py`, `temporal_client.py`, `temporal_contract.py`) move into the plugin directory and are refactored to use intra-plugin imports:

```python
# temporal_workflow_service.py (inside temporal-tools plugin)
from temporal_contract import validate_temporal_activity_contract
from temporal_client import TemporalClientAdapter, TemporalClientUnavailableError
from ayder_cli.core.config import Config, load_config  # stable API
from ayder_cli.core.result import ToolError, ToolSuccess  # stable API
```

All temporal service files are refactored the same way:
- `temporal_worker.py` — changes `from ayder_cli.services.temporal_client import ...` to `from temporal_client import ...`
- `temporal_metadata.py` — already imports only from stable API (`ayder_cli.core.context`, `ayder_cli.core.result`)
- `temporal_contract.py` — no ayder imports (uses only `pydantic`), no changes needed

This makes the plugin fully self-contained — it only imports from the stable `ayder_cli` API, never from `ayder_cli.services.*` or `ayder_cli.application.*`.

## Plugin API Versioning

### Constants

```python
# src/ayder_cli/tools/plugin_api.py
PLUGIN_API_VERSION: int = 1      # current version
PLUGIN_API_MIN_VERSION: int = 1  # oldest supported
```

All API version values are **integers** everywhere — in Python constants, in `plugin.toml` (`api_version = 1`), and in `plugins.json` (`"api_version": 1`). Parsed as `int` from TOML (which natively supports integers).

### What triggers a version bump
- Changes to `ToolDefinition` dataclass fields
- Changes to execution pipeline signature (DI parameters)
- Changes to `ToolSuccess`/`ToolError` contract
- Changes to `ProjectContext` interface used by plugins

### Compatibility check

At both install time and load time:
- Plugin `api_version > PLUGIN_API_VERSION` — rejected: "Update ayder"
- Plugin `api_version < PLUGIN_API_MIN_VERSION` — rejected: "Plugin too old"
- At load time, incompatible plugins are skipped with a warning (no crash)

## Plugin Storage

### Disk Layout

```
~/.ayder/plugins/                  # global plugins
├── plugins.json                   # installed plugin manifest
├── dbs-tools/
│   ├── plugin.toml
│   ├── dbs_tool_definitions.py
│   └── dbs_tool.py
└── venv-tools/
    └── ...

<project>/.ayder/plugins/          # project-local plugins
├── plugins.json
└── ...
```

### plugins.json

```json
{
  "plugins": {
    "dbs-tools": {
      "version": "1.0.0",
      "api_version": 1,
      "source": "https://github.com/ayder/ayder-plugins/dbs-tools",
      "source_type": "github",
      "installed_at": "2026-03-21T10:30:00Z",
      "commit_sha": "abc123f"
    },
    "venv-tools": {
      "version": "0.2.0",
      "api_version": 1,
      "source": "/Users/me/dev/ayder-plugins/venv-tools",
      "source_type": "local",
      "installed_at": "2026-03-21T11:00:00Z",
      "commit_sha": null
    }
  }
}
```

### Name Conflict Resolution

- Duplicate **plugin name** between global and project-local: **error, refuse to load**
- Duplicate **plugin name** with a builtin tag: **error at install time**
- Duplicate **tool name** (two plugins defining the same tool `name` in their `TOOL_DEFINITIONS`): **error at load time** — same `ValueError` as the existing builtin duplicate detection in `_discover_definitions()`

## CLI Commands

### install-plugin

```
ayder install-plugin <source> [--project] [--force]
```

Sources:
- GitHub URL: `ayder install-plugin https://github.com/ayder/ayder-plugins/dbs-tools`
- Local path: `ayder install-plugin ../ayder-plugins/dbs-tools`

Steps:
1. Parse source — detect GitHub URL vs local path
2. For GitHub: parse `owner/repo` and subdirectory from URL, download via GitHub API
3. For local: validate directory exists
4. Read `plugin.toml`, validate schema
5. Check `api_version` compatibility
6. Check no name conflict with builtins or installed plugins
7. Copy files to `~/.ayder/plugins/<name>/` (or `.ayder/plugins/` with `--project`)
8. If `[dependencies]` in `plugin.toml`: show list, prompt user for confirmation, install via `uv pip install` (consistent with project's package manager). Falls back to `pip install` if `uv` is not available. If dependency installation fails, the plugin directory is removed (rollback) and the error is reported.
9. Update `plugins.json`
10. Print success summary

Flags:
- `--project` — install to `.ayder/plugins/` instead of global
- `--force` — overwrite if already installed

### uninstall-plugin

```
ayder uninstall-plugin <name>
```

1. Find plugin in global or project-local
2. Remove directory
3. Update `plugins.json`
4. Does NOT uninstall pip dependencies (could affect other packages)

### list-plugins

```
ayder list-plugins
```

Output:
```
Installed plugins:
  dbs-tools     v1.0.0  (github: ayder/ayder-plugins/dbs-tools)
  venv-tools    v0.2.0  (local: /Users/me/dev/ayder-plugins/venv-tools)
```

Shows both global and project-local, labeled accordingly.

### update-plugin

```
ayder update-plugin [name]
```

- With name: re-fetches that specific plugin from its recorded source
- Without name: updates all installed plugins
- For GitHub sources: downloads latest, compares version, replaces files, re-installs deps if changed
- For local sources: re-copies from original path
- Shows what changed (version diff)

## GitHub Download Mechanism

### URL Parsing

```
https://github.com/ayder/ayder-plugins/dbs-tools
         ↓              ↓              ↓
      host          owner/repo      subdirectory
```

**Parsing algorithm:** The first two path segments after `github.com` are always `owner/repo`. Everything after is the subdirectory path. If there are only two segments, the plugin is at the repo root.

Examples:
- `https://github.com/ayder/ayder-plugins/dbs-tools` — repo `ayder/ayder-plugins`, path `dbs-tools`
- `https://github.com/ayder/ayder-plugins/tools/dbs-tools` — repo `ayder/ayder-plugins`, path `tools/dbs-tools`
- `https://github.com/user/my-single-plugin` — repo `user/my-single-plugin`, path `/` (root)

GitHub tree/blob URLs are also supported by stripping `/tree/<branch>/` or `/blob/<branch>/` from the path:
- `https://github.com/ayder/ayder-plugins/tree/main/dbs-tools` — repo `ayder/ayder-plugins`, path `dbs-tools`

### Download Flow

1. Resolve default branch: `GET /repos/{owner}/{repo}` -> `default_branch`
2. Get latest commit SHA: `GET /repos/{owner}/{repo}/commits/{branch}` -> record in `plugins.json`
3. List directory contents: `GET /repos/{owner}/{repo}/contents/{path}?ref={branch}`
4. Download each file recursively

### Authentication
- Public repos: no auth (60 req/hr rate limit)
- Private repos: `GITHUB_TOKEN` env var, passed as `Authorization: Bearer` header

### Error Handling
- 404: "Plugin not found at this URL"
- 403 rate limit: "GitHub API rate limited. Set GITHUB_TOKEN for higher limits"
- Network error: "Could not reach GitHub. For local install, use a file path instead"

### Implementation
Uses `urllib.request` from stdlib — no additional dependencies.

## Runtime Integration

### Loading Pipeline

Plugin loading happens in two phases to solve the chicken-and-egg problem (`TOOL_DEFINITIONS` is populated at import time, but project path is only known at runtime):

**Phase 1 — Import time (definition.py):**
1. `_discover_definitions()` — builtins from `tools/builtins/` (unchanged)
2. `_discover_global_plugins()` — load from `~/.ayder/plugins/` (path is known statically)
3. `TOOL_DEFINITIONS = builtins + global_plugins`

**Phase 2 — Runtime (in `create_default_registry()`):**
1. `project_ctx` is now available
2. `_discover_project_plugins(project_path)` — load from `<project>/.ayder/plugins/`
3. For each project plugin: add its directory to `sys.path`, resolve `func_ref` to callable, remove from `sys.path`
4. Validate no tool-name conflicts against `TOOL_DEFINITIONS` + any already-registered dynamic definitions
5. Register via `register_dynamic_tool(td, resolved_handler)` for each tool

**External plugin loading steps (both phases):**
1. Scan plugin directories
2. Read `plugin.toml` for each
3. Check API version compatibility — skip with warning if incompatible
4. Check for tool-name conflicts — error if found
5. Add plugin directory to `sys.path`
6. Import `TOOL_DEFINITIONS` from the definitions file declared in `plugin.toml`
7. Resolve `func_ref` eagerly and store resolved callable in `_plugin_handlers` side-table
8. Remove plugin directory from `sys.path`

For Phase 1 (global plugins), `create_default_registry()` looks up pre-resolved handlers from `_plugin_handlers` instead of calling `_resolve_func_ref()`. For Phase 2 (project plugins), resolution and registration happen together in `create_default_registry()`.

### Tag System Integration

External plugins use the existing tag system. Their tools appear in `TOOL_DEFINITIONS` and are automatically visible to the `/plugin` TUI command. Enabled by default when installed. Users toggle with `/plugin` as usual.

### Multi-Select Plugin Screen

New `CLIMultiSelectScreen` class in `tui/screens.py`:
- **Space** toggles the highlighted item on/off (checkbox style `[x]` / `[ ]`)
- **Up/Down** navigates
- **Enter** confirms selections and dismisses with the set of enabled values
- **Esc** cancels without changes (returns `None`, consistent with `CLISelectScreen`)
- Hint bar: `↑↓ navigate, Space to toggle, Enter to confirm, Esc to cancel`
- `CLISelectScreen` remains unchanged for other commands

The `/plugin` handler in `commands.py` switches from `CLISelectScreen` to `CLIMultiSelectScreen`. On dismiss (Enter), receives the full set of enabled tags and applies to `config.tool_tags`. On cancel (Esc), no changes are made.

## File Changes

### New Files (ayder-cli)

| File | Purpose |
|------|---------|
| `src/ayder_cli/tools/plugin_api.py` | `PLUGIN_API_VERSION`, `PLUGIN_API_MIN_VERSION` |
| `src/ayder_cli/tools/plugin_manager.py` | Install, uninstall, update, list, load plugins |
| `src/ayder_cli/tools/plugin_github.py` | GitHub API download + URL parsing |

### Modified Files (ayder-cli)

| File | Change |
|------|--------|
| `src/ayder_cli/cli.py` | Add `install-plugin`, `uninstall-plugin`, `list-plugins`, `update-plugin` subcommands |
| `src/ayder_cli/tools/definition.py` | `_discover_definitions()` merges global plugin definitions via `_discover_global_plugins()` |
| `src/ayder_cli/tools/registry.py` | `create_default_registry()` loads project plugins, uses `_plugin_handlers` for global plugin callables |
| `src/ayder_cli/cli_runner.py` | `_run_temporal_queue_cli()` refactored to dynamically import from temporal plugin (if installed) |
| `src/ayder_cli/tui/screens.py` | Add `CLIMultiSelectScreen` class |
| `src/ayder_cli/tui/commands.py` | `handle_plugin()` uses `CLIMultiSelectScreen` |

### CLI Flag Changes

The `--temporal-task-queue` flag in `cli.py` depends on temporal service files that are moving to the plugin. This flag becomes a **plugin-provided CLI extension**: when the temporal plugin is installed globally, it registers the flag. When not installed, the flag is unavailable.

Implementation: `cli.py` checks if the temporal plugin is in the global `TOOL_DEFINITIONS` (populated at import time from global plugins only) before adding the flag to argparse. If not loaded, the flag is omitted silently.

**Limitation:** If the temporal plugin is installed as a project-local plugin only (not global), the `--temporal-task-queue` flag will not be available since project plugins load after argparse. This is an acceptable trade-off — temporal is a system-level capability and should be installed globally.

### Removed from ayder-cli

| Files | Destination Plugin |
|-------|--------------------|
| `builtins/dbs_tool.py` + `dbs_tool_definitions.py` | dbs-tools |
| `builtins/venv.py` + `venv_definitions.py` | venv-tools |
| `builtins/python_editor.py` + `python_editor_definitions.py` | python-tools |
| `builtins/temporal.py` + `temporal_definitions.py` | temporal-tools |
| `services/temporal_workflow_service.py` | temporal-tools |
| `services/temporal_client.py` | temporal-tools |
| `services/temporal_worker.py` | temporal-tools |
| `application/temporal_contract.py` | temporal-tools |
| `application/temporal_metadata.py` | temporal-tools |

### New External Repo (ayder-plugins at /Users/sinanalyuruk/Vscode/ayder-plugins/)

```
ayder-plugins/
├── dbs-tools/
│   ├── plugin.toml
│   ├── dbs_tool_definitions.py
│   └── dbs_tool.py
├── venv-tools/
│   ├── plugin.toml
│   ├── venv_definitions.py
│   └── venv.py
├── python-tools/
│   ├── plugin.toml
│   ├── python_editor_definitions.py
│   └── python_editor.py
└── temporal-tools/
    ├── plugin.toml
    ├── temporal_definitions.py
    ├── temporal.py
    ├── temporal_workflow_service.py
    ├── temporal_client.py
    ├── temporal_worker.py
    ├── temporal_contract.py
    └── temporal_metadata.py
```

## Testing Strategy

### Plugin system tests (stay in ayder-cli)
- Unit tests for `plugin_manager.py`: install, uninstall, update, list operations
- Unit tests for `plugin_github.py`: URL parsing, API response handling (mocked HTTP)
- Unit tests for `plugin_api.py`: version compatibility checks
- Integration test for plugin loading: create a fixture plugin directory, verify it loads into `TOOL_DEFINITIONS`
- Integration test for name conflict detection
- Test `CLIMultiSelectScreen` widget behavior

### Extracted tool tests (move to ayder-plugins)
- Existing tests for venv, dbs, python_editor, temporal tools move to the plugin repo
- Plugin repo has its own test suite that runs against `ayder_cli` as an installed dependency
- Tests import from the stable API (`ayder_cli.core.result`, `ayder_cli.core.context`, etc.)

### Existing ayder-cli tests
- Tests that import extracted tools directly will be removed
- Tests that exercise tools through the registry (integration tests) get a skip condition: `@pytest.mark.skipif` when the plugin is not installed
