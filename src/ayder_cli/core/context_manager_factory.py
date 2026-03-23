"""Registry-based factory for ContextManager implementations.

Mirrors ProviderOrchestrator: maps driver names to lazy-imported classes.
Open for extension (register new drivers), closed for modification.
"""
from __future__ import annotations

import importlib


class ContextManagerFactory:
    """Registry and factory for ContextManager implementations."""

    def __init__(self):
        self._registry: dict[str, str] = {
            "ollama": "ayder_cli.core.ollama_context_manager.OllamaContextManager",
        }
        self._default = "ayder_cli.core.default_context_manager.DefaultContextManager"

    def register(self, driver: str, class_path: str) -> None:
        """Register a context manager for a driver."""
        self._registry[driver] = class_path

    def create(self, cfg):  # type: ignore[return]
        """Instantiate the appropriate ContextManager for the config's driver."""
        class_path = self._registry.get(cfg.driver, self._default)
        cls = self._import_class(class_path)
        return cls.from_config(cfg)  # type: ignore[attr-defined]

    def _import_class(self, path: str) -> type:
        module_name, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)


context_manager_factory = ContextManagerFactory()
