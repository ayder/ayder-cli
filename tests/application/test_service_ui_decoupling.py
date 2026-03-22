"""Architecture boundary tests for service/UI decoupling.

Verifies:
- Service modules do not import ayder_cli.ui
- InteractionSink protocol is correctly defined and exported
- LLM providers use injected InteractionSink for debug output
- TUI adapter satisfies the protocol
"""

import ast
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest


class TestArchitectureBoundary:
    """Service modules must not depend on the presentation layer."""

    def test_services_directory_has_no_ui_imports(self):
        project_root = Path(__file__).parent.parent.parent
        services_dir = project_root / "src" / "ayder_cli" / "services"
        violations = []

        for py_file in services_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "ayder_cli.ui" or alias.name.startswith("ayder_cli.ui."):
                                violations.append(f"{py_file.relative_to(project_root)}: import {alias.name}")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith("ayder_cli.ui"):
                            names = ", ".join(a.name for a in node.names)
                            violations.append(f"{py_file.relative_to(project_root)}: from {node.module} import {names}")
            except SyntaxError:
                continue

        assert not violations, (
            "Service modules must not import ayder_cli.ui.\n"
            "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
        )

    def test_tui_adapter_not_imported_by_services(self):
        """services/ must not import adapter modules (no circular deps)."""
        project_root = Path(__file__).parent.parent.parent
        services_dir = project_root / "src" / "ayder_cli" / "services"
        for py_file in services_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            tree = ast.parse(py_file.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "adapter" not in alias.name, f"{py_file} imports adapter"
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "adapter" not in node.module, f"{py_file} imports from adapter"


class TestInteractionSinkProtocol:
    def test_services_exports_interaction_sink(self):
        from ayder_cli import services
        assert hasattr(services, "InteractionSink")

    def test_interaction_sink_is_runtime_checkable(self):
        from ayder_cli.services import InteractionSink
        assert hasattr(InteractionSink, "_is_runtime_protocol")

    def test_interaction_sink_has_on_llm_request_debug(self):
        from ayder_cli.services import InteractionSink
        assert "on_llm_request_debug" in dir(InteractionSink)


class TestTUIAdapterLayer:
    def test_tui_adapter_exists_in_tui_layer(self):
        project_root = Path(__file__).parent.parent.parent
        assert (project_root / "src" / "ayder_cli" / "tui" / "adapter.py").exists()

    def test_tui_adapter_satisfies_interaction_sink(self):
        from ayder_cli.services import InteractionSink
        from ayder_cli.tui.adapter import TUIInteractionSink
        assert isinstance(TUIInteractionSink(), InteractionSink)

    def test_cli_adapter_removed_from_ui_layer(self):
        """cli_adapter.py was deleted — the TUI path is the only live adapter."""
        project_root = Path(__file__).parent.parent.parent
        assert not (project_root / "src" / "ayder_cli" / "ui" / "cli_adapter.py").exists()


class TestLLMProviderIntegration:
    def test_openai_provider_works_without_sink(self):
        from ayder_cli.providers.impl.openai import OpenAIProvider
        config = Mock()
        config.base_url = "http://mock"
        config.api_key = "mock"
        provider = OpenAIProvider(config=config)
        assert provider.interaction_sink is None

    def test_openai_provider_calls_sink_on_verbose(self):
        import asyncio
        from unittest.mock import AsyncMock
        from ayder_cli.providers.impl.openai import OpenAIProvider
        from ayder_cli.services import InteractionSink

        sink = Mock(spec=InteractionSink)
        mock_client = Mock()
        choice = Mock()
        choice.message.content = "response"
        choice.message.reasoning_content = ""
        choice.message.tool_calls = []
        mock_response = Mock()
        mock_response.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        config = Mock()
        config.base_url = "http://mock"
        config.api_key = "mock"

        provider = OpenAIProvider(config=config, interaction_sink=sink)
        provider.client = mock_client

        asyncio.run(provider.chat([{"role": "user", "content": "hi"}], "gpt-4", verbose=True))
        sink.on_llm_request_debug.assert_called_once()
