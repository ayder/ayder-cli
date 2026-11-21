"""Comment-preserving edits of provider profiles in config.toml.

Backs the config wizard (first run and ``/config``). Every edit goes through a
tomlkit document, so comments, ordering and every table the wizard does not
touch keep their exact bytes. The path is read from ``config.CONFIG_PATH`` at
call time, so the ``-c/--config`` override is honoured.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from urllib.parse import urlsplit

import httpx
import openai
import tomlkit
from pydantic import ValidationError
from tomlkit.exceptions import TOMLKitError
from tomlkit.toml_document import TOMLDocument

from ayder_cli.core import config as config_module
from ayder_cli.core.config import DEFAULTS, Config

# Profile names are written as bare TOML keys: [llm.<name>].
PROFILE_NAME = re.compile(r"[A-Za-z0-9_-]+")


class ProfileEditError(ValueError):
    """A profile edit that cannot be made; the message is shown to the user."""


@dataclass(frozen=True)
class ProfileSummary:
    """One ``[llm.<name>]`` profile as the wizard lists it."""

    name: str
    driver: str
    model: str
    is_default: bool


def _path(path: Path | None) -> Path:
    return Path(path) if path is not None else config_module.CONFIG_PATH


def _plain(value: Any) -> Any:
    """A tomlkit item as a plain Python value."""
    unwrap = getattr(value, "unwrap", None)
    return unwrap() if callable(unwrap) else value


def load_document(path: Path | None = None) -> TOMLDocument:
    """Parse config.toml, seeding the default template when it is missing."""
    target = _path(path)
    if not target.exists():
        from ayder_cli.core.config_migration import ensure_latest_config

        ensure_latest_config(target, defaults=config_module.DEFAULTS)
    try:
        return tomlkit.parse(target.read_text(encoding="utf-8"))
    except OSError as e:
        raise ProfileEditError(f"Could not read {target}: {e.strerror or e}") from e
    except TOMLKitError as e:
        raise ProfileEditError(f"{target} is not valid TOML: {e}") from e


def save_document(doc: TOMLDocument, path: Path | None = None) -> None:
    """Write ``doc`` atomically (temporary file + ``os.replace``), keeping the file mode."""
    target = _path(path)
    try:
        mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
        fd, tmp_name = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
        )
        replaced = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(doc.as_string())
            if mode is not None:
                os.chmod(tmp_name, mode)
            os.replace(tmp_name, target)
            replaced = True
        finally:
            if not replaced:
                Path(tmp_name).unlink(missing_ok=True)
    except OSError as e:
        raise ProfileEditError(f"Could not write {target}: {e.strerror or e}") from e


def _profiles(doc: TOMLDocument) -> dict[str, Mapping[str, Any]]:
    llm = doc.get("llm")
    if not isinstance(llm, Mapping):
        return {}
    return {name: section for name, section in llm.items() if isinstance(section, Mapping)}


def default_profile(doc: TOMLDocument) -> str:
    """The ``[app].provider`` value (the profile a new session starts with)."""
    app = doc.get("app")
    provider = app.get("provider") if isinstance(app, Mapping) else None
    if isinstance(provider, str) and provider.strip():
        return provider.strip()
    return str(config_module.DEFAULTS["provider"])


def profile_driver(name: str, section: Mapping[str, Any]) -> str:
    """The driver ``Config`` uses for profile ``name``.

    Its ``driver`` key, else the one ``Config`` infers from the profile name
    (``[llm.ollama]`` → ollama), else openai.
    """
    driver = _plain(section.get("driver"))
    if isinstance(driver, str) and driver.strip():
        return driver.strip()
    return config_module._DRIVER_BY_PROVIDER.get(name, "openai")


def list_profiles(doc: TOMLDocument) -> list[ProfileSummary]:
    """Every ``[llm.<name>]`` profile, in file order."""
    default = default_profile(doc)
    return [
        ProfileSummary(
            name=name,
            driver=profile_driver(name, section),
            model=str(_plain(section.get("model", ""))),
            is_default=name == default,
        )
        for name, section in _profiles(doc).items()
    ]


def get_profile(doc: TOMLDocument, name: str) -> dict[str, Any]:
    """The profile's keys as plain Python values."""
    section = _profiles(doc).get(name)
    if section is None:
        raise ProfileEditError(f"No profile named '{name}'.")
    return {key: _plain(value) for key, value in section.items()}


def set_default(doc: TOMLDocument, name: str) -> None:
    """Make ``name`` the ``[app].provider``; creates ``[app]`` when missing."""
    if name not in _profiles(doc):
        raise ProfileEditError(f"No profile named '{name}'.")
    app = doc.get("app")
    if not isinstance(app, Mapping):
        doc["app"] = tomlkit.table()
        app = doc["app"]
    app["provider"] = name  # type: ignore[index]


def upsert_profile(
    doc: TOMLDocument,
    name: str,
    values: Mapping[str, Any],
    *,
    remove: Iterable[str] = (),
) -> None:
    """Add ``[llm.<name>]`` or merge ``values`` into it, deleting the keys in ``remove``.

    Keys not named in ``values`` or ``remove`` are kept as they are, and a value
    equal to the one already in the file is not rewritten (its formatting and
    trailing comment stay).
    """
    if not PROFILE_NAME.fullmatch(name):
        raise ProfileEditError(
            f"Profile name {name!r} may use only letters, digits, '-' and '_'."
        )
    llm = doc.get("llm")
    if not isinstance(llm, Mapping):
        doc["llm"] = tomlkit.table(is_super_table=True)
        llm = doc["llm"]
    section = llm.get(name)
    if section is None:
        table = tomlkit.table()
        for key, value in values.items():
            table[key] = value
        llm[name] = table  # type: ignore[index]
        # A table added before other tables needs its own blank line; one added
        # at the end of the file gets the separator from tomlkit already.
        if not doc.as_string().endswith(table.as_string()):
            table.add(tomlkit.nl())
        return
    if not isinstance(section, Mapping):
        raise ProfileEditError(f"[llm] key '{name}' is not a table.")
    for key, value in values.items():
        if key not in section or _plain(section[key]) != value:
            section[key] = value  # type: ignore[index]
    for key in remove:
        if key in section:
            del section[key]  # type: ignore[attr-defined]


def _error_text(error: Mapping[str, Any]) -> str:
    loc = ".".join(str(part) for part in error.get("loc", ())) or "config"
    msg = str(error.get("msg", "invalid value")).removeprefix("Value error, ")
    return f"{loc}: {msg}"


def validate(doc: TOMLDocument, *, active: str) -> Config:
    """Build the ``Config`` the file yields with ``active`` as the provider.

    Errors are reported as ``loc: msg`` without input values, so an API key never
    reaches the message.
    """
    if active not in _profiles(doc):
        raise ProfileEditError(f"No profile named '{active}'.")
    data = doc.unwrap()
    app = data.get("app")
    data["app"] = {**(app if isinstance(app, dict) else {}), "provider": active}
    try:
        return Config(**data)
    except ValidationError as e:
        raise ProfileEditError(
            "; ".join(_error_text(err) for err in e.errors(include_input=False))
        ) from e


def _agents_using(doc: TOMLDocument, name: str) -> list[str]:
    agents = doc.get("agents")
    if not isinstance(agents, Mapping):
        return []
    return [
        agent
        for agent, section in agents.items()
        if isinstance(section, Mapping) and _plain(section.get("provider")) == name
    ]


def delete_profile(doc: TOMLDocument, name: str, *, session_provider: str | None) -> None:
    """Remove ``[llm.<name>]`` unless a delete rule forbids it."""
    profiles = _profiles(doc)
    if name not in profiles:
        raise ProfileEditError(f"No profile named '{name}'.")
    if len(profiles) == 1:
        raise ProfileEditError(f"'{name}' is the last profile; add another one first.")
    if name == default_profile(doc):
        raise ProfileEditError(f"'{name}' is the default profile; set another default first.")
    if name == session_provider:
        raise ProfileEditError(
            f"'{name}' is the profile this session is using; switch with /provider first."
        )
    agents = _agents_using(doc, name)
    if agents:
        raise ProfileEditError(f"'{name}' is used by agents: {', '.join(agents)}.")
    del doc["llm"][name]  # type: ignore[union-attr]


# --- Presets and per-driver fields -----------------------------------------


@dataclass(frozen=True)
class Preset:
    """A provider the wizard can add with ready-made settings."""

    key: str  # suggested profile name
    label: str
    driver: str
    model: str
    num_ctx: int
    base_url: str | None = None


_EVREN = DEFAULTS["extra_llm_profiles"]["evren"]
PRESETS: dict[str, Preset] = {
    "anthropic": Preset(
        "anthropic", "Claude", "anthropic",
        DEFAULTS["anthropic"]["model"], DEFAULTS["anthropic"]["num_ctx"],
    ),
    "gemini": Preset(
        "gemini", "Gemini", "google",
        DEFAULTS["gemini"]["model"], DEFAULTS["gemini"]["num_ctx"],
    ),
    "evren": Preset(
        "evren", "Evren", "openai", _EVREN["model"], _EVREN["num_ctx"], _EVREN["base_url"],
    ),
    # Native Ollama API: no /v1 suffix. The model comes from "Fetch models".
    "ollama": Preset(
        "ollama", "Ollama", "ollama", "", DEFAULTS["openai"]["num_ctx"], "http://localhost:11434",
    ),
    "openai": Preset(
        "openai", "OpenAI-compatible", "openai", "", DEFAULTS["openai"]["num_ctx"],
        "http://localhost/v1",
    ),
}


@dataclass(frozen=True)
class DriverFields:
    """Which profile keys a driver reads (the wizard shows only these)."""

    uses_base_url: bool
    uses_api_key: bool
    advanced: tuple[str, ...]
    fetch_models: bool = False


DRIVER_FIELDS: dict[str, DriverFields] = {
    "openai": DriverFields(
        True, True, ("num_ctx", "max_output_tokens", "reasoning_effort", "stop_sequences"), True
    ),
    # The native Ollama path ignores api_key (ollama.com reads OLLAMA_API_KEY).
    "ollama": DriverFields(True, False, ("num_ctx", "think", "reasoning_effort"), True),
    "anthropic": DriverFields(False, True, ("num_ctx", "max_output_tokens", "stop_sequences")),
    "google": DriverFields(False, True, ("num_ctx", "max_output_tokens")),
}
GENERIC_FIELDS = DriverFields(True, True, ("num_ctx",))


def driver_fields(driver: str) -> DriverFields:
    """The fields for ``driver``; other drivers (deepseek, qwen, glm) get the generic set."""
    return DRIVER_FIELDS.get(driver, GENERIC_FIELDS)


def compose_base_url(host: str, port: str, path: str) -> str:
    """Join the wizard's Host, Port and Path fields into a base URL."""
    host = host.strip().rstrip("/")
    port = port.strip()
    path = path.strip()
    if not host:
        raise ProfileEditError("Host is required.")
    if port:
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ProfileEditError(f"port must be a number from 1 to 65535 (got {port!r}).")
        host = f"{host}:{int(port)}"
    if path and not path.startswith("/"):
        path = f"/{path}"
    url = host + ("" if path == "/" else path)
    try:
        urlsplit(url).port
    except ValueError as e:
        raise ProfileEditError(f"Invalid host or port in {url!r}: {e}.") from e
    return url


def split_base_url(url: str) -> tuple[str, str, str]:
    """Split a base URL into the wizard's (host, port, path) fields."""
    parts = urlsplit(url.strip())
    netloc = parts.netloc
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is not None:
        netloc = netloc[: netloc.rfind(":")]
    host = f"{parts.scheme}://{netloc}" if parts.scheme else netloc
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    return host, "" if port is None else str(port), path


def suggest_name(doc: TOMLDocument, base: str) -> str:
    """``base``, or ``base2``, ``base3``, … when the name is taken."""
    taken = set(_profiles(doc))
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def placeholder_profile(doc: TOMLDocument, preset: Preset) -> str | None:
    """The preset's profile when it exists as an empty-key placeholder, else None.

    The seeded template ships ``anthropic``, ``gemini`` and ``evren`` with an empty
    ``api_key``; adding that preset edits the placeholder instead of adding a copy.
    """
    if not driver_fields(preset.driver).uses_api_key:
        return None
    section = _profiles(doc).get(preset.key)
    if section is None:
        return None
    if profile_driver(preset.key, section) != preset.driver or _plain(section.get("api_key", "")):
        return None
    return preset.key


def install_hint(driver: str) -> str | None:
    """How to install ``driver``'s missing SDK, or None when it is installed."""
    from ayder_cli.providers import provider_orchestrator

    extra = provider_orchestrator.missing_extra(driver)
    return f"Install it with: pip install ayder-cli[{extra}]" if extra else None


def check_buildable(doc: TOMLDocument, name: str) -> str | None:
    """None when profile ``name`` builds a provider, else the error to show.

    Building makes no network call; it catches what would stop the TUI from
    starting with this profile as the default.
    """
    from ayder_cli.providers import ProviderUnavailableError, provider_orchestrator

    try:
        provider_orchestrator.create(validate(doc, active=name))
    except ProfileEditError as e:
        return str(e)
    except ProviderUnavailableError as e:
        return str(e)
    except (ValueError, ImportError, httpx.InvalidURL, openai.OpenAIError) as e:
        return f"{name}: {e}"
    return None
