"""Driver registry with auto-discovery and matrix-first resolution."""

from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules
from typing import Any

from loguru import logger

from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver
from ayder_cli.providers.impl.ollama_drivers.matrix import RESOLUTION_MATRIX

_SKIP_MODULES: frozenset[str] = frozenset({"base", "registry", "matrix", "_errors"})


class DriverRegistry:
    """Resolve Ollama model names to per-family chat drivers."""

    def __init__(self, inspector: Any):
        self._inspector = inspector
        self._drivers: list[ChatDriver] = self._auto_discover()
        self._drivers.sort(key=lambda d: d.priority)
        self._by_name: dict[str, ChatDriver] = {d.name: d for d in self._drivers}
        self._cache: dict[str, ChatDriver] = {}

    def _auto_discover(self) -> list[ChatDriver]:
        drivers: list[ChatDriver] = []
        package = import_module("ayder_cli.providers.impl.ollama_drivers")
        for _, modname, _ in iter_modules(package.__path__):
            if modname in _SKIP_MODULES:
                continue
            try:
                module = import_module(f"{package.__name__}.{modname}")
            except Exception as exc:
                logger.warning(f"Skipping Ollama driver module {modname!r}: {exc}")
                continue
            for attr in vars(module).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, ChatDriver)
                    and attr is not ChatDriver
                    and not getattr(attr, "abstract", False)
                ):
                    drivers.append(attr())
        return drivers

    async def resolve(self, model: str, override: str | None = None) -> ChatDriver:
        """Resolve the best driver for a model."""
        if override and override in self._by_name:
            return self._by_name[override]

        if model in self._cache:
            return self._cache[model]

        try:
            info = await self._inspector.get_model_info(model)
        except Exception as exc:
            logger.warning(f"/api/show failed for {model!r}: {exc}; using default")
            return self._default_driver()

        for rule in RESOLUTION_MATRIX:
            if rule.matches(info) and rule.driver in self._by_name:
                driver = self._by_name[rule.driver]
                logger.debug(
                    f"Matrix matched {model!r} to {driver.name} "
                    f"({rule.note or 'no note'})"
                )
                self._cache[model] = driver
                return driver

        for driver in self._drivers:
            if driver.supports(info):
                logger.debug(f"Driver {driver.name} self-claimed {model!r}")
                self._cache[model] = driver
                return driver

        driver = self._default_driver()
        self._cache[model] = driver
        return driver

    def get(self, name: str) -> ChatDriver:
        """Return a registered driver by name."""
        return self._by_name[name]

    def _default_driver(self) -> ChatDriver:
        if "generic_native" in self._by_name:
            return self._by_name["generic_native"]
        if self._drivers:
            return self._drivers[0]
        raise RuntimeError("No Ollama chat drivers are registered")
