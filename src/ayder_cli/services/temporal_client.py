"""Lazy Temporal SDK client adapter."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable, cast

from ayder_cli.core.config import Config, load_config


class TemporalClientUnavailableError(RuntimeError):
    """Raised when Temporal client cannot be initialized."""


def _import_temporal_client_class() -> type:
    """Import temporalio Client lazily."""
    from temporalio.client import Client  # type: ignore

    return Client


def _default_connector(client_cls: type, host: str, namespace: str) -> Any:
    """Create Temporal client using SDK connect entrypoint."""
    connect_fn = getattr(client_cls, "connect", None)
    if connect_fn is None:
        raise TemporalClientUnavailableError("Temporal Client.connect is unavailable")

    result = connect_fn(host, namespace=namespace)
    if inspect.isawaitable(result):
        async_result = cast(Awaitable[Any], result)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            async def _resolve() -> Any:
                return await async_result

            return asyncio.run(_resolve())
        raise TemporalClientUnavailableError(
            "Cannot run synchronous temporal connect while event loop is active"
        )
    return result


class TemporalClientAdapter:
    """Lazily initialized Temporal client adapter with caching."""

    def __init__(
        self,
        config: Config | None = None,
        connector: Callable[[type, str, str], Any] | None = None,
    ) -> None:
        self._config = config or load_config()
        self._connector = connector or _default_connector
        self._client: Any | None = None

    @property
    def enabled(self) -> bool:
        """Whether Temporal runtime is enabled in config."""
        return self._config.temporal.enabled

    def get_client(self) -> Any:
        """Get cached Temporal client, initializing lazily when needed."""
        if not self.enabled:
            raise TemporalClientUnavailableError(
                "Temporal runtime is disabled in config"
            )

        if self._client is not None:
            return self._client

        try:
            client_cls = _import_temporal_client_class()
        except ImportError as e:
            raise TemporalClientUnavailableError(
                "temporalio package is not installed. "
                "Install optional dependency: uv pip install -e '.[temporal]'"
            ) from e

        self._client = self._connector(
            client_cls,
            self._config.temporal.host,
            self._config.temporal.namespace,
        )
        return self._client

    def clear_cache(self) -> None:
        """Clear cached Temporal client (mainly for tests)."""
        self._client = None
