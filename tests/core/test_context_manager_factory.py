"""Tests for ContextManagerFactory — registry-based OCP factory."""
import pytest
from unittest.mock import MagicMock

from ayder_cli.core.context_manager_factory import ContextManagerFactory


def test_create_returns_default_for_unknown_driver():
    factory = ContextManagerFactory()
    cfg = MagicMock()
    cfg.driver = "anthropic"
    cfg.context_manager.max_context_tokens = 8192
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    cfg.context_manager.tool_result_compress_age = 5
    cfg.context_manager.max_tool_result_length = 2048
    cfg.context_manager.compress_tool_results = True
    cfg.context_manager.enabled = True
    cfg.provider = "anthropic"
    cfg.model = "claude-sonnet"
    mgr = factory.create(cfg)
    from ayder_cli.core.default_context_manager import DefaultContextManager
    assert isinstance(mgr, DefaultContextManager)


def test_create_returns_ollama_for_ollama_driver():
    factory = ContextManagerFactory()
    cfg = MagicMock()
    cfg.driver = "ollama"
    cfg.base_url = "http://localhost:11434"
    cfg.num_ctx = 65536
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    mgr = factory.create(cfg)
    from ayder_cli.core.ollama_context_manager import OllamaContextManager
    assert isinstance(mgr, OllamaContextManager)


def test_register_adds_new_driver():
    factory = ContextManagerFactory()
    factory.register("custom", "ayder_cli.core.default_context_manager.DefaultContextManager")
    cfg = MagicMock()
    cfg.driver = "custom"
    cfg.context_manager.max_context_tokens = 4096
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    cfg.context_manager.tool_result_compress_age = 5
    cfg.context_manager.max_tool_result_length = 2048
    cfg.context_manager.compress_tool_results = True
    cfg.context_manager.enabled = True
    cfg.provider = "custom"
    cfg.model = "custom-model"
    mgr = factory.create(cfg)
    assert mgr is not None
