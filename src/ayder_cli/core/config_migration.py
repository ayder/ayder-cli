"""Config migration helpers for schema v2.0."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Callable

LATEST_CONFIG_VERSION = "2.0"
LEGACY_PROVIDER_TABLES: tuple[str, ...] = ("openai", "anthropic", "gemini")
_DRIVER_BY_PROVIDER: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "google",
}

_MIGRATION_NOTICE = (
    "Notice: Your configuration has been updated to Version 2.0. "
    "A backup of your old config was saved to `config.toml.bak`. "
    "Please check your `provider` settings in the new `config.toml`."
)


def _toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def render_v2_config(
    defaults: dict[str, Any],
    *,
    app_overrides: dict[str, Any] | None = None,
    logging_overrides: dict[str, Any] | None = None,
    temporal_overrides: dict[str, Any] | None = None,
    llm_overrides: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Render a v2.0 config TOML using defaults + overrides."""
    app: dict[str, Any] = {
        "provider": str(defaults.get("provider", "openai")),
        "editor": str(defaults.get("editor", "vim")),
        "verbose": bool(defaults.get("verbose", False)),
        "max_background_processes": int(defaults.get("max_background_processes", 5)),
        "max_iterations": int(defaults.get("max_iterations", 50)),
    }
    if app_overrides:
        app.update(app_overrides)

    logging_cfg = dict(defaults.get("logging", {}))
    if logging_overrides:
        logging_cfg.update(logging_overrides)

    temporal_cfg = _deep_merge_dict(dict(defaults.get("temporal", {})), temporal_overrides or {})

    llm_profiles: dict[str, dict[str, Any]] = {}
    for provider in LEGACY_PROVIDER_TABLES:
        section = dict(defaults.get(provider, {}))
        section.setdefault("driver", _DRIVER_BY_PROVIDER[provider])
        llm_profiles[provider] = section
    if llm_overrides:
        for name, section in llm_overrides.items():
            merged = dict(llm_profiles.get(name, {}))
            merged.update(section)
            if "driver" not in merged:
                merged["driver"] = _DRIVER_BY_PROVIDER.get(name, "openai")
            llm_profiles[name] = merged

    if app["provider"] not in llm_profiles:
        llm_profiles[app["provider"]] = {
            "driver": "openai",
            "base_url": str(defaults["openai"]["base_url"]),
            "api_key": str(defaults["openai"]["api_key"]),
            "model": str(defaults["openai"]["model"]),
            "num_ctx": int(defaults["openai"]["num_ctx"]),
        }

    lines: list[str] = [
        f'config_version = "{LATEST_CONFIG_VERSION}"',
        "",
        "[app]",
        f'provider = {_toml_str(str(app["provider"]))}',
        f'editor = {_toml_str(str(app["editor"]))}',
        f'verbose = {_toml_bool(bool(app["verbose"]))}',
        f"max_background_processes = {int(app['max_background_processes'])}",
        f"max_iterations = {int(app['max_iterations'])}",
        "",
        "[logging]",
        f"file_enabled = {_toml_bool(bool(logging_cfg.get('file_enabled', True)))}",
        f'file_path = {_toml_str(str(logging_cfg.get("file_path", ".ayder/log/ayder.log")))}',
        f'rotation = {_toml_str(str(logging_cfg.get("rotation", "10 MB")))}',
        f'retention = {_toml_str(str(logging_cfg.get("retention", "7 days")))}',
    ]

    level = logging_cfg.get("level")
    if isinstance(level, str) and level.strip():
        lines.append(f'level = {_toml_str(level)}')

    lines.extend(
        [
            "",
            "[temporal]",
            f"enabled = {_toml_bool(bool(temporal_cfg.get('enabled', False)))}",
            f'host = {_toml_str(str(temporal_cfg.get("host", "localhost:7233")))}',
            f'namespace = {_toml_str(str(temporal_cfg.get("namespace", "default")))}',
            f'metadata_dir = {_toml_str(str(temporal_cfg.get("metadata_dir", ".ayder/temporal")))}',
            "",
            "[temporal.timeouts]",
        ]
    )
    timeouts = temporal_cfg.get("timeouts", {})
    lines.extend(
        [
            f"workflow_schedule_to_close_seconds = {int(timeouts.get('workflow_schedule_to_close_seconds', 7200))}",
            f"activity_start_to_close_seconds = {int(timeouts.get('activity_start_to_close_seconds', 900))}",
            f"activity_heartbeat_seconds = {int(timeouts.get('activity_heartbeat_seconds', 30))}",
            "",
            "[temporal.retry]",
        ]
    )
    retry = temporal_cfg.get("retry", {})
    lines.extend(
        [
            f"initial_interval_seconds = {int(retry.get('initial_interval_seconds', 5))}",
            f"backoff_coefficient = {float(retry.get('backoff_coefficient', 2.0))}",
            f"maximum_interval_seconds = {int(retry.get('maximum_interval_seconds', 60))}",
            f"maximum_attempts = {int(retry.get('maximum_attempts', 3))}",
        ]
    )

    for name in sorted(llm_profiles):
        profile = llm_profiles[name]
        driver = str(profile.get("driver", _DRIVER_BY_PROVIDER.get(name, "openai")))
        lines.extend(
            [
                "",
                f"[llm.{name}]",
                f'driver = {_toml_str(driver)}',
            ]
        )
        if profile.get("base_url") is not None:
            lines.append(f'base_url = {_toml_str(str(profile.get("base_url", "")))}')
        lines.extend(
            [
                f'api_key = {_toml_str(str(profile.get("api_key", "")))}',
                f'model = {_toml_str(str(profile.get("model", "")))}',
                f"num_ctx = {int(profile.get('num_ctx', defaults['openai']['num_ctx']))}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def _extract_legacy_overrides(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    app_overrides: dict[str, Any] = {}
    logging_overrides: dict[str, Any] = {}
    temporal_overrides: dict[str, Any] = {}
    llm_overrides: dict[str, dict[str, Any]] = {}

    provider = data.get("provider")
    if isinstance(provider, str) and provider.strip():
        app_overrides["provider"] = provider.strip()

    editor = data.get("editor")
    if isinstance(editor, dict):
        editor_name = editor.get("editor")
        if isinstance(editor_name, str) and editor_name.strip():
            app_overrides["editor"] = editor_name

    ui = data.get("ui")
    if isinstance(ui, dict) and isinstance(ui.get("verbose"), bool):
        app_overrides["verbose"] = ui["verbose"]

    agent = data.get("agent")
    if isinstance(agent, dict) and isinstance(agent.get("max_iterations"), int):
        app_overrides["max_iterations"] = agent["max_iterations"]

    if isinstance(data.get("max_background_processes"), int):
        app_overrides["max_background_processes"] = data["max_background_processes"]

    logging_section = data.get("logging")
    if isinstance(logging_section, dict):
        logging_overrides = dict(logging_section)

    temporal_section = data.get("temporal")
    if isinstance(temporal_section, dict):
        temporal_overrides = dict(temporal_section)

    for provider_name in LEGACY_PROVIDER_TABLES:
        section = data.get(provider_name)
        if isinstance(section, dict):
            merged = dict(section)
            merged["driver"] = _DRIVER_BY_PROVIDER[provider_name]
            llm_overrides[provider_name] = merged

    llm_legacy = data.get("llm")
    if isinstance(llm_legacy, dict):
        # Legacy flat [llm] schema (pre-[llm.<name>]) support.
        if all(not isinstance(v, dict) for v in llm_legacy.values()):
            legacy_provider = llm_legacy.get("provider")
            if (
                isinstance(legacy_provider, str)
                and legacy_provider.strip()
                and "provider" not in app_overrides
            ):
                app_overrides["provider"] = legacy_provider.strip()

            target_provider = llm_legacy.get("provider") or app_overrides.get(
                "provider", "openai"
            )
            target_provider = (
                target_provider if target_provider in LEGACY_PROVIDER_TABLES else "openai"
            )
            section = {
                k: v
                for k, v in llm_legacy.items()
                if k in {"base_url", "api_key", "model", "num_ctx", "driver"}
            }
            if section:
                section.setdefault(
                    "driver", _DRIVER_BY_PROVIDER.get(target_provider, "openai")
                )
                llm_overrides[target_provider] = _deep_merge_dict(
                    llm_overrides.get(target_provider, {}), section
                )

    return app_overrides, logging_overrides, temporal_overrides, llm_overrides


def _backup_config(config_path: Path) -> Path:
    backup_path = config_path.with_name(f"{config_path.name}.bak")
    if backup_path.exists():
        backup_path.unlink()
    config_path.rename(backup_path)
    return backup_path


def ensure_latest_config(
    config_path: Path,
    *,
    defaults: dict[str, Any],
    notify: bool = False,
    output: Callable[[str], None] | None = None,
) -> str | None:
    """Ensure config.toml is in v2.0 schema, migrating legacy schema when needed."""
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(render_v2_config(defaults), encoding="utf-8")
        return None

    parsed: dict[str, Any] | None = None
    parse_error = False
    try:
        with open(config_path, "rb") as f:
            loaded = tomllib.load(f)
            if isinstance(loaded, dict):
                parsed = loaded
            else:
                parse_error = True
    except Exception:
        parse_error = True

    if (
        not parse_error
        and isinstance(parsed, dict)
        and str(parsed.get("config_version", "")).strip() == LATEST_CONFIG_VERSION
    ):
        return None

    _backup_config(config_path)

    if parse_error or not isinstance(parsed, dict):
        new_content = render_v2_config(defaults)
    else:
        try:
            (
                app_overrides,
                logging_overrides,
                temporal_overrides,
                llm_overrides,
            ) = _extract_legacy_overrides(parsed)
            new_content = render_v2_config(
                defaults,
                app_overrides=app_overrides,
                logging_overrides=logging_overrides,
                temporal_overrides=temporal_overrides,
                llm_overrides=llm_overrides,
            )
        except Exception:
            new_content = render_v2_config(defaults)

    config_path.write_text(new_content, encoding="utf-8")

    if notify and output is not None:
        output(_MIGRATION_NOTICE)
    return _MIGRATION_NOTICE
