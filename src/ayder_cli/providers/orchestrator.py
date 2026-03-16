"""
Provider Orchestrator/Registry pattern.
"""

from typing import Dict, Type
from ayder_cli.core.config import Config
from ayder_cli.providers.base import AIProvider

class ProviderOrchestrator:
    """Registry and factory for AI Providers."""
    
    def __init__(self):
        self._providers: Dict[str, str] = {
            "openai": "ayder_cli.providers.impl.openai.OpenAIProvider",
            "anthropic": "ayder_cli.providers.impl.claude.ClaudeProvider",
            "google": "ayder_cli.providers.impl.gemini.GeminiProvider",
            "ollama": "ayder_cli.providers.impl.ollama.OllamaProvider",
            "dashscope": "ayder_cli.providers.impl.qwen.QwenNativeProvider",
            "zhipu": "ayder_cli.providers.impl.glm.GLMNativeProvider",
            "deepseek": "ayder_cli.providers.impl.deepseek.DeepSeekProvider",
        }

    def register(self, driver_name: str, provider_path: str) -> None:
        """Register a new provider class path to a specific driver name."""
        self._providers[driver_name] = provider_path

    def _import_provider(self, path: str) -> Type[AIProvider]:
        import importlib
        module_name, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    def create(self, config: Config, interaction_sink=None) -> AIProvider:
        """Instantiate the appropriate provider for the given configuration."""
        driver = config.driver
        if driver not in self._providers:
            raise ValueError(
                f"Unsupported LLM driver '{driver}'. "
                f"Expected one of: {', '.join(self._providers.keys())}."
            )
        provider_cls = self._import_provider(self._providers[driver])
        return provider_cls(config, interaction_sink=interaction_sink)


# Module-level singleton for easy import and setup
provider_orchestrator = ProviderOrchestrator()
