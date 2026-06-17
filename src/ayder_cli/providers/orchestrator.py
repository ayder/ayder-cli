"""
Provider Orchestrator / Registry.

Maps driver names to provider class paths plus optional-dependency metadata.
Availability is probed lazily via importlib.util.find_spec so heavy SDKs are
never imported just to check whether they are installed. config.driver is
never mutated; vendor aliases resolve to a canonical family name at lookup.
"""

import importlib
import importlib.util
from dataclasses import dataclass

from ayder_cli.core.config import Config
from ayder_cli.providers.base import AIProvider, ProviderUnavailableError


@dataclass(frozen=True)
class DriverCapability:
    provider_path: str
    sdk_module: str | None = None   # None => core driver (no optional dependency)
    extra_name: str | None = None   # pip extra that provides sdk_module

    def __post_init__(self) -> None:
        # A driver is either core (no SDK probe, no pip extra) or optional
        # (both set). Mixing them is meaningless: an SDK with no extra can't
        # tell users how to install it, and an extra with no SDK is never
        # probed. Enforcing this lets create() trust extra_name is a str
        # whenever an optional driver's SDK is missing.
        if (self.sdk_module is None) != (self.extra_name is None):
            raise ValueError(
                "DriverCapability requires sdk_module and extra_name to be set "
                f"together (got sdk_module={self.sdk_module!r}, "
                f"extra_name={self.extra_name!r})."
            )


def _installed(sdk_module: str | None) -> bool:
    """True if the SDK is importable. Core drivers (None) are always available."""
    if sdk_module is None:
        return True
    try:
        return importlib.util.find_spec(sdk_module) is not None
    except (ImportError, ValueError, AttributeError):
        return False


_IMPL = "ayder_cli.providers.impl"
# Insertion order controls how the availability list is displayed.
_CAPABILITIES: dict[str, DriverCapability] = {
    "openai":    DriverCapability(f"{_IMPL}.openai.OpenAIProvider"),
    "ollama":    DriverCapability(f"{_IMPL}.ollama.OllamaProvider"),
    "deepseek":  DriverCapability(f"{_IMPL}.deepseek.DeepSeekProvider"),
    "anthropic": DriverCapability(f"{_IMPL}.claude.ClaudeProvider",    "anthropic",    "anthropic"),
    "google":    DriverCapability(f"{_IMPL}.gemini.GeminiProvider",    "google.genai", "google"),
    "qwen":      DriverCapability(f"{_IMPL}.qwen.QwenNativeProvider",  "dashscope",    "qwen"),
    "glm":       DriverCapability(f"{_IMPL}.glm.GLMNativeProvider",    "zhipuai",      "glm"),
}
# Vendor-name aliases -> canonical family name.
_ALIASES: dict[str, str] = {"dashscope": "qwen", "zhipu": "glm"}


class ProviderOrchestrator:
    """Registry and factory for AI Providers."""

    def __init__(self) -> None:
        self._capabilities: dict[str, DriverCapability] = dict(_CAPABILITIES)
        self._aliases: dict[str, str] = dict(_ALIASES)

    def register(
        self,
        driver_name: str,
        provider_path: str,
        *,
        sdk_module: str | None = None,
        extra_name: str | None = None,
    ) -> None:
        """Register a provider. Backward compatible: 2-arg calls register a core driver."""
        self._capabilities[driver_name] = DriverCapability(provider_path, sdk_module, extra_name)

    def _canonical(self, driver: str) -> str:
        return self._aliases.get(driver, driver)

    def available_drivers(self) -> dict[str, bool]:
        """Map each canonical driver name -> whether its SDK is importable."""
        return {name: _installed(cap.sdk_module) for name, cap in self._capabilities.items()}

    def _import_provider(self, path: str) -> type[AIProvider]:
        module_name, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def create(self, config: Config, interaction_sink=None) -> AIProvider:
        """Instantiate the provider for config.driver, or raise if its SDK is missing."""
        driver = self._canonical(config.driver)
        cap = self._capabilities.get(driver)
        if cap is None:
            known = list(self._capabilities) + list(self._aliases)
            raise ValueError(
                f"Unsupported LLM driver '{config.driver}'. "
                f"Expected one of: {', '.join(known)}."
            )
        if not _installed(cap.sdk_module):
            # Reaching here means sdk_module is not None (core drivers are
            # always "installed"), so this optional driver always declares an
            # extra_name — guaranteed by DriverCapability's invariant.
            assert cap.extra_name is not None
            # Report the user's verbatim driver name; install command uses the
            # canonical extra (e.g. driver="dashscope" -> ayder-cli[qwen]).
            raise ProviderUnavailableError(config.driver, cap.extra_name, self.available_drivers())
        provider_cls = self._import_provider(cap.provider_path)
        return provider_cls(config, interaction_sink=interaction_sink)


# Module-level singleton for easy import and setup
provider_orchestrator = ProviderOrchestrator()
