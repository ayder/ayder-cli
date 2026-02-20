import tomllib
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Any, Callable, Dict

CONFIG_DIR = Path("~/.ayder").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.toml"

# Maintained for test compatibility and initial file generation
DEFAULTS: Dict[str, Any] = {
    "provider": "openai",
    "openai": {
        "driver": "openai",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "model": "qwen3-coder:latest",
        "num_ctx": 65536,
    },
    "anthropic": {
        "driver": "anthropic",
        "api_key": "",
        "model": "claude-sonnet-4-5-20250929",
        "num_ctx": 8192,
    },
    "gemini": {
        "driver": "google",
        "api_key": "",
        "model": "gemini-3-flash",
        "num_ctx": 65536,
    },
    "editor": "vim",
    "verbose": False,
    "logging": {
        "file_enabled": True,
        "file_path": ".ayder/log/ayder.log",
        "rotation": "10 MB",
        "retention": "7 days",
    },
    "max_background_processes": 5,
    "max_iterations": 50,
    "temporal": {
        "enabled": False,
        "host": "localhost:7233",
        "namespace": "default",
        "metadata_dir": ".ayder/temporal",
        "timeouts": {
            "workflow_schedule_to_close_seconds": 7200,
            "activity_start_to_close_seconds": 900,
            "activity_heartbeat_seconds": 30,
        },
        "retry": {
            "initial_interval_seconds": 5,
            "backoff_coefficient": 2.0,
            "maximum_interval_seconds": 60,
            "maximum_attempts": 3,
        },
    },
}

_PROVIDER_SECTIONS = ("openai", "anthropic", "gemini")
_DRIVER_BY_PROVIDER = {
    "openai": "openai",
    "ollama": "ollama",
    "anthropic": "anthropic",
    "gemini": "google",
}

_DEFAULT_TOML = """\
config_version = "2.0"

[app]
provider = "{provider}"
editor = "{editor}"
verbose = {verbose_str}
max_background_processes = {max_background_processes}
max_iterations = {max_iterations}

[logging]
file_enabled = {logging_file_enabled}
file_path = "{logging_file_path}"
rotation = "{logging_rotation}"
retention = "{logging_retention}"

[temporal]
enabled = {temporal_enabled}
host = "{temporal_host}"
namespace = "{temporal_namespace}"
metadata_dir = "{temporal_metadata_dir}"

[temporal.timeouts]
workflow_schedule_to_close_seconds = {temporal_workflow_schedule_to_close_seconds}
activity_start_to_close_seconds = {temporal_activity_start_to_close_seconds}
activity_heartbeat_seconds = {temporal_activity_heartbeat_seconds}

[temporal.retry]
initial_interval_seconds = {temporal_initial_interval_seconds}
backoff_coefficient = {temporal_backoff_coefficient}
maximum_interval_seconds = {temporal_maximum_interval_seconds}
maximum_attempts = {temporal_maximum_attempts}

[llm.openai]
driver = "openai"
base_url = "{openai_base_url}"
api_key = "{openai_api_key}"
model = "{openai_model}"
num_ctx = {openai_num_ctx}

[llm.anthropic]
driver = "anthropic"
api_key = "{anthropic_api_key}"
model = "{anthropic_model}"
num_ctx = {anthropic_num_ctx}

[llm.gemini]
driver = "google"
api_key = "{gemini_api_key}"
model = "{gemini_model}"
num_ctx = {gemini_num_ctx}
"""


class TemporalTimeoutsConfig(BaseModel):
    """Temporal timeout settings."""

    model_config = ConfigDict(frozen=True)

    workflow_schedule_to_close_seconds: int = Field(default=7200)
    activity_start_to_close_seconds: int = Field(default=900)
    activity_heartbeat_seconds: int = Field(default=30)

    @field_validator(
        "workflow_schedule_to_close_seconds",
        "activity_start_to_close_seconds",
        "activity_heartbeat_seconds",
    )
    @classmethod
    def validate_positive_seconds(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("temporal timeout values must be positive")
        return v


class TemporalRetryConfig(BaseModel):
    """Temporal retry policy settings."""

    model_config = ConfigDict(frozen=True)

    initial_interval_seconds: int = Field(default=5)
    backoff_coefficient: float = Field(default=2.0)
    maximum_interval_seconds: int = Field(default=60)
    maximum_attempts: int = Field(default=3)

    @field_validator("initial_interval_seconds", "maximum_interval_seconds", "maximum_attempts")
    @classmethod
    def validate_positive_retry_values(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("temporal retry values must be positive")
        return v

    @field_validator("backoff_coefficient")
    @classmethod
    def validate_backoff_coefficient(cls, v: float) -> float:
        if v < 1.0:
            raise ValueError("backoff_coefficient must be >= 1.0")
        return v


class TemporalConfig(BaseModel):
    """Optional Temporal runtime configuration."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(default=False)
    host: str = Field(default="localhost:7233")
    namespace: str = Field(default="default")
    metadata_dir: str = Field(default=".ayder/temporal")
    timeouts: TemporalTimeoutsConfig = Field(default_factory=TemporalTimeoutsConfig)
    retry: TemporalRetryConfig = Field(default_factory=TemporalRetryConfig)

    @field_validator("host", "namespace", "metadata_dir")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("temporal host/namespace/metadata_dir must be non-empty")
        return v


class Config(BaseModel):
    """Unified configuration model with validation."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    config_version: str = Field(default="2.0")
    provider: str = Field(default="openai")
    driver: str = Field(default="openai")
    base_url: str | None = Field(default="http://localhost:11434/v1")
    api_key: str = Field(default="ollama")
    model: str = Field(default="qwen3-coder:latest")
    num_ctx: int = Field(default=65536)
    editor: str = Field(default="vim")
    verbose: bool = Field(default=False)
    logging_level: str | None = Field(default=None)
    logging_file_enabled: bool = Field(default=True)
    logging_file_path: str = Field(default=".ayder/log/ayder.log")
    logging_rotation: str = Field(default="10 MB")
    logging_retention: str = Field(default="7 days")
    max_background_processes: int = Field(default=5)
    max_iterations: int = Field(default=50)
    max_output_tokens: int = Field(default=4096)
    max_history_messages: int = Field(default=0)
    stop_sequences: list[str] = Field(default_factory=list)
    tool_tags: list[str] = Field(default_factory=lambda: ["core", "metadata"])
    temporal: TemporalConfig = Field(default_factory=TemporalConfig)

    @model_validator(mode="before")
    @classmethod
    def flatten_nested_sections(cls, data: Any) -> Any:
        """Flatten v2 TOML sections into flat fields."""
        if not isinstance(data, dict):
            return data

        new_data = data.copy()

        app_section = data.get("app")
        if isinstance(app_section, dict):
            new_data.pop("app", None)
            new_data.update(app_section)

        provider = str(new_data.get("provider", DEFAULTS["provider"]))

        llm_section = data.get("llm")
        if isinstance(llm_section, dict):
            profile = llm_section.get(provider)
            if not isinstance(profile, dict):
                default_profile = llm_section.get(DEFAULTS["provider"])
                if isinstance(default_profile, dict):
                    profile = default_profile
            if isinstance(profile, dict):
                new_data.update(profile)
            new_data.pop("llm", None)

        if "driver" not in new_data:
            new_data["driver"] = _DRIVER_BY_PROVIDER.get(provider, "openai")

        if "logging" in data and isinstance(data["logging"], dict):
            section_data = new_data.pop("logging")
            for key, value in section_data.items():
                field_name = key if key.startswith("logging_") else f"logging_{key}"
                new_data[field_name] = value

        # Keep temporal section as nested config object
        if "temporal" in data and isinstance(data["temporal"], dict):
            new_data["temporal"] = data["temporal"]

        return new_data

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("provider must be a non-empty profile name")
        return v

    @field_validator("driver")
    @classmethod
    def validate_driver(cls, v: str) -> str:
        if v not in ("openai", "ollama", "anthropic", "google"):
            raise ValueError("driver must be one of 'openai', 'ollama', 'anthropic', or 'google'")
        return v

    @field_validator("num_ctx")
    @classmethod
    def validate_num_ctx(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("num_ctx must be positive")
        return v

    @field_validator("max_background_processes")
    @classmethod
    def validate_max_background_processes(cls, v: int) -> int:
        if v < 1 or v > 20:
            raise ValueError("max_background_processes must be between 1 and 20")
        return v

    @field_validator("max_iterations")
    @classmethod
    def validate_max_iterations(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError("max_iterations must be between 1 and 100")
        return v

    @field_validator("max_output_tokens")
    @classmethod
    def validate_max_output_tokens(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_output_tokens must be positive")
        return v

    @field_validator("max_history_messages")
    @classmethod
    def validate_max_history_messages(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_history_messages must be non-negative (0 = unlimited)")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @field_validator("logging_level")
    @classmethod
    def validate_logging_level(cls, v: str | None) -> str | None:
        if v is None:
            return None
        level = v.strip().upper()
        if not level:
            return None
        if level not in {"NONE", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError(
                "logging_level must be one of NONE, ERROR, WARNING, INFO, DEBUG"
            )
        return level


def load_config_for_provider(provider: str) -> Config:
    """Load config from ~/.ayder/config.toml with a specific provider active.

    Re-reads the TOML file and overrides the provider key before flattening,
    so the returned Config has the chosen provider's settings merged in.
    """
    from ayder_cli.core.config_migration import ensure_latest_config

    ensure_latest_config(CONFIG_PATH, defaults=DEFAULTS)

    if not CONFIG_PATH.exists():
        return Config(provider=provider)

    with open(CONFIG_PATH, "rb") as f:
        try:
            data = tomllib.load(f)
        except Exception:
            return Config(provider=provider)

    app = data.get("app")
    if isinstance(app, dict):
        app["provider"] = provider
    else:
        data["app"] = {"provider": provider}
    return Config(**data)


def list_provider_profiles() -> list[str]:
    """Return available provider profile names from [llm.<name>] config sections."""
    from ayder_cli.core.config_migration import ensure_latest_config

    ensure_latest_config(CONFIG_PATH, defaults=DEFAULTS)

    if not CONFIG_PATH.exists():
        return [DEFAULTS["provider"]]

    try:
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return [DEFAULTS["provider"]]

    llm = data.get("llm")
    if isinstance(llm, dict):
        profiles = [name for name, section in llm.items() if isinstance(section, dict)]
        if profiles:
            return sorted(dict.fromkeys(profiles))

    app = data.get("app")
    if isinstance(app, dict):
        provider = app.get("provider")
        if isinstance(provider, str) and provider.strip():
            return [provider.strip()]

    return [DEFAULTS["provider"]]


def load_config(
    *,
    notify_migration: bool = False,
    output: Callable[[str], None] | None = None,
) -> Config:
    """Load config from ~/.ayder/config.toml, creating it with defaults if missing."""
    from ayder_cli.core.config_migration import ensure_latest_config

    ensure_latest_config(
        CONFIG_PATH, defaults=DEFAULTS, notify=notify_migration, output=output
    )

    with open(CONFIG_PATH, "rb") as f:
        try:
            data = tomllib.load(f)
            return Config(**data)
        except Exception:
            return Config()
