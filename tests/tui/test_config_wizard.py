"""Config wizard screens: profile form, provider type, profiles list (/config, first run)."""

import importlib.util
import tomllib

import pytest
from textual.app import App
from textual.widgets import Button, Checkbox, Input, Label, Static

from ayder_cli.core import config as config_module
from ayder_cli.core.config import DEFAULTS
from ayder_cli.core.config_editor import PRESETS
from ayder_cli.tui import config_wizard as wiz
from ayder_cli.tui.config_wizard import ProfileFormScreen, SaveResult

CONFIG = """\
config_version = "2.0"

[app]
provider = "local"

[llm.local]
driver = "ollama"
base_url = "http://localhost:11434"
model = "qwen3:latest"
num_ctx = 65536

[llm.cloud]
driver = "openai"
base_url = "http://10.0.0.5:1234/v1"
api_key = "sk-test"
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
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / ".ayder" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_DIR", path.parent)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    return path


def hide_sdks(monkeypatch, *modules):
    real = importlib.util.find_spec

    def fake(name, *a, **k):
        return None if name in modules else real(name, *a, **k)

    monkeypatch.setattr("importlib.util.find_spec", fake)


class Host(App):
    """Pushes one screen on mount and records what it dismisses with."""

    def __init__(self, make_screen):
        super().__init__()
        self._make_screen = make_screen
        self.results: list = []

    def on_mount(self) -> None:
        self.push_screen(self._make_screen(), self.results.append)


def data(path):
    return tomllib.loads(path.read_text(encoding="utf-8"))


def preset_form(key, *, name=None, first_run=False):
    preset = PRESETS[key]
    return lambda: ProfileFormScreen(
        name=name or preset.key,
        values=wiz.preset_values(preset),
        title=f"Add profile - {preset.label}",
        first_run=first_run,
    )


def edit_form(name, *, is_default=False, first_run=False):
    from ayder_cli.core import config_editor as editor

    return lambda: ProfileFormScreen(
        name=name,
        values=editor.get_profile(editor.load_document(), name),
        editing=True,
        is_default=is_default,
        first_run=first_run,
        title=f"Edit profile '{name}'",
    )


def text_of(screen, selector) -> str:
    return str(screen.query_one(selector, Static).render())


async def save(pilot, screen):
    screen.query_one("#save", Button).press()
    await pilot.pause()
    await pilot.pause()


# --- Step 6: ProfileFormScreen ---------------------------------------------


@pytest.mark.anyio
async def test_claude_preset_form(config_path):
    app = Host(preset_form("anthropic", name="claude2"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#model", Input).value == DEFAULTS["anthropic"]["model"]
        assert screen.query_one("#api-key", Input).password is True
        assert not screen.query("#host")
        assert not screen.query("#fetch")
        assert screen.query_one("#adv-num_ctx", Input).value == str(DEFAULTS["anthropic"]["num_ctx"])
        assert {w.id for w in screen.query(".advanced-field")} == {
            "adv-num_ctx", "adv-max_output_tokens", "adv-stop_sequences",
        }


@pytest.mark.anyio
async def test_ollama_preset_form(config_path):
    app = Host(preset_form("ollama"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#host", Input).value == "http://localhost"
        assert screen.query_one("#port", Input).value == "11434"
        assert screen.query_one("#path", Input).value == ""
        assert not screen.query("#api-key")
        assert "OLLAMA_API_KEY" in text_of(screen, "#ollama-key-note")
        assert {w.id for w in screen.query(".advanced-field")} == {
            "adv-num_ctx", "adv-think", "adv-reasoning_effort",
        }


@pytest.mark.anyio
async def test_url_preview_follows_the_fields(config_path):
    app = Host(preset_form("openai", name="lm"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#host", Input).value = "http://10.1.1.1"
        screen.query_one("#port", Input).value = "8080"
        screen.query_one("#path", Input).value = "v1"
        await pilot.pause()
        assert "http://10.1.1.1:8080/v1" in text_of(screen, "#url-preview")

        screen.query_one("#port", Input).value = "abc"
        await pilot.pause()
        assert "port" in text_of(screen, "#url-preview")


@pytest.mark.anyio
async def test_valid_save_writes_the_profile(config_path):
    app = Host(preset_form("ollama", name="ollama"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#model", Input).value = "gemma4:31b"
        await save(pilot, screen)

    assert app.results == [SaveResult("ollama", False, None)]
    assert data(config_path)["llm"]["ollama"] == {
        "driver": "ollama",
        "base_url": "http://localhost:11434",
        "model": "gemma4:31b",
        "num_ctx": DEFAULTS["openai"]["num_ctx"],
    }
    assert data(config_path)["app"]["provider"] == "local"


@pytest.mark.anyio
async def test_make_default_writes_the_provider(config_path):
    app = Host(preset_form("ollama", name="ollama2"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#model", Input).value = "m"
        screen.query_one("#make-default", Checkbox).value = True
        await save(pilot, screen)

    assert app.results == [SaveResult("ollama2", True, None)]
    assert data(config_path)["app"]["provider"] == "ollama2"


@pytest.mark.anyio
async def test_first_run_checks_make_default(config_path):
    app = Host(preset_form("ollama", first_run=True))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        assert app.screen.query_one("#make-default", Checkbox).value is True


@pytest.mark.anyio
async def test_empty_advanced_fields_are_not_written(config_path):
    app = Host(preset_form("anthropic", name="claude2"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#api-key", Input).value = "sk-ant"
        screen.query_one("#adv-num_ctx", Input).value = ""
        await save(pilot, screen)

    assert data(config_path)["llm"]["claude2"] == {
        "driver": "anthropic",
        "api_key": "sk-ant",
        "model": DEFAULTS["anthropic"]["model"],
    }


@pytest.mark.anyio
async def test_edit_prefills_and_clearing_a_field_removes_the_key(config_path):
    app = Host(edit_form("cloud"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query_one("#name", Input).disabled is True
        assert (
            screen.query_one("#host", Input).value,
            screen.query_one("#port", Input).value,
            screen.query_one("#path", Input).value,
        ) == ("http://10.0.0.5", "1234", "/v1")
        assert screen.query_one("#api-key", Input).value == "sk-test"
        screen.query_one("#adv-num_ctx", Input).value = ""
        screen.query_one("#adv-stop_sequences", Input).value = "</s>, END"
        await save(pilot, screen)

    assert app.results == [SaveResult("cloud", False, None)]
    assert data(config_path)["llm"]["cloud"] == {
        "driver": "openai",
        "base_url": "http://10.0.0.5:1234/v1",
        "api_key": "sk-test",
        "model": "big-model",
        "skills": "none",
        "stop_sequences": ["</s>", "END"],
    }


@pytest.mark.anyio
async def test_invalid_input_is_shown_and_nothing_is_written(config_path):
    app = Host(preset_form("openai", name="lm"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#host", Input).value = "localhost"
        screen.query_one("#api-key", Input).value = "x"
        screen.query_one("#model", Input).value = "m"
        await save(pilot, screen)
        assert "base_url" in text_of(screen, "#error")
        assert app.screen is screen

    assert app.results == []
    assert config_path.read_text(encoding="utf-8") == CONFIG


@pytest.mark.anyio
async def test_model_is_required(config_path):
    app = Host(preset_form("ollama", name="ollama"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await save(pilot, app.screen)
        assert "Model" in text_of(app.screen, "#error")
    assert config_path.read_text(encoding="utf-8") == CONFIG


@pytest.mark.anyio
async def test_duplicate_name_is_refused(config_path):
    app = Host(preset_form("ollama", name="cloud"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        app.screen.query_one("#model", Input).value = "m"
        await save(pilot, app.screen)
        assert "already exists" in text_of(app.screen, "#error")
    assert config_path.read_text(encoding="utf-8") == CONFIG


@pytest.mark.anyio
async def test_missing_sdk_disables_make_default(config_path, monkeypatch):
    hide_sdks(monkeypatch, "anthropic")
    app = Host(edit_form("anthropic", first_run=True))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        box = screen.query_one("#make-default", Checkbox)
        assert box.disabled is True and box.value is False
        assert "pip install ayder-cli[anthropic]" in text_of(screen, "#install-hint")


@pytest.mark.anyio
async def test_build_failure_on_the_default_profile_is_refused(config_path):
    config_path.write_text(CONFIG.replace('provider = "local"', 'provider = "cloud"'), encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")
    app = Host(edit_form("cloud", is_default=True))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#api-key", Input).value = ""
        await save(pilot, screen)
        assert "api_key" in text_of(screen, "#error")

    assert app.results == []
    assert config_path.read_text(encoding="utf-8") == before


@pytest.mark.anyio
async def test_build_failure_on_another_profile_saves_with_a_warning(config_path):
    app = Host(edit_form("cloud"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#api-key", Input).value = ""
        await save(pilot, screen)

    [result] = app.results
    assert (result.name, result.make_default) == ("cloud", False)
    assert result.warning and "api_key" in result.warning
    assert data(config_path)["llm"]["cloud"]["api_key"] == ""


# --- Step 7: Fetch models ----------------------------------------------------

import httpx  # noqa: E402
import openai  # noqa: E402
from textual.widgets import OptionList  # noqa: E402

from ayder_cli.providers import evren, provider_orchestrator  # noqa: E402
from ayder_cli.providers.evren import EvrenTerms  # noqa: E402
from ayder_cli.tui.config_wizard import ModelPickerScreen  # noqa: E402
from ayder_cli.tui.screens import EvrenTermsScreen  # noqa: E402

EVREN_URL = "https://evren-llmapi.ssyz.org.tr/v1"


class FakeProvider:
    """list_models() answers from a queue; an exception in it is raised."""

    def __init__(self, answers):
        self.answers = answers
        self.configs = []

    async def list_models(self):
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


def fake_create(monkeypatch, answers):
    provider = FakeProvider(answers)

    def create(cfg, interaction_sink=None):
        provider.configs.append(cfg)
        return provider

    monkeypatch.setattr(provider_orchestrator, "create", create)
    return provider


def picker_rows(picker):
    option_list = picker.query_one("#model-options", OptionList)
    return [
        str(option_list.get_option_at_index(i).prompt).split("  (current)")[0]
        for i in range(option_list.option_count)
    ]


async def fetch(app, pilot):
    app.screen.query_one("#fetch", Button).press()
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


@pytest.mark.anyio
async def test_fetch_opens_the_model_picker_and_fills_the_pick(config_path, monkeypatch):
    provider = fake_create(monkeypatch, [["qwen3:32b", "llama3"]])
    app = Host(preset_form("ollama", name="ollama"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        form = app.screen
        await fetch(app, pilot)
        picker = app.screen
        assert isinstance(picker, ModelPickerScreen)
        assert picker_rows(picker) == ["llama3", "qwen3:32b"]
        await pilot.press("down", "enter")
        await pilot.pause()
        assert app.screen is form
        assert form.query_one("#model", Input).value == "qwen3:32b"
        assert "qwen3:32b" in text_of(form, "#fetch-status")

    assert provider.configs[0].base_url == "http://localhost:11434"
    assert provider.configs[0].driver == "ollama"


@pytest.mark.anyio
async def test_fetch_with_no_models(config_path, monkeypatch):
    fake_create(monkeypatch, [[]])
    app = Host(preset_form("ollama", name="ollama"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await fetch(app, pilot)
        assert isinstance(app.screen, ProfileFormScreen)
        assert "No models returned" in text_of(app.screen, "#fetch-status")


@pytest.mark.anyio
async def test_fetch_shows_api_errors(config_path, monkeypatch):
    request = httpx.Request("GET", "http://10.0.0.5:1234/v1/models")
    fake_create(monkeypatch, [openai.APIConnectionError(request=request)])
    app = Host(edit_form("cloud"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await fetch(app, pilot)
        assert "Connection error" in text_of(app.screen, "#fetch-status")
        assert str(app.screen.query_one("#fetch", Button).label) == "Fetch models"


@pytest.mark.anyio
async def test_fetch_survives_an_unexpected_error(config_path, monkeypatch):
    fake_create(monkeypatch, [RuntimeError("driver blew up")])
    app = Host(edit_form("cloud"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await fetch(app, pilot)
        assert "driver blew up" in text_of(app.screen, "#fetch-status")
        assert isinstance(app.screen, ProfileFormScreen)
    assert app.return_code in (0, None)


@pytest.mark.anyio
async def test_fetch_reports_form_errors_without_fetching(config_path, monkeypatch):
    provider = fake_create(monkeypatch, [["x"]])
    app = Host(edit_form("cloud"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        app.screen.query_one("#port", Input).value = "abc"
        await fetch(app, pilot)
        assert "port" in text_of(app.screen, "#fetch-status")
    assert provider.configs == []


def terms_error():
    request = httpx.Request("GET", f"{EVREN_URL}/models")
    return openai.PermissionDeniedError(
        "terms", response=httpx.Response(403, request=request),
        body={"code": "terms_not_accepted", "message": "accept the terms"},
    )


@pytest.fixture
def evren_terms(monkeypatch):
    calls = []

    async def fetch_terms(client):
        calls.append(("fetch", None))
        return EvrenTerms(1, "# Terms\n\nArticle 1.")

    async def accept_terms(client, version):
        calls.append(("accept", version))
        return version

    monkeypatch.setattr(evren, "fetch_terms", fetch_terms)
    monkeypatch.setattr(evren, "accept_terms", accept_terms)
    return calls


def evren_form():
    values = wiz.preset_values(PRESETS["evren"])
    values["api_key"] = "sk-evren"
    return lambda: ProfileFormScreen(name="evren2", values=values, title="Add profile - Evren")


@pytest.mark.anyio
async def test_fetch_on_evren_asks_for_the_terms_and_refetches(config_path, monkeypatch, evren_terms):
    fake_create(monkeypatch, [terms_error(), ["deepseek-v4-flash", "dots-ocr"]])
    app = Host(evren_form())
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await fetch(app, pilot)
        assert isinstance(app.screen, EvrenTermsScreen)
        app.screen.query_one("#terms-approve", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, ModelPickerScreen)
        assert picker_rows(app.screen) == ["deepseek-v4-flash", "dots-ocr"]

    assert evren_terms == [("fetch", None), ("accept", 1)]


@pytest.mark.anyio
async def test_fetch_on_evren_deny_keeps_the_terms_unaccepted(config_path, monkeypatch, evren_terms):
    fake_create(monkeypatch, [terms_error()])
    app = Host(evren_form())
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        await fetch(app, pilot)
        app.screen.query_one("#terms-deny", Button).press()
        await pilot.pause()
        await pilot.pause()
        assert "not accepted" in text_of(app.screen, "#fetch-status")

    assert evren_terms == [("fetch", None)]


@pytest.mark.anyio
async def test_no_fetch_button_for_google(config_path):
    app = Host(preset_form("gemini", name="gemini2"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        assert not app.screen.query("#fetch")


# --- Step 8: ProviderTypeScreen ------------------------------------------------

from ayder_cli.tui.config_wizard import ProviderTypeScreen  # noqa: E402


def option_rows(option_list):
    return [option_list.get_option_at_index(i) for i in range(option_list.option_count)]


@pytest.mark.anyio
async def test_provider_type_lists_the_presets():
    app = Host(ProviderTypeScreen)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        options = option_rows(app.screen.query_one(OptionList))
        assert [o.id for o in options] == ["anthropic", "gemini", "evren", "ollama", "openai"]
        assert not any(o.disabled for o in options)
        assert "Claude" in str(options[0].prompt)
        await pilot.press("down", "down", "enter")
        await pilot.pause()
    assert app.results == ["evren"]


@pytest.mark.anyio
async def test_provider_type_disables_presets_without_their_sdk(monkeypatch):
    hide_sdks(monkeypatch, "anthropic")
    app = Host(ProviderTypeScreen)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        option_list = app.screen.query_one(OptionList)
        claude = option_list.get_option("anthropic")
        assert claude.disabled is True
        assert "pip install ayder-cli[anthropic]" in str(claude.prompt)
        assert option_list.highlighted == 1
        # The cursor never lands on the disabled preset: up wraps past it to the
        # last one, and down from there wraps past it to Gemini.
        await pilot.press("up")
        assert option_list.highlighted == 4
        await pilot.press("down", "enter")
        await pilot.pause()
    assert app.results == ["gemini"]


@pytest.mark.anyio
async def test_provider_type_escape_cancels():
    app = Host(ProviderTypeScreen)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert app.results == [None]


# --- Step 9: ConfigWizardScreen (the profiles list) ---------------------------

from ayder_cli.tui.config_wizard import ConfigWizardScreen, ConfirmDeleteScreen  # noqa: E402


def wizard(switches, *, session="local", first_run=False):
    return lambda: ConfigWizardScreen(
        session_provider=lambda: session, on_switch=switches.append, first_run=first_run
    )


def profiles_list(app):
    return app.screen.query_one("#profiles", OptionList)


async def highlight(app, pilot, name):
    option_list = profiles_list(app)
    option_list.highlighted = option_list.get_option_index(name)
    await pilot.pause()


async def settle(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.pause()


@pytest.mark.anyio
async def test_wizard_lists_profiles_with_default_and_in_use(config_path):
    switches = []
    app = Host(wizard(switches, session="cloud"))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        rows = {o.id: str(o.prompt) for o in option_rows(profiles_list(app))}
        assert list(rows) == ["local", "cloud", "anthropic"]
        assert rows["local"].startswith("★")
        assert "(in use)" in rows["cloud"] and not rows["cloud"].startswith("★")
        assert "big-model" in rows["cloud"]
        assert "pip install" not in rows["anthropic"]


@pytest.mark.anyio
async def test_wizard_shows_the_install_hint_for_a_missing_sdk(config_path, monkeypatch):
    hide_sdks(monkeypatch, "anthropic")
    app = Host(wizard([]))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        prompt = str(profiles_list(app).get_option("anthropic").prompt)
        assert "pip install ayder-cli[anthropic]" in prompt


@pytest.mark.anyio
async def test_wizard_add_saves_and_refreshes(config_path):
    switches = []
    app = Host(wizard(switches))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await pilot.press("a")
        await settle(app, pilot)
        assert isinstance(app.screen, ProviderTypeScreen)
        await pilot.press("down", "down", "down", "enter")  # Ollama
        await settle(app, pilot)
        form = app.screen
        assert isinstance(form, ProfileFormScreen)
        assert form.query_one("#name", Input).value == "ollama"
        form.query_one("#model", Input).value = "gemma4:31b"
        await save(pilot, form)
        await settle(app, pilot)
        assert isinstance(app.screen, ConfigWizardScreen)
        assert "ollama" in [o.id for o in option_rows(profiles_list(app))]
        assert "Saved 'ollama'" in text_of(app.screen, "#status")

    assert switches == []
    assert data(config_path)["llm"]["ollama"]["model"] == "gemma4:31b"


@pytest.mark.anyio
async def test_wizard_add_with_make_default_switches(config_path):
    switches = []
    app = Host(wizard(switches))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await pilot.press("a")
        await settle(app, pilot)
        await pilot.press("down", "down", "down", "enter")
        await settle(app, pilot)
        form = app.screen
        form.query_one("#model", Input).value = "m"
        form.query_one("#make-default", Checkbox).value = True
        await save(pilot, form)
        await settle(app, pilot)

    assert switches == ["ollama"]
    assert data(config_path)["app"]["provider"] == "ollama"


@pytest.mark.anyio
async def test_wizard_add_on_a_seeded_placeholder_edits_it(config_path):
    from ayder_cli.core.config_migration import render_v2_config

    config_path.write_text(render_v2_config(DEFAULTS), encoding="utf-8")
    app = Host(wizard([], session="openai", first_run=True))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await pilot.press("a")
        await settle(app, pilot)
        await pilot.press("enter")  # Claude
        await settle(app, pilot)
        form = app.screen
        assert isinstance(form, ProfileFormScreen)
        assert form.query_one("#name", Input).value == "anthropic"
        assert form.query_one("#name", Input).disabled is True
        form.query_one("#api-key", Input).value = "sk-ant-real"
        form.query_one("#make-default", Checkbox).value = False
        await save(pilot, form)
        await settle(app, pilot)

    llm = data(config_path)["llm"]
    assert llm["anthropic"]["api_key"] == "sk-ant-real"
    assert "anthropic2" not in llm and "claude" not in llm


@pytest.mark.anyio
async def test_wizard_edit_of_the_session_profile_switches(config_path):
    switches = []
    app = Host(wizard(switches, session="cloud"))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "cloud")
        await pilot.press("e")
        await settle(app, pilot)
        form = app.screen
        assert form.query_one("#name", Input).value == "cloud"
        form.query_one("#model", Input).value = "bigger-model"
        await save(pilot, form)
        await settle(app, pilot)

    assert switches == ["cloud"]
    assert data(config_path)["llm"]["cloud"]["model"] == "bigger-model"


@pytest.mark.anyio
async def test_wizard_enter_edits_and_cancel_changes_nothing(config_path):
    switches = []
    app = Host(wizard(switches))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "anthropic")
        await pilot.press("enter")
        await settle(app, pilot)
        assert app.screen.query_one("#name", Input).value == "anthropic"
        await pilot.press("escape")
        await settle(app, pilot)
        assert isinstance(app.screen, ConfigWizardScreen)

    assert switches == []
    assert config_path.read_text(encoding="utf-8") == CONFIG


@pytest.mark.anyio
async def test_wizard_set_default(config_path):
    switches = []
    app = Host(wizard(switches))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "cloud")
        await pilot.press("s")
        await settle(app, pilot)
        assert str(profiles_list(app).get_option("cloud").prompt).startswith("★")

    assert switches == ["cloud"]
    assert data(config_path)["app"]["provider"] == "cloud"


@pytest.mark.anyio
async def test_wizard_set_default_refuses_a_missing_sdk(config_path, monkeypatch):
    hide_sdks(monkeypatch, "anthropic")
    switches = []
    app = Host(wizard(switches))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "anthropic")
        await pilot.press("s")
        await settle(app, pilot)
        assert "pip install ayder-cli[anthropic]" in text_of(app.screen, "#status")

    assert switches == []
    assert config_path.read_text(encoding="utf-8") == CONFIG


@pytest.mark.anyio
async def test_wizard_set_default_refuses_a_profile_that_does_not_build(config_path):
    config_path.write_text(CONFIG.replace('api_key = "sk-test"', 'api_key = ""'), encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")
    switches = []
    app = Host(wizard(switches))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "cloud")
        await pilot.press("s")
        await settle(app, pilot)
        assert "api_key" in text_of(app.screen, "#status")

    assert switches == []
    assert config_path.read_text(encoding="utf-8") == before


@pytest.mark.anyio
async def test_wizard_delete_refused_shows_the_reason(config_path):
    app = Host(wizard([]))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "local")
        await pilot.press("d")
        await settle(app, pilot)
        assert isinstance(app.screen, ConfigWizardScreen)
        assert "default" in text_of(app.screen, "#status")

    assert config_path.read_text(encoding="utf-8") == CONFIG


@pytest.mark.anyio
async def test_wizard_delete_confirmed(config_path):
    app = Host(wizard([]))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "anthropic")
        await pilot.press("d")
        await settle(app, pilot)
        assert isinstance(app.screen, ConfirmDeleteScreen)
        await pilot.press("y")
        await settle(app, pilot)
        assert [o.id for o in option_rows(profiles_list(app))] == ["local", "cloud"]

    assert "anthropic" not in data(config_path)["llm"]


@pytest.mark.anyio
async def test_wizard_delete_declined(config_path):
    app = Host(wizard([]))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "anthropic")
        await pilot.press("d")
        await settle(app, pilot)
        await pilot.press("n")
        await settle(app, pilot)
        assert isinstance(app.screen, ConfigWizardScreen)

    assert config_path.read_text(encoding="utf-8") == CONFIG


@pytest.mark.anyio
async def test_wizard_escape_closes(config_path):
    app = Host(wizard([]))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        await pilot.press("escape")
        await settle(app, pilot)
    assert app.results == [None]


@pytest.mark.anyio
async def test_wizard_first_run(config_path):
    app = Host(wizard([], first_run=True))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        assert "Welcome" in str(app.screen.query_one("#wizard-title", Label).render())
        await pilot.press("a")
        await settle(app, pilot)
        await pilot.press("down", "down", "down", "enter")
        await settle(app, pilot)
        assert app.screen.query_one("#make-default", Checkbox).value is True


# --- Review fixes ---------------------------------------------------------------

UNTOUCHED = """\
[app]
provider = "lmstudio"

[llm.ollama]
base_url = "http://localhost:11434/"
model = "qwen3:latest"  # no driver line: Config infers ollama from the name

[llm.lmstudio]
driver = "openai"
base_url = "http://localhost:1234/v1"
model = "local-model"
stop_sequences = ["a,b", " x "]
reasoning_effort = "default"
"""


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["ollama", "lmstudio"])
async def test_edit_saved_untouched_keeps_the_bytes(config_path, name):
    config_path.write_text(UNTOUCHED, encoding="utf-8")
    switches = []
    app = Host(wizard(switches, session="lmstudio"))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, name)
        await pilot.press("e")
        await settle(app, pilot)
        form = app.screen
        if name == "ollama":
            assert "Driver: ollama" in str(form.query_one(".description", Label).render())
            assert not form.query("#api-key")
        await save(pilot, form)
        await settle(app, pilot)
        assert isinstance(app.screen, ConfigWizardScreen)

    assert config_path.read_text(encoding="utf-8") == UNTOUCHED


@pytest.mark.anyio
async def test_new_keyless_openai_compatible_profile_can_be_the_default(config_path):
    switches = []
    app = Host(wizard(switches, first_run=True))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await pilot.press("a")
        await settle(app, pilot)
        await pilot.press("up", "enter")  # OpenAI-compatible (wraps to the last preset)
        await settle(app, pilot)
        form = app.screen
        assert form.query_one("#make-default", Checkbox).value is True
        form.query_one("#port", Input).value = "1234"
        form.query_one("#model", Input).value = "local-model"
        await save(pilot, form)
        await settle(app, pilot)

    profile = data(config_path)["llm"]["openai"]
    assert "api_key" not in profile
    assert profile["base_url"] == "http://localhost:1234/v1"
    assert data(config_path)["app"]["provider"] == "openai"
    assert switches == ["openai"]


@pytest.mark.anyio
async def test_saving_the_session_profile_broken_keeps_the_session(config_path):
    switches = []
    app = Host(wizard(switches, session="cloud"))
    async with app.run_test(size=(110, 60)) as pilot:
        await settle(app, pilot)
        await highlight(app, pilot, "cloud")
        await pilot.press("e")
        await settle(app, pilot)
        app.screen.query_one("#api-key", Input).value = ""
        await save(pilot, app.screen)
        await settle(app, pilot)
        status = text_of(app.screen, "#status")
        assert "cannot be used yet" in status and "keeps its current settings" in status

    assert switches == []
    assert data(config_path)["llm"]["cloud"]["api_key"] == ""


@pytest.mark.anyio
async def test_closing_the_form_during_a_fetch(config_path, monkeypatch):
    import asyncio

    class Hanging:
        async def list_models(self):
            await asyncio.Event().wait()

    monkeypatch.setattr(provider_orchestrator, "create", lambda cfg, interaction_sink=None: Hanging())
    app = Host(preset_form("ollama", name="ollama"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        app.screen.query_one("#fetch", Button).press()
        await pilot.pause()
        assert str(app.screen.query_one("#fetch", Button).label) == "Fetching…"
        await pilot.press("escape")
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, ProfileFormScreen)
    assert app.results == [None]
    assert app.return_code in (0, None)


# --- Live-test cosmetics (2026-11-21) ----------------------------------------

from ayder_cli.themes import get_theme  # noqa: E402


@pytest.mark.anyio
async def test_wizard_rows_align_name_driver_and_model_columns(config_path):
    app = Host(wizard([], session="cloud"))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        rows = [str(o.prompt).split("\n")[0] for o in option_rows(profiles_list(app))]

    # "★ " / "  " marker, names padded to "anthropic" (9), drivers to "anthropic" (9).
    assert rows == [
        "★ local      ollama     qwen3:latest",
        "  cloud      openai     big-model  (in use)",
        "  anthropic  anthropic  claude-sonnet-5-5",
    ]


@pytest.mark.anyio
async def test_wizard_install_hint_sits_under_the_name_column(config_path, monkeypatch):
    hide_sdks(monkeypatch, "anthropic")
    app = Host(wizard([]))
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        prompt = str(profiles_list(app).get_option("anthropic").prompt)
    assert prompt.split("\n")[1] == "  Install it with: pip install ayder-cli[anthropic]"


@pytest.mark.anyio
async def test_wizard_list_has_a_blank_line_under_the_description(config_path):
    app = Host(wizard([]))
    app.CSS = get_theme("ayder").css
    async with app.run_test(size=(110, 50)) as pilot:
        await settle(app, pilot)
        description = app.screen.query_one(".description", Static)
        assert profiles_list(app).region.y >= description.region.bottom + 1


@pytest.mark.parametrize("theme", ["ayder", "claude"])
def test_wizard_hint_is_not_greyed_out(theme):
    css = get_theme(theme).css
    block = css.split(".config-modal .hint {", 1)[1].split("}", 1)[0]
    assert "dim" not in block
    assert "ansi_bright_black" not in block and "#666680" not in block



# --- Model picker (live-test redesign, 2026-11-21) ---------------------------

MODELS = ["qwen3.6-plus", "deepseek-v4.1-flash", "qwen3.8-max-preview", "glm-5.2", "kimi-k2.7"]


def picker(current=""):
    return lambda: ModelPickerScreen(MODELS, current=current, title="Pick a model for 'alibaba'")


@pytest.mark.anyio
async def test_model_picker_lists_sorted_and_marks_the_current_model():
    app = Host(picker(current="qwen3.8-max-preview"))
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        options = screen.query_one("#model-options", OptionList)
        assert picker_rows(screen) == sorted(MODELS)
        assert options.highlighted_option.id == "qwen3.8-max-preview"
        assert "(current)" in str(options.highlighted_option.prompt)
        assert screen.query_one("#model-filter", Input).has_focus
        assert text_of(screen, "#model-count") == "5 models"
        await pilot.press("enter")
        await pilot.pause()
    assert app.results == ["qwen3.8-max-preview"]


@pytest.mark.anyio
async def test_model_picker_filters_as_you_type():
    app = Host(picker())
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press(*"QWEN")
        await pilot.pause()
        screen = app.screen
        assert picker_rows(screen) == ["qwen3.6-plus", "qwen3.8-max-preview"]
        assert text_of(screen, "#model-count") == "2 of 5 models"
        await pilot.press("down", "enter")
        await pilot.pause()
    assert app.results == ["qwen3.8-max-preview"]


@pytest.mark.anyio
async def test_model_picker_no_match():
    app = Host(picker())
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press(*"zzz")
        await pilot.pause()
        assert picker_rows(app.screen) == []
        assert text_of(app.screen, "#model-count") == "No model matches 'zzz'."
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ModelPickerScreen)
    assert app.results == []


@pytest.mark.anyio
async def test_model_picker_escape_keeps_the_model(config_path, monkeypatch):
    fake_create(monkeypatch, [MODELS])
    app = Host(edit_form("cloud"))
    async with app.run_test(size=(100, 60)) as pilot:
        await pilot.pause()
        form = app.screen
        await fetch(app, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is form
        assert form.query_one("#model", Input).value == "big-model"


@pytest.mark.anyio
@pytest.mark.parametrize("theme", ["ayder", "claude"])
@pytest.mark.parametrize("rows", [24, 30, 50])
async def test_model_picker_fits_on_screen(theme, rows):
    many = [f"vendor/model-{i:03d}" for i in range(300)]
    app = Host(lambda: ModelPickerScreen(many, current="vendor/model-150", title="Pick"))
    app.CSS = get_theme(theme).css
    async with app.run_test(size=(100, rows)) as pilot:
        await pilot.pause()
        screen = app.screen
        box = screen.query_one(".config-modal")
        assert screen.region.contains_region(box.region)
        options = screen.query_one("#model-options", OptionList)
        assert box.region.contains_region(options.region)
        highlighted = options.highlighted
        assert options.scroll_y <= highlighted < options.scroll_y + options.size.height
        # No empty rows under the hint: only the box's padding and border follow it.
        hint = screen.query(".hint").last()
        assert box.region.bottom - hint.region.bottom == 2


@pytest.mark.anyio
async def test_model_picker_shows_a_filter_label():
    app = Host(picker())
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        assert "Filter" in str(app.screen.query_one("#filter-label", Label).render())
