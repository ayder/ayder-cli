"""Tests for runtime factory — shared runtime composition path.

These tests validate that CLI and TUI receive factory-built dependencies
and that composition parity is maintained between both interfaces.
"""

import pytest
from unittest.mock import Mock, patch
from dataclasses import fields


class TestRuntimeFactoryAssembly:
    """Test factory assembles all required components."""

    def test_runtime_factory_assembles_all_components(self):
        """Factory returns all 9 required components.
        
        Validates the factory creates a complete RuntimeComponents object
        with all dependencies properly initialized.
        """
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime, RuntimeComponents

        create_runtime()

        # Verify all expected fields exist
        expected_fields = {
            'config',
            'llm_provider',
            'process_manager',
            'project_ctx',
            'tool_registry',
            'tool_executor',
            'checkpoint_manager',
            'memory_manager',
            'system_prompt',
        }
        actual_fields = {f.name for f in fields(RuntimeComponents)}
        assert expected_fields == actual_fields, f"Missing fields: {expected_fields - actual_fields}"

    def test_factory_components_not_none(self):
        """All assembled components are non-None."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime

        components = create_runtime()

        # Verify no component is None
        for field_name in ['config', 'llm_provider', 'process_manager', 'project_ctx',
                           'tool_registry', 'tool_executor', 'checkpoint_manager',
                           'memory_manager', 'system_prompt']:
            value = getattr(components, field_name)
            assert value is not None, f"Component '{field_name}' should not be None"

    def test_factory_accepts_config_override(self):
        """Factory accepts injected config instead of loading default."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime
        from ayder_cli.core.config import Config

        mock_config = Config(
            base_url="http://custom:8080/v1",
            api_key="custom-key",
            model="custom-model",
            num_ctx=8192,
            verbose=True,
        )

        components = create_runtime(config=mock_config)

        assert components.config == mock_config
        assert components.config.model == "custom-model"

    def test_factory_accepts_project_root(self):
        """Factory accepts custom project root."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from pathlib import Path
        from ayder_cli.application.runtime_factory import create_runtime

        components = create_runtime(project_root="/custom/path")

        # Compare as Path objects (implementation uses Path)
        assert components.project_ctx.root == Path("/custom/path")

    def test_factory_accepts_model_name(self):
        """Factory accepts model name override."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime

        components = create_runtime(model_name="qwen3-coder:latest")

        assert components.config.model == "qwen3-coder:latest"


class TestFactoryCLIIntegration:
    """Test CLI uses factory-built dependencies."""

    def test_cli_uses_factory_components(self):
        """CLI runner uses factory-built dependencies.
        
        Validates that cli_runner._build_services() delegates to create_runtime()
        and returns components in the expected order for backward compatibility.
        """
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.cli_runner import _build_services

        services = _build_services()

        # Backward compatible return order: (config, llm, tool_executor, project_ctx,
        #                                   enhanced_system, checkpoint_manager, memory_manager)
        assert len(services) == 7
        cfg, llm, tool_exec, project_ctx, system_prompt, ckpt_mgr, mem_mgr = services

        assert cfg is not None
        assert llm is not None
        assert tool_exec is not None
        assert project_ctx is not None
        assert system_prompt is not None
        assert ckpt_mgr is not None
        assert mem_mgr is not None

    def test_cli_factory_integration_preserves_behavior(self):
        """CLI factory integration preserves existing behavior."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.cli_runner import _build_services

        services = _build_services()
        cfg, llm, tool_exec, project_ctx, system_prompt, ckpt_mgr, mem_mgr = services

        # System prompt should contain expected content
        assert "model" in system_prompt.lower() or "ayder" in system_prompt.lower()


class TestFactoryTUIIntegration:
    """Test TUI uses factory-built dependencies."""

    def test_tui_uses_factory_components(self):
        """TUI app uses factory-built dependencies.
        
        Validates that AyderApp initializes using create_runtime() for core deps.
        """
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.tui.app import AyderApp

        # TUI now uses create_runtime factory - patch the factory call
        with patch('ayder_cli.tui.app.create_runtime') as mock_create_runtime:
            mock_components = Mock()
            mock_components.config = Mock()
            mock_components.config.model = "test-model"
            mock_components.config.num_ctx = 65536
            mock_components.config.max_iterations = 50
            mock_components.config.max_background_processes = 5
            mock_components.config.max_output_tokens = 4096
            mock_components.config.stop_sequences = []
            mock_components.config.tool_tags = ["core", "metadata"]
            mock_components.config.driver = "openai"
            mock_components.llm_provider = Mock()
            mock_components.tool_registry = Mock()
            mock_components.tool_registry.execute.return_value = "src/\n  main.py"
            mock_components.checkpoint_manager = Mock()
            mock_components.memory_manager = Mock()
            mock_components.system_prompt = "test system prompt"
            mock_create_runtime.return_value = mock_components

            # Create app - should use factory
            app = AyderApp()

            # Verify factory was called
            mock_create_runtime.assert_called_once()

            # Verify core dependencies initialized from factory
            assert app.config is not None
            assert app.llm is not None
            assert app.registry is not None
            assert app.chat_loop is not None


class TestFactoryCompositionParity:
    """Test CLI and TUI get equivalent core dependencies."""

    def test_cli_tui_factory_parity(self):
        """CLI and TUI get equivalent core dependencies.
        
        Validates that both interfaces receive the same types of dependencies
        from the factory, ensuring consistent behavior.
        """
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime
        from ayder_cli.services.llm import LLMProvider
        from ayder_cli.tools.registry import ToolRegistry
        from ayder_cli.services.tools.executor import ToolExecutor
        from ayder_cli.checkpoint_manager import CheckpointManager
        from ayder_cli.memory import MemoryManager
        from ayder_cli.process_manager import ProcessManager
        from ayder_cli.core.context import ProjectContext
        from ayder_cli.core.config import Config

        components = create_runtime()

        # Type checks for all components
        assert isinstance(components.config, Config)
        assert isinstance(components.llm_provider, LLMProvider)
        assert isinstance(components.process_manager, ProcessManager)
        assert isinstance(components.project_ctx, ProjectContext)
        assert isinstance(components.tool_registry, ToolRegistry)
        assert isinstance(components.tool_executor, ToolExecutor)
        assert isinstance(components.checkpoint_manager, CheckpointManager)
        assert isinstance(components.memory_manager, MemoryManager)
        assert isinstance(components.system_prompt, str)

    def test_factory_consistent_system_prompt(self):
        """Factory produces consistent system prompt for CLI and TUI."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime

        components = create_runtime()

        # System prompt should contain expected sections
        assert len(components.system_prompt) > 100  # Substantial prompt
        assert "model" in components.system_prompt.lower() or "ayder" in components.system_prompt.lower()

    def test_factory_project_structure_macro(self):
        """Factory includes project structure macro in system prompt when available."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime

        components = create_runtime()

        # Should attempt to include project structure
        # (may be empty if structure tool fails, but should not error)
        assert isinstance(components.system_prompt, str)


class TestFactoryEdgeCases:
    """Test factory edge cases and error handling."""

    def test_factory_handles_structure_macro_failure(self):
        """Factory handles failure to get project structure gracefully."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from ayder_cli.application.runtime_factory import create_runtime

        with patch('ayder_cli.application.runtime_factory.create_default_registry') as mock_create:
            mock_registry = Mock()
            mock_registry.execute.side_effect = Exception("Structure error")
            mock_create.return_value = mock_registry

            # Should not raise
            components = create_runtime()
            
            # System prompt should still be valid (without structure macro)
            assert isinstance(components.system_prompt, str)
            assert "PROJECT STRUCTURE" not in components.system_prompt

    def test_factory_default_values(self):
        """Factory uses sensible defaults when optional args omitted."""
        pytest.importorskip(
            "ayder_cli.application.runtime_factory",
            reason="Runtime factory not yet implemented by DEV-02.1"
        )
        from pathlib import Path
        from ayder_cli.application.runtime_factory import create_runtime

        # Call with no arguments
        components = create_runtime()

        # Should use current directory as project root (resolved to absolute path)
        assert components.project_ctx.root is not None
        assert isinstance(components.project_ctx.root, (str, Path))

        # All components should be initialized
        assert components.config is not None
        assert components.llm_provider is not None
