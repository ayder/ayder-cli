"""Config wizard: provider profiles in config.toml (first run and ``/config``).

Screens:
- ``ConfigWizardScreen``: the profiles list (add, edit, delete, set default).
- ``ProviderTypeScreen``: picks the preset for a new profile.
- ``ProfileFormScreen``: adds or edits one ``[llm.<name>]`` profile.
- ``ModelPickerScreen``: picks one of the models "Fetch models" listed.
- ``ConfirmDeleteScreen``: yes/no before a delete.

All file access goes through ``core.config_editor``; errors are shown inline.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Collapsible, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option
from textual.worker import Worker, WorkerState

from openai import APIError, AsyncOpenAI

from ayder_cli.core.config import Config
from ayder_cli.core.config_editor import (
    PRESETS,
    PROFILE_NAME,
    Preset,
    ProfileEditError,
    check_buildable,
    compose_base_url,
    default_profile,
    delete_profile,
    driver_fields,
    get_profile,
    install_hint,
    list_profiles,
    load_document,
    placeholder_profile,
    profile_driver,
    save_document,
    set_default,
    split_base_url,
    suggest_name,
    upsert_profile,
    validate,
)
from ayder_cli.core.reasoning import OLLAMA_EFFORTS, OPENAI_EFFORTS
from ayder_cli.providers import evren, provider_orchestrator
from ayder_cli.providers.evren import EvrenTerms
from ayder_cli.tui.screens import EvrenTermsScreen

_THINK_CHOICES = ("true", "false", "low", "medium", "high")
_ADVANCED_LABELS = {
    "num_ctx": "Context window (num_ctx)",
    "max_output_tokens": "Max output tokens",
    "reasoning_effort": "Reasoning effort",
    "think": "Thinking (think)",
    "stop_sequences": "Stop sequences (comma-separated)",
}


@dataclass(frozen=True)
class SaveResult:
    """What a profile form saved."""

    name: str
    make_default: bool  # the save made this profile the default
    warning: str | None = None


@dataclass(frozen=True)
class _TermsNeeded:
    """The evren gateway refused the listing until its terms are accepted."""

    terms: EvrenTerms
    client: AsyncOpenAI


async def _list_models(cfg: Config) -> list[str] | _TermsNeeded:
    """List the models of ``cfg``'s endpoint (runs in a form worker)."""
    provider = provider_orchestrator.create(cfg)
    try:
        return await provider.list_models()
    except APIError as e:
        if not evren.is_evren_terms_error(cfg.base_url, e):
            raise
        client = evren.make_client(cfg)
        return _TermsNeeded(await evren.fetch_terms(client), client)


def preset_values(preset: Preset) -> dict[str, Any]:
    """The starting values of a new profile made from ``preset``."""
    values: dict[str, Any] = {"driver": preset.driver, "model": preset.model}
    if preset.base_url is not None:
        values["base_url"] = preset.base_url
    if driver_fields(preset.driver).uses_api_key:
        values["api_key"] = ""
    values["num_ctx"] = preset.num_ctx
    return values


def _think_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value if isinstance(value, str) else None


class ProfileFormScreen(ModalScreen[SaveResult | None]):
    """Adds or edits one provider profile; dismisses with a ``SaveResult`` on save."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        *,
        name: str,
        values: Mapping[str, Any],
        title: str,
        editing: bool = False,
        is_default: bool = False,
        first_run: bool = False,
    ) -> None:
        super().__init__()
        self._profile_name = name
        self._values = dict(values)
        self._title = title
        self._editing = editing
        self._is_default = is_default
        self._first_run = first_run
        self._driver = profile_driver(name, self._values)
        # Raw widget values at mount; an edit writes only the keys whose widgets
        # changed, so untouched keys keep their bytes (and a missing key stays missing).
        self._initial: dict[str, Any] = {}
        self._fields = driver_fields(self._driver)
        self._install_hint = install_hint(self._driver)

    # --- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        fields = self._fields
        with Vertical(classes="config-modal"):
            yield Label(self._title, classes="prompt", markup=False)
            yield Label(f"Driver: {self._driver}", classes="description", markup=False)
            with VerticalScroll(id="form-scroll"):
                yield Label("Profile name", classes="field-label")
                yield Input(self._profile_name, id="name", disabled=self._editing)
                if fields.uses_base_url:
                    host, port, path = split_base_url(str(self._values.get("base_url") or ""))
                    yield Label("Host (with http:// or https://)", classes="field-label")
                    yield Input(host, id="host", placeholder="http://localhost")
                    yield Label("Port (optional)", classes="field-label")
                    yield Input(port, id="port", placeholder="e.g. 11434")
                    yield Label("Path (optional)", classes="field-label")
                    yield Input(path, id="path", placeholder="e.g. /v1")
                    yield Static("", id="url-preview", classes="note", markup=False)
                if fields.uses_api_key:
                    yield Label("API key", classes="field-label")
                    yield Input(str(self._values.get("api_key") or ""), id="api-key", password=True)
                if self._driver == "ollama":
                    yield Static(
                        "No API key here: ollama.com reads the OLLAMA_API_KEY environment variable.",
                        id="ollama-key-note",
                        classes="note",
                        markup=False,
                    )
                yield Label("Model", classes="field-label")
                with Horizontal(id="model-row"):
                    yield Input(str(self._values.get("model") or ""), id="model")
                    if fields.fetch_models:
                        yield Button("Fetch models", id="fetch")
                yield Static("", id="fetch-status", classes="note", markup=False)
                with Collapsible(title="Advanced", collapsed=True, id="advanced"):
                    for key in fields.advanced:
                        yield Label(_ADVANCED_LABELS.get(key, key), classes="field-label")
                        yield self._advanced_widget(key)
                yield Checkbox(
                    "Make default",
                    value=self._is_default or (self._first_run and not self._install_hint),
                    id="make-default",
                    disabled=self._is_default or bool(self._install_hint),
                )
                if self._install_hint:
                    yield Static(self._install_hint, id="install-hint", classes="warning", markup=False)
                yield Static("", id="error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def _advanced_widget(self, key: str) -> Input | Select[str]:
        value = self._values.get(key)
        widget_id = f"adv-{key}"
        if key in ("num_ctx", "max_output_tokens"):
            return Input(
                "" if value is None else str(value),
                id=widget_id,
                type="integer",
                placeholder="built-in default",
                classes="advanced-field",
            )
        if key == "stop_sequences":
            text = ", ".join(str(v) for v in value) if isinstance(value, list) else ""
            return Input(text, id=widget_id, placeholder="none", classes="advanced-field")
        if key == "reasoning_effort":
            efforts = OLLAMA_EFFORTS if self._driver == "ollama" else OPENAI_EFFORTS
            choices = ["default", *efforts]
        else:  # think
            choices = list(_THINK_CHOICES)
            value = _think_text(value)
        if isinstance(value, str) and value not in choices:
            choices.append(value)
        return Select(
            [(choice, choice) for choice in choices],
            prompt="(not set)",
            value=value if isinstance(value, str) else Select.NULL,
            id=widget_id,
            classes="advanced-field",
        )

    def on_mount(self) -> None:
        self._initial = {
            widget.id: widget.value
            for widget in self.query("Input, Select")
            if widget.id and widget.id != "name" and isinstance(widget, (Input, Select))
        }
        self._update_preview()

    # --- field handling -----------------------------------------------------

    def _input(self, widget_id: str) -> str:
        return self.query_one(f"#{widget_id}", Input).value

    def _base_url(self) -> str | None:
        host, port, path = self._input("host"), self._input("port"), self._input("path")
        if not (host.strip() or port.strip() or path.strip()):
            return None
        return compose_base_url(host, port, path)

    @on(Input.Changed, "#host, #port, #path")
    def _update_preview(self) -> None:
        if not self._fields.uses_base_url:
            return
        preview = self.query_one("#url-preview", Static)
        try:
            url = self._base_url()
        except ProfileEditError as e:
            preview.update(str(e))
            return
        preview.update(f"base_url = {url}" if url else "base_url not set (driver default)")

    def _changed(self, *widget_ids: str) -> bool:
        """A new profile writes every field; an edit only the fields the user changed."""
        if not self._editing:
            return True
        return any(
            self.query_one(f"#{widget_id}").value != self._initial.get(widget_id)  # type: ignore[attr-defined]
            for widget_id in widget_ids
        )

    def _collect(self, *, require_model: bool = True) -> tuple[str, dict[str, Any], list[str]]:
        """The form's profile name, values to write, and keys to remove.

        A blank field is not written: a new profile leaves the key out (so the
        driver default applies, e.g. a keyless local endpoint), and an edit that
        clears a field removes the key. A cleared API key is written as "".
        """
        name = self._input("name").strip()
        values: dict[str, Any] = {}
        remove: list[str] = []
        if not self._editing:
            values["driver"] = self._driver
        if self._fields.uses_base_url and self._changed("host", "port", "path"):
            url = self._base_url()
            if url is None:
                remove.append("base_url")
            else:
                values["base_url"] = url
        if self._fields.uses_api_key and self._changed("api-key"):
            api_key = self._input("api-key").strip()
            if api_key or self._editing:
                values["api_key"] = api_key
        model = self._input("model").strip()
        if require_model and not model:
            raise ProfileEditError("Model is required.")
        if self._changed("model"):
            values["model"] = model
        for key in self._fields.advanced:
            if not self._changed(f"adv-{key}"):
                continue
            parsed = self._advanced_value(key)
            if parsed is None:
                remove.append(key)
            else:
                values[key] = parsed
        return name, values, remove

    def _advanced_value(self, key: str) -> Any:
        widget = self.query_one(f"#adv-{key}")
        if isinstance(widget, Select):
            choice = widget.value
            if choice is Select.NULL:
                return None
            if key == "think" and choice in ("true", "false"):
                return choice == "true"
            return choice
        assert isinstance(widget, Input)
        raw = widget.value.strip()
        if not raw:
            return None
        if key == "stop_sequences":
            items = [item.strip() for item in raw.split(",") if item.strip()]
            return items or None
        try:
            return int(raw)
        except ValueError as e:
            raise ProfileEditError(f"{key} must be a whole number.") from e

    # --- actions ------------------------------------------------------------

    def _show_error(self, message: str) -> None:
        self.query_one("#error", Static).update(message)

    @on(Button.Pressed, "#save")
    def action_save(self) -> None:
        try:
            name, values, remove = self._collect()
            doc = load_document()
            if not self._editing and name in {p.name for p in list_profiles(doc)}:
                raise ProfileEditError(f"A profile named '{name}' already exists.")
            upsert_profile(doc, name, values, remove=remove)
            make_default = self.query_one("#make-default", Checkbox).value and not self._is_default
            if make_default:
                set_default(doc, name)
            validate(doc, active=name)
            becomes_default = name == default_profile(doc)
            warning = None
            build_error = check_buildable(doc, name)
            if build_error:
                if becomes_default:
                    raise ProfileEditError(build_error)
                warning = f"Saved '{name}', but it cannot be used yet: {build_error}"
            save_document(doc)
        except ProfileEditError as e:
            self._show_error(str(e))
            return
        self.dismiss(SaveResult(name, make_default, warning))

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)

    # --- Fetch models ---------------------------------------------------------
    # Workers run with exit_on_error=False: any failure (named or not) arrives
    # in on_worker_state_changed and is shown in the form, never exits the app.

    def _fetch_status(self, message: str) -> None:
        self.query_one("#fetch-status", Static).update(message)

    def _fetch_button(self, *, busy: bool) -> None:
        button = self.query_one("#fetch", Button)
        button.disabled = busy
        button.label = "Fetching…" if busy else "Fetch models"

    @on(Button.Pressed, "#fetch")
    def action_fetch(self) -> None:
        try:
            name, values, remove = self._collect(require_model=False)
            doc = load_document()
            probe = name if PROFILE_NAME.fullmatch(name) else "wizard-probe"
            upsert_profile(doc, probe, values, remove=remove)
            cfg = validate(doc, active=probe)
        except ProfileEditError as e:
            self._fetch_status(str(e))
            return
        self._fetch_button(busy=True)
        self._fetch_status("Fetching models…")
        self.run_worker(_list_models(cfg), group="fetch", exclusive=True, exit_on_error=False)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        worker = event.worker
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED):
            return
        if worker.group == "fetch":
            self._fetch_button(busy=False)
            if event.state == WorkerState.SUCCESS:
                self._fetched(worker.result)
            elif event.state == WorkerState.ERROR:
                self._fetch_status(f"Fetching models failed: {worker.error}")
        elif worker.group == "terms":
            if event.state == WorkerState.SUCCESS:
                self._fetch_status(f"Accepted evren terms v{worker.result}.")
                self.action_fetch()
            elif event.state == WorkerState.ERROR:
                self._fetch_status(f"Could not accept evren terms: {worker.error}")

    def _fetched(self, result: list[str] | _TermsNeeded | None) -> None:
        if isinstance(result, _TermsNeeded):
            self._ask_terms(result)
            return
        if not result:
            self._fetch_status("No models returned; type the model name.")
            return
        count = len(set(result))
        model = self.query_one("#model", Input)

        def picked(choice: str | None) -> None:
            if choice is None:
                self._fetch_status(f"{count} models fetched; the model is unchanged.")
                return
            model.value = choice
            model.focus()
            self._fetch_status(f"Picked {choice} from {count} models.")

        name = self._input("name").strip() or self._profile_name
        self.app.push_screen(
            ModelPickerScreen(result, current=model.value.strip(), title=f"Pick a model for '{name}'"),
            picked,
        )

    def _ask_terms(self, needed: _TermsNeeded) -> None:
        def decided(approved: bool | None) -> None:
            if approved:
                self.run_worker(
                    evren.accept_terms(needed.client, needed.terms.version),
                    group="terms",
                    exit_on_error=False,
                )
            else:
                self._fetch_status(
                    "evren terms not accepted; models cannot be listed until they are."
                )

        self.app.push_screen(EvrenTermsScreen(needed.terms), decided)



# Rows of the picker box besides the list: title, filter, count and hint lines,
# their margins, and the box's border and padding.
_PICKER_CHROME_ROWS = 11


class ModelPickerScreen(ModalScreen[str | None]):
    """Picks one of the fetched models; typing in the filter narrows the list.

    The arrow and page keys move the list while the filter keeps focus, Enter
    picks the highlighted model, Esc cancels.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "move('cursor_up')", show=False),
        Binding("down", "move('cursor_down')", show=False),
        Binding("pageup", "move('page_up')", show=False),
        Binding("pagedown", "move('page_down')", show=False),
    ]

    def __init__(self, models: list[str], *, current: str = "", title: str = "Pick a model") -> None:
        super().__init__()
        self._models = sorted(dict.fromkeys(models))
        self._current = current
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(classes="config-modal"):
            yield Label(self._title, classes="prompt", markup=False)
            with Horizontal(id="filter-row"):
                yield Label("Filter: ", id="filter-label")
                yield Input(placeholder="type part of a model name", id="model-filter", compact=True)
            yield OptionList(id="model-options")
            yield Static("", id="model-count", classes="note", markup=False)
            yield Label(
                "Type to filter · [b]↑↓[/] move · [b]Enter[/] pick · [b]Esc[/] cancel",
                classes="hint",
            )

    def on_mount(self) -> None:
        self._fit_list()
        self._show("")
        self.query_one("#model-filter", Input).focus()

    def on_resize(self) -> None:
        self._fit_list()

    def _fit_list(self) -> None:
        """Cap the list in cells so the box fits the terminal without empty rows.

        A ``vh`` max-height in CSS leaves the auto-height box sized for the
        uncapped list (empty rows under the hint); an absolute cap does not.
        """
        cap = int(self.app.size.height * 0.9) - _PICKER_CHROME_ROWS
        self.query_one("#model-options", OptionList).styles.max_height = max(3, min(20, cap))

    def _show(self, text: str) -> None:
        needle = text.strip().lower()
        matches = [m for m in self._models if needle in m.lower()]
        option_list = self.query_one("#model-options", OptionList)
        option_list.clear_options()
        for model in matches:
            prompt = Text(model)
            if model == self._current:
                prompt.append("  (current)", style="green")
            option_list.add_option(Option(prompt, id=model))
        if matches:
            option_list.highlighted = (
                matches.index(self._current) if self._current in matches else 0
            )
        if not needle:
            count = f"{len(self._models)} models"
        elif matches:
            count = f"{len(matches)} of {len(self._models)} models"
        else:
            count = f"No model matches {text.strip()!r}."
        self.query_one("#model-count", Static).update(count)

    @on(Input.Changed, "#model-filter")
    def _filter(self, event: Input.Changed) -> None:
        event.stop()
        self._show(event.value)

    def action_move(self, action: str) -> None:
        getattr(self.query_one("#model-options", OptionList), f"action_{action}")()

    @on(Input.Submitted, "#model-filter")
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        option = self.query_one("#model-options", OptionList).highlighted_option
        if option is not None:
            self.dismiss(option.id)

    @on(OptionList.OptionSelected, "#model-options")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ProviderTypeScreen(ModalScreen[str | None]):
    """Picks the preset for a new profile; a preset whose SDK is missing is disabled."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        options = []
        for key, preset in PRESETS.items():
            hint = install_hint(preset.driver)
            prompt = Text(preset.label, style="bold")
            prompt.append(f"  ({preset.driver})", style="dim")
            if hint:
                prompt.append(f"\n    {hint}", style="yellow")
            options.append(Option(prompt, id=key, disabled=bool(hint)))
        with Vertical(classes="config-modal"):
            yield Label("Add a provider", classes="prompt")
            yield OptionList(*options, id="presets")
            yield Label("↑↓ to navigate, Enter to select, Esc to cancel", classes="hint")

    def on_mount(self) -> None:
        option_list = self.query_one("#presets", OptionList)
        for index in range(option_list.option_count):
            if not option_list.get_option_at_index(index).disabled:
                option_list.highlighted = index
                break
        option_list.focus()

    @on(OptionList.OptionSelected, "#presets")
    def _picked(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Yes/No before a profile is deleted; No holds focus so a stray Enter keeps it."""

    BINDINGS = [
        Binding("y", "answer(True)", "Yes"),
        Binding("n", "answer(False)", "No"),
        Binding("escape", "answer(False)", "No"),
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical(classes="config-modal"):
            yield Label(self._question, classes="prompt", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Yes, delete", id="delete-yes", variant="error")
                yield Button("No", id="delete-no")

    def on_mount(self) -> None:
        self.query_one("#delete-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "delete-yes")

    def action_answer(self, answer: bool) -> None:
        self.dismiss(answer)


class ConfigWizardScreen(ModalScreen[None]):
    """The provider profiles in config.toml: add, edit, delete, set default.

    ``on_switch(name)`` moves the running session to profile ``name``; it is
    called when the session's profile is saved or a profile becomes the default.
    """

    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("s", "set_default", "Set default"),
        Binding("escape", "close", "Close"),
    ]

    def __init__(
        self,
        *,
        session_provider: Callable[[], str],
        on_switch: Callable[[str], None],
        first_run: bool = False,
    ) -> None:
        super().__init__()
        self._session_provider = session_provider
        self._on_switch = on_switch
        self._first_run = first_run

    def compose(self) -> ComposeResult:
        from ayder_cli.core import config as config_module

        if self._first_run:
            title = "Welcome to ayder: set up a provider"
            description = (
                "A default config was written. Add a provider or edit one, make it the "
                "default, then press Esc to start."
            )
        else:
            title = "Provider profiles"
            description = f"Config: {config_module.CONFIG_PATH}"
        with Vertical(classes="config-modal"):
            yield Label(title, id="wizard-title", classes="prompt", markup=False)
            # Static, not Label: a Label does not wrap and the first-run text is long.
            yield Static(description, classes="description", markup=False)
            yield OptionList(id="profiles")
            yield Static("", id="status", classes="note", markup=False)
            yield Label(
                "[b]a[/] add · [b]e[/]/[b]Enter[/] edit · [b]d[/] delete · "
                "[b]s[/] set default · [b]Esc[/] close",
                classes="hint",
            )

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#profiles", OptionList).focus()

    # --- list -----------------------------------------------------------------

    def _status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _refresh(self, select: str | None = None) -> None:
        option_list = self.query_one("#profiles", OptionList)
        keep = select or self._highlighted()
        try:
            profiles = list_profiles(load_document())
        except ProfileEditError as e:
            self._status(str(e))
            return
        session = self._session_provider()
        option_list.clear_options()
        # Columns: marker, name, driver, model (names and drivers are ASCII keys).
        name_width = max((len(p.name) for p in profiles), default=0)
        driver_width = max((len(p.driver) for p in profiles), default=0)
        for profile in profiles:
            prompt = Text("★ " if profile.is_default else "  ", style="bold yellow")
            prompt.append(profile.name.ljust(name_width), style="bold")
            prompt.append("  ")
            prompt.append(profile.driver.ljust(driver_width), style="dim")
            prompt.append("  ")
            prompt.append(profile.model or "(no model)", style="dim")
            if profile.name == session:
                prompt.append("  (in use)", style="green")
            hint = install_hint(profile.driver)
            if hint:
                prompt.append(f"\n  {hint}", style="yellow")
            option_list.add_option(Option(prompt, id=profile.name))
        names = [p.name for p in profiles]
        if names:
            option_list.highlighted = names.index(keep) if keep in names else 0

    def _highlighted(self) -> str | None:
        option = self.query_one("#profiles", OptionList).highlighted_option
        return option.id if option is not None else None

    # --- add / edit -----------------------------------------------------------

    def action_add(self) -> None:
        self.app.push_screen(ProviderTypeScreen(), self._preset_chosen)

    def _preset_chosen(self, key: str | None) -> None:
        if key is None:
            return
        preset = PRESETS[key]
        try:
            doc = load_document()
        except ProfileEditError as e:
            self._status(str(e))
            return
        placeholder = placeholder_profile(doc, preset)
        if placeholder is not None:
            self._open_edit(placeholder)
            return
        self.app.push_screen(
            ProfileFormScreen(
                name=suggest_name(doc, preset.key),
                values=preset_values(preset),
                title=f"Add profile: {preset.label}",
                first_run=self._first_run,
            ),
            self._saved,
        )

    def action_edit(self) -> None:
        name = self._highlighted()
        if name is not None:
            self._open_edit(name)

    @on(OptionList.OptionSelected, "#profiles")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.action_edit()

    def _open_edit(self, name: str) -> None:
        try:
            doc = load_document()
            values = get_profile(doc, name)
        except ProfileEditError as e:
            self._status(str(e))
            return
        self.app.push_screen(
            ProfileFormScreen(
                name=name,
                values=values,
                title=f"Edit profile '{name}'",
                editing=True,
                is_default=name == default_profile(doc),
                first_run=self._first_run,
            ),
            self._saved,
        )

    def _saved(self, result: SaveResult | None) -> None:
        if result is None:
            return
        self._refresh(select=result.name)
        if result.warning:
            # The profile does not build, so the session is not moved onto it.
            note = (
                " The session keeps its current settings."
                if result.name == self._session_provider()
                else ""
            )
            self._status(result.warning + note)
            return
        if result.make_default:
            self._status(f"Saved '{result.name}'; it is now the default.")
        else:
            self._status(f"Saved '{result.name}'.")
        if result.make_default or result.name == self._session_provider():
            self._on_switch(result.name)

    # --- set default / delete -------------------------------------------------

    def action_set_default(self) -> None:
        name = self._highlighted()
        if name is None:
            return
        try:
            doc = load_document()
            if name == default_profile(doc):
                self._status(f"'{name}' is already the default.")
                return
            hint = install_hint(str(get_profile(doc, name).get("driver", "openai")))
            if hint:
                self._status(f"'{name}' cannot be the default yet. {hint}")
                return
            build_error = check_buildable(doc, name)
            if build_error:
                self._status(build_error)
                return
            set_default(doc, name)
            save_document(doc)
        except ProfileEditError as e:
            self._status(str(e))
            return
        self._refresh(select=name)
        self._status(f"'{name}' is now the default.")
        self._on_switch(name)

    def action_delete(self) -> None:
        name = self._highlighted()
        if name is None:
            return
        try:
            doc = load_document()
            delete_profile(doc, name, session_provider=self._session_provider())
        except ProfileEditError as e:
            self._status(str(e))
            return

        def answered(confirmed: bool | None) -> None:
            if not confirmed:
                self._status(f"Kept '{name}'.")
                return
            try:
                save_document(doc)
            except ProfileEditError as e:
                self._status(str(e))
                return
            self._refresh()
            self._status(f"Deleted '{name}'.")

        self.app.push_screen(ConfirmDeleteScreen(f"Delete profile '{name}'?"), answered)

    def action_close(self) -> None:
        self.dismiss(None)
