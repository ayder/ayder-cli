import importlib

import pytest
from loguru import logger

MODULES = [
    ("ayder_cli.providers.impl.openai", "llm"),
    ("ayder_cli.providers.impl.ollama", "llm"),
    ("ayder_cli.providers.impl.claude", "llm"),
    ("ayder_cli.providers.impl.gemini", "llm"),
    ("ayder_cli.providers.impl.ollama_drivers.registry", "llm"),
    ("ayder_cli.providers.impl.qwen", "llm"),
    ("ayder_cli.providers.impl.ollama_drivers.generic_xml", "llm"),
    ("ayder_cli.core.cache_monitor", "context"),
]


@pytest.mark.parametrize("module_name,channel", MODULES)
def test_module_logger_binds_expected_channel(module_name, channel):
    mod = importlib.import_module(module_name)
    seen = []
    sid = logger.add(lambda m: seen.append(m.record["extra"]), level=0)
    try:
        mod.logger.warning("probe")
    finally:
        logger.remove(sid)
    assert seen, f"{module_name} produced no record"
    assert seen[0].get("channel") == channel


def test_no_record_is_left_unbound():
    """A channel-aware filter must never meet an empty extra from these modules."""
    for module_name, _ in MODULES:
        mod = importlib.import_module(module_name)
        seen = []
        sid = logger.add(lambda m: seen.append(m.record["extra"]), level=0)
        try:
            mod.logger.info("probe")
        finally:
            logger.remove(sid)
        assert "channel" in seen[0], f"{module_name} emits unbound records"
