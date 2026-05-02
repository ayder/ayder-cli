"""GenericNativeDriver: trusts Ollama's server-side tool extraction."""

from __future__ import annotations

from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode


class GenericNativeDriver(ChatDriver):
    name = "generic_native"
    mode = DriverMode.NATIVE
    priority = 900
    fallback_driver = "generic_xml"
    supports_families = ()
