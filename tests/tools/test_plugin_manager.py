"""Tests for plugin manager — TOML parsing and validation."""

import pytest
from unittest.mock import patch

from ayder_cli.tools.plugin_manager import (
    parse_plugin_toml,
    PluginError,
)
from ayder_cli.tools.plugin_manager import (
    install_plugin_from_local,
    uninstall_plugin,
    list_installed_plugins,
    read_plugins_json,
)
from ayder_cli.tools.plugin_manager import (
    install_plugin_from_github,
    update_plugin,
    detect_source_type,
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
