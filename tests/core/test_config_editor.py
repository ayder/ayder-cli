"""Comment-preserving provider-profile edits of config.toml (config wizard)."""

import os
import stat
import tomllib

import pytest

from ayder_cli.core import config as config_module
from ayder_cli.core import config_editor as editor
from ayder_cli.core.config_editor import ProfileEditError, ProfileSummary

HAND_WRITTEN = """\
config_version = "2.0"

# My own notes about this file.
[app]
provider = "local"   # the session default
editor = "vim"

[ui]
theme = "ayder"
palette = "auto"

[retry]
max_attempts = 3

[llm.local]
driver = "ollama"
base_url = "http://localhost:11434"
model = "qwen3:latest"  # pulled 2026-11-01
num_ctx = 65536

[agents.reviewer]
provider = "cloud"
system_prompt = "Review code."

[llm.cloud]
driver = "openai"
base_url = "https://api.example.com/v1"
api_key = "sk-test"
# keep this model pinned
model = "big-model"
num_ctx = 131072
skills = "none"

[llm.anthropic]
driver = "anthropic"
api_key = ""
model = "claude-sonnet-5-5"
num_ctx = 200000
"""


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / ".ayder" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(HAND_WRITTEN, encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_DIR", path.parent)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    return path


def _without(text: str, block: str) -> str:
    assert block in text, f"{block!r} not in output"
    return text.replace(block, "", 1)


# --- Step 2: load, save, list, set default --------------------------------


def test_round_trip_is_byte_identical(config_path):
    doc = editor.load_document()
    editor.save_document(doc)

    assert config_path.read_text(encoding="utf-8") == HAND_WRITTEN


def test_list_profiles_in_file_order(config_path):
    profiles = editor.list_profiles(editor.load_document())

    assert profiles == [
        ProfileSummary("local", "ollama", "qwen3:latest", True),
        ProfileSummary("cloud", "openai", "big-model", False),
        ProfileSummary("anthropic", "anthropic", "claude-sonnet-5-5", False),
    ]


def test_get_profile_returns_plain_values(config_path):
    profile = editor.get_profile(editor.load_document(), "cloud")

    assert profile == {
        "driver": "openai",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "model": "big-model",
        "num_ctx": 131072,
        "skills": "none",
    }


def test_get_profile_unknown_name(config_path):
    with pytest.raises(ProfileEditError, match="nope"):
        editor.get_profile(editor.load_document(), "nope")


def test_set_default_changes_only_the_provider_line(config_path):
    doc = editor.load_document()
    editor.set_default(doc, "cloud")
    editor.save_document(doc)

    assert config_path.read_text(encoding="utf-8") == HAND_WRITTEN.replace(
        'provider = "local"   # the session default',
        'provider = "cloud"   # the session default',
    )


def test_set_default_creates_a_missing_app_table(config_path):
    config_path.write_text('[llm.only]\ndriver = "openai"\nmodel = "m"\n', encoding="utf-8")
    doc = editor.load_document()
    editor.set_default(doc, "only")
    editor.save_document(doc)

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["app"]["provider"] == "only"
    assert data["llm"]["only"] == {"driver": "openai", "model": "m"}


def test_set_default_unknown_profile(config_path):
    with pytest.raises(ProfileEditError, match="nope"):
        editor.set_default(editor.load_document(), "nope")


def test_save_is_atomic_when_the_replace_fails(config_path, monkeypatch):
    doc = editor.load_document()
    editor.set_default(doc, "cloud")

    def boom(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(editor.os, "replace", boom)
    with pytest.raises(ProfileEditError, match="No space left"):
        editor.save_document(doc)

    assert config_path.read_text(encoding="utf-8") == HAND_WRITTEN
    assert sorted(p.name for p in config_path.parent.iterdir()) == ["config.toml"]


def test_save_keeps_the_file_mode(config_path):
    os.chmod(config_path, 0o600)
    doc = editor.load_document()
    editor.set_default(doc, "cloud")
    editor.save_document(doc)

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

    os.chmod(config_path, 0o644)
    editor.save_document(editor.load_document())
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o644


def test_path_is_read_at_call_time(tmp_path, monkeypatch, config_path):
    other = tmp_path / "other.toml"
    other.write_text('[app]\nprovider = "x"\n\n[llm.x]\ndriver = "openai"\n', encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_PATH", other)

    doc = editor.load_document()
    assert [p.name for p in editor.list_profiles(doc)] == ["x"]
    editor.set_default(doc, "x")
    editor.save_document(doc)
    assert config_path.read_text(encoding="utf-8") == HAND_WRITTEN


def test_load_reports_a_malformed_file(config_path):
    config_path.write_text("[app\nprovider = ", encoding="utf-8")

    with pytest.raises(ProfileEditError, match="config.toml"):
        editor.load_document()


def test_load_seeds_a_missing_file(config_path):
    config_path.unlink()

    doc = editor.load_document()

    assert "openai" in [p.name for p in editor.list_profiles(doc)]
    assert config_path.exists()


# --- Step 3: add or update a profile, with validation ----------------------


def test_upsert_merges_into_an_existing_profile(config_path):
    doc = editor.load_document()
    editor.upsert_profile(
        doc, "cloud", {"model": "bigger-model", "max_output_tokens": 4096}, remove=("num_ctx",)
    )
    editor.save_document(doc)

    profile = tomllib.loads(config_path.read_text(encoding="utf-8"))["llm"]["cloud"]
    assert profile == {
        "driver": "openai",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "model": "bigger-model",
        "skills": "none",
        "max_output_tokens": 4096,
    }


def test_upsert_keeps_comments_inside_the_table(config_path):
    doc = editor.load_document()
    editor.upsert_profile(doc, "local", {"model": "qwen3:32b"})
    editor.upsert_profile(doc, "cloud", {"model": "other"})
    editor.save_document(doc)

    assert config_path.read_text(encoding="utf-8") == HAND_WRITTEN.replace(
        'model = "qwen3:latest"  # pulled 2026-11-01', 'model = "qwen3:32b"  # pulled 2026-11-01'
    ).replace('# keep this model pinned\nmodel = "big-model"', '# keep this model pinned\nmodel = "other"')


def test_upsert_leaves_unchanged_values_untouched(config_path):
    doc = editor.load_document()
    editor.upsert_profile(doc, "local", {"model": "qwen3:latest", "num_ctx": 65536})
    editor.save_document(doc)

    assert config_path.read_text(encoding="utf-8") == HAND_WRITTEN


def test_upsert_adds_a_profile_between_interleaved_tables(config_path):
    doc = editor.load_document()
    editor.upsert_profile(doc, "lm-studio", {"driver": "openai", "model": "m"})
    editor.save_document(doc)

    text = config_path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data["llm"]["lm-studio"] == {"driver": "openai", "model": "m"}
    added = '[llm.lm-studio]\ndriver = "openai"\nmodel = "m"\n\n'
    assert _without(text, added) == HAND_WRITTEN


def test_upsert_adds_a_profile_at_the_end_of_a_seeded_file(config_path):
    from ayder_cli.core.config import DEFAULTS
    from ayder_cli.core.config_migration import render_v2_config

    seeded = render_v2_config(DEFAULTS)
    config_path.write_text(seeded, encoding="utf-8")
    doc = editor.load_document()
    editor.upsert_profile(doc, "ollama", {"driver": "ollama", "model": "m"})
    editor.save_document(doc)

    text = config_path.read_text(encoding="utf-8")
    assert text == seeded + '\n[llm.ollama]\ndriver = "ollama"\nmodel = "m"\n'


def test_upsert_creates_the_llm_table(config_path):
    config_path.write_text('config_version = "2.0"\n\n[app]\nprovider = "x"\n', encoding="utf-8")
    doc = editor.load_document()
    editor.upsert_profile(doc, "x", {"driver": "openai", "model": "m"})
    editor.save_document(doc)

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert data["llm"] == {"x": {"driver": "openai", "model": "m"}}


@pytest.mark.parametrize("name", ["", "has space", "dot.ted", "ünï", "a/b"])
def test_upsert_rejects_names_that_are_not_bare_keys(config_path, name):
    with pytest.raises(ProfileEditError, match="name"):
        editor.upsert_profile(editor.load_document(), name, {"driver": "openai"})


def test_validate_returns_the_profile_config(config_path):
    cfg = editor.validate(editor.load_document(), active="cloud")

    assert (cfg.provider, cfg.driver, cfg.model, cfg.num_ctx) == (
        "cloud", "openai", "big-model", 131072,
    )


def test_validate_reports_field_errors_without_input_values(config_path):
    doc = editor.load_document()
    editor.upsert_profile(doc, "cloud", {"base_url": "sk-secret-looking"})

    with pytest.raises(ProfileEditError) as err:
        editor.validate(doc, active="cloud")

    message = str(err.value)
    assert message.startswith("base_url: ")
    assert "http://" in message
    assert "sk-secret-looking" not in message
    assert "sk-test" not in message


def test_validate_unknown_profile(config_path):
    with pytest.raises(ProfileEditError, match="nope"):
        editor.validate(editor.load_document(), active="nope")


# --- Step 4: delete rules ---------------------------------------------------


def test_delete_refuses_the_default_profile(config_path):
    with pytest.raises(ProfileEditError, match="default"):
        editor.delete_profile(editor.load_document(), "local", session_provider="anthropic")


def test_delete_refuses_the_session_profile(config_path):
    with pytest.raises(ProfileEditError, match="session"):
        editor.delete_profile(editor.load_document(), "anthropic", session_provider="anthropic")


def test_delete_refuses_a_profile_agents_use(config_path):
    with pytest.raises(ProfileEditError, match="reviewer"):
        editor.delete_profile(editor.load_document(), "cloud", session_provider="local")


def test_delete_refuses_the_last_profile(config_path):
    config_path.write_text('[llm.only]\ndriver = "openai"\n', encoding="utf-8")

    with pytest.raises(ProfileEditError, match="last"):
        editor.delete_profile(editor.load_document(), "only", session_provider=None)


def test_delete_unknown_profile(config_path):
    with pytest.raises(ProfileEditError, match="nope"):
        editor.delete_profile(editor.load_document(), "nope", session_provider=None)


def test_delete_removes_only_that_table(config_path):
    doc = editor.load_document()
    editor.delete_profile(doc, "anthropic", session_provider="local")
    editor.save_document(doc)

    # The blank line before the table belongs to the table above it and stays.
    removed = '[llm.anthropic]\ndriver = "anthropic"\napi_key = ""\nmodel = "claude-sonnet-5-5"\nnum_ctx = 200000\n'
    assert config_path.read_text(encoding="utf-8") == _without(HAND_WRITTEN, removed)


def test_delete_in_an_interleaved_layout_keeps_the_rest(config_path):
    text = HAND_WRITTEN.replace('[agents.reviewer]\nprovider = "cloud"', '[agents.reviewer]\nprovider = "local"')
    config_path.write_text(text, encoding="utf-8")
    doc = editor.load_document()
    editor.delete_profile(doc, "cloud", session_provider="local")
    editor.save_document(doc)

    removed = (
        '[llm.cloud]\ndriver = "openai"\nbase_url = "https://api.example.com/v1"\n'
        'api_key = "sk-test"\n# keep this model pinned\nmodel = "big-model"\n'
        'num_ctx = 131072\nskills = "none"\n\n'
    )
    after = config_path.read_text(encoding="utf-8")
    assert after == _without(text, removed)
    assert "cloud" not in tomllib.loads(after)["llm"]


# --- Step 5: presets, per-driver fields, URL helpers -----------------------

import importlib.util  # noqa: E402

from ayder_cli.core.config import DEFAULTS  # noqa: E402
from ayder_cli.providers import provider_orchestrator  # noqa: E402


def hide_sdks(monkeypatch, *modules):
    """Make the named SDK modules look uninstalled; keep everything else real."""
    real = importlib.util.find_spec

    def fake(name, *a, **k):
        return None if name in modules else real(name, *a, **k)

    monkeypatch.setattr("importlib.util.find_spec", fake)


def test_presets_come_from_defaults():
    p = editor.PRESETS
    assert list(p) == ["anthropic", "gemini", "evren", "ollama", "openai"]
    assert (p["anthropic"].label, p["anthropic"].driver, p["anthropic"].base_url) == (
        "Claude", "anthropic", None,
    )
    assert (p["anthropic"].model, p["anthropic"].num_ctx) == (
        DEFAULTS["anthropic"]["model"], DEFAULTS["anthropic"]["num_ctx"],
    )
    assert (p["gemini"].driver, p["gemini"].model, p["gemini"].num_ctx) == (
        "google", DEFAULTS["gemini"]["model"], DEFAULTS["gemini"]["num_ctx"],
    )
    evren = DEFAULTS["extra_llm_profiles"]["evren"]
    assert (p["evren"].driver, p["evren"].base_url, p["evren"].model, p["evren"].num_ctx) == (
        "openai", evren["base_url"], evren["model"], evren["num_ctx"],
    )
    assert (p["ollama"].driver, p["ollama"].base_url) == ("ollama", "http://localhost:11434")
    assert p["openai"].driver == "openai"
    assert p["openai"].label == "OpenAI-compatible"


def test_driver_fields():
    f = editor.driver_fields
    assert f("openai") == editor.DriverFields(
        True, True, ("num_ctx", "max_output_tokens", "reasoning_effort", "stop_sequences"), True
    )
    assert f("ollama") == editor.DriverFields(
        True, False, ("num_ctx", "think", "reasoning_effort"), True
    )
    assert f("anthropic") == editor.DriverFields(
        False, True, ("num_ctx", "max_output_tokens", "stop_sequences"), False
    )
    assert f("google") == editor.DriverFields(False, True, ("num_ctx", "max_output_tokens"), False)
    for other in ("deepseek", "qwen", "glm", "dashscope", "zhipu"):
        assert f(other) == editor.DriverFields(True, True, ("num_ctx",), False)


@pytest.mark.parametrize(
    "url, parts",
    [
        ("http://localhost:11434", ("http://localhost", "11434", "")),
        ("https://evren-llmapi.ssyz.org.tr/v1", ("https://evren-llmapi.ssyz.org.tr", "", "/v1")),
        ("http://10.0.0.5:1234/v1", ("http://10.0.0.5", "1234", "/v1")),
    ],
)
def test_base_url_round_trip(url, parts):
    assert editor.split_base_url(url) == parts
    assert editor.compose_base_url(*parts) == url


def test_compose_base_url_normalises():
    assert editor.compose_base_url(" http://h/ ", " 8080 ", "v1") == "http://h:8080/v1"
    assert editor.compose_base_url("http://h", "", "/") == "http://h"


@pytest.mark.parametrize("port", ["abc", "0", "70000", "-1", "1.5"])
def test_compose_base_url_rejects_bad_ports(port):
    with pytest.raises(ProfileEditError, match="port"):
        editor.compose_base_url("http://h", port, "/v1")


def test_compose_base_url_rejects_two_ports():
    with pytest.raises(ProfileEditError, match="port"):
        editor.compose_base_url("http://h:1234", "5678", "")


def test_compose_base_url_needs_a_host():
    with pytest.raises(ProfileEditError, match="[Hh]ost"):
        editor.compose_base_url("  ", "1234", "/v1")


def test_suggest_name(config_path):
    doc = editor.load_document()
    assert editor.suggest_name(doc, "ollama") == "ollama"
    assert editor.suggest_name(doc, "local") == "local2"
    editor.upsert_profile(doc, "local2", {"driver": "ollama"})
    assert editor.suggest_name(doc, "local") == "local3"


def test_placeholder_profile_matches_the_seeded_empty_key_profiles(config_path):
    from ayder_cli.core.config_migration import render_v2_config

    config_path.write_text(render_v2_config(DEFAULTS), encoding="utf-8")
    doc = editor.load_document()

    assert editor.placeholder_profile(doc, editor.PRESETS["anthropic"]) == "anthropic"
    assert editor.placeholder_profile(doc, editor.PRESETS["gemini"]) == "gemini"
    assert editor.placeholder_profile(doc, editor.PRESETS["evren"]) == "evren"
    # Seeded openai has api_key = "ollama"; no ollama profile is seeded.
    assert editor.placeholder_profile(doc, editor.PRESETS["openai"]) is None
    assert editor.placeholder_profile(doc, editor.PRESETS["ollama"]) is None


def test_placeholder_profile_ignores_filled_keys_and_other_drivers(config_path):
    doc = editor.load_document()
    editor.upsert_profile(doc, "anthropic", {"api_key": "sk-ant-real"})
    editor.upsert_profile(doc, "gemini", {"driver": "openai", "api_key": ""})

    assert editor.placeholder_profile(doc, editor.PRESETS["anthropic"]) is None
    assert editor.placeholder_profile(doc, editor.PRESETS["gemini"]) is None


def test_missing_extra_and_install_hint(monkeypatch):
    hide_sdks(monkeypatch, "anthropic", "google.genai")

    assert provider_orchestrator.missing_extra("anthropic") == "anthropic"
    assert provider_orchestrator.missing_extra("google") == "google"
    assert provider_orchestrator.missing_extra("openai") is None
    assert provider_orchestrator.missing_extra("ollama") is None
    assert provider_orchestrator.missing_extra("no-such-driver") is None
    assert editor.install_hint("anthropic") == "Install it with: pip install ayder-cli[anthropic]"
    assert editor.install_hint("openai") is None


def test_install_hint_none_when_installed():
    assert editor.install_hint("anthropic") is None
    assert editor.install_hint("google") is None


def test_check_buildable_ok_for_a_good_profile(config_path):
    assert editor.check_buildable(editor.load_document(), "cloud") is None
    assert editor.check_buildable(editor.load_document(), "local") is None


def test_check_buildable_reports_a_missing_sdk(config_path, monkeypatch):
    hide_sdks(monkeypatch, "anthropic")

    error = editor.check_buildable(editor.load_document(), "anthropic")

    assert error is not None and "pip install ayder-cli[anthropic]" in error


def test_check_buildable_reports_driver_errors(config_path):
    doc = editor.load_document()
    editor.upsert_profile(doc, "cloud", {"api_key": ""})
    editor.upsert_profile(doc, "anthropic", {"driver": "google"})
    editor.upsert_profile(doc, "local", {"base_url": "http://h:abc"})

    assert "api_key" in (editor.check_buildable(doc, "cloud") or "")
    assert "API key" in (editor.check_buildable(doc, "anthropic") or "")
    assert editor.check_buildable(doc, "local")
    assert editor.check_buildable(doc, "nope") == "No profile named 'nope'."


# --- Review fixes: the driver Config infers from the profile name -------------


def test_profile_without_driver_line_uses_the_inferred_driver(config_path):
    config_path.write_text(
        '[app]\nprovider = "ollama"\n\n[llm.ollama]\nmodel = "m"\n\n'
        '[llm.anthropic]\napi_key = ""\nmodel = "c"\n\n[llm.mine]\nmodel = "x"\n',
        encoding="utf-8",
    )
    doc = editor.load_document()

    assert [(p.name, p.driver) for p in editor.list_profiles(doc)] == [
        ("ollama", "ollama"), ("anthropic", "anthropic"), ("mine", "openai"),
    ]
    assert editor.profile_driver("ollama", editor.get_profile(doc, "ollama")) == "ollama"
    assert editor.placeholder_profile(doc, editor.PRESETS["anthropic"]) == "anthropic"
