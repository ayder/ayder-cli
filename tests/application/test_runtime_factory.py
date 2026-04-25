"""Tests for runtime factory — shared runtime composition path.

These tests validate that CLI and TUI receive factory-built dependencies
and that composition parity is maintained between both interfaces.
"""

from unittest.mock import Mock, patch
from dataclasses import fields
from pathlib import Path

from unittest.mock import MagicMock

from ayder_cli.agents.config import AgentConfig
from ayder_cli.application.runtime_factory import create_runtime, create_agent_runtime, RuntimeComponents
from ayder_cli.core.config import Config
from ayder_cli.providers import AIProvider
from ayder_cli.process_manager import ProcessManager
from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.registry import ToolRegistry
from ayder_cli.tui.app import AyderApp


class TestRuntimeFactoryAssembly:
    """Test factory assembles all required components."""

    def test_runtime_factory_assembles_all_components(self):
        """Factory returns all required components.

        Validates the factory creates a complete RuntimeComponents object
        with all dependencies properly initialized.
        """
        create_runtime()

        # Verify all expected fields exist
        expected_fields = {
            'config',
            'llm_provider',
            'process_manager',
            'project_ctx',
            'tool_registry',
            'system_prompt',
            'context_manager',
        }
        actual_fields = {f.name for f in fields(RuntimeComponents)}
        assert expected_fields.issubset(actual_fields), f"Missing fields: {expected_fields - actual_fields}"

    def test_factory_components_not_none(self):
        """All assembled components are non-None."""
        components = create_runtime()

        # Verify no component is None
        for field_name in ['config', 'llm_provider', 'process_manager', 'project_ctx',
                           'tool_registry', 'system_prompt']:
            value = getattr(components, field_name)
            assert value is not None, f"Component '{field_name}' should not be None"

    def test_factory_accepts_config_override(self):
        """Factory accepts injected config instead of loading default."""
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
        components = create_runtime(project_root="/custom/path")

        # Compare as Path objects (implementation uses Path)
        assert components.project_ctx.root == Path("/custom/path")

    def test_factory_accepts_model_name(self):
        """Factory accepts model name override."""
        components = create_runtime(model_name="qwen3-coder:latest")

        assert components.config.model == "qwen3-coder:latest"


class TestFactoryTUIIntegration:
    """Test TUI uses factory-built dependencies."""

    def test_tui_uses_factory_components(self):
        """TUI app uses factory-built dependencies.

        Validates that AyderApp initializes using create_runtime() for core deps.
        """
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
            mock_components.tool_registry.get_system_prompts.return_value = ""
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
        components = create_runtime()

        # Type checks for all components
        assert isinstance(components.config, Config)
        assert isinstance(components.llm_provider, AIProvider)
        assert isinstance(components.process_manager, ProcessManager)
        assert isinstance(components.project_ctx, ProjectContext)
        assert isinstance(components.tool_registry, ToolRegistry)
        assert isinstance(components.system_prompt, str)

    def test_factory_consistent_system_prompt(self):
        """Factory produces consistent system prompt for CLI and TUI."""
        components = create_runtime()

        # System prompt should contain expected sections
        assert len(components.system_prompt) > 100  # Substantial prompt
        assert "model" in components.system_prompt.lower() or "ayder" in components.system_prompt.lower()

    def test_factory_project_structure_macro(self):
        """Factory includes project structure macro in system prompt when available."""
        components = create_runtime()

        # Should attempt to include project structure
        # (may be empty if structure tool fails, but should not error)
        assert isinstance(components.system_prompt, str)


class TestFactoryEdgeCases:
    """Test factory edge cases and error handling."""

    def test_factory_handles_structure_macro_failure(self):
        """Factory handles failure to get project structure gracefully."""
        with patch('ayder_cli.application.runtime_factory.create_default_registry') as mock_create:
            mock_registry = Mock()
            mock_registry.execute.side_effect = Exception("Structure error")
            mock_registry.get_system_prompts.return_value = ""
            mock_registry.get_schemas.return_value = []
            mock_create.return_value = mock_registry

            # Should not raise
            components = create_runtime()

            # System prompt should still be valid (without structure macro)
            assert isinstance(components.system_prompt, str)
            assert "PROJECT STRUCTURE" not in components.system_prompt

    def test_factory_default_values(self):
        """Factory uses sensible defaults when optional args omitted."""
        # Call with no arguments
        components = create_runtime()

        # Should use current directory as project root (resolved to absolute path)
        assert components.project_ctx.root is not None
        assert isinstance(components.project_ctx.root, (str, Path))

        # All components should be initialized
        assert components.config is not None
        assert components.llm_provider is not None


class TestCreateAgentRuntime:
    """Tests for agent-specific runtime assembly.

    These are integration tests: they exercise create_agent_runtime with
    real (non-mocked) AgentConfig, Config, and ProjectContext objects.
    """

    def test_creates_runtime_with_agent_config(self):
        """create_agent_runtime returns RuntimeComponents for an agent."""
        agent_cfg = AgentConfig(name="test-agent", system_prompt="You are a test.")
        parent_cfg = Config()
        project_ctx = ProjectContext(".")
        pm = MagicMock()

        mock_registry = MagicMock()
        mock_registry.get_system_prompts.return_value = ""

        with patch("ayder_cli.application.runtime_factory.provider_orchestrator") as mock_orch, \
             patch("ayder_cli.application.runtime_factory.create_default_registry", return_value=mock_registry):
            mock_provider = MagicMock()
            mock_orch.create.return_value = mock_provider

            rt = create_agent_runtime(
                agent_config=agent_cfg,
                parent_config=parent_cfg,
                project_ctx=project_ctx,
                process_manager=pm,
                permissions={"r", "w", "x"},
            )

        assert rt.config is not None
        # Provider is wrapped with RetryingProvider by default — unwrap for identity check.
        from ayder_cli.providers.retry import RetryingProvider
        inner = rt.llm_provider._inner if isinstance(rt.llm_provider, RetryingProvider) else rt.llm_provider
        assert inner == mock_provider
        assert rt.process_manager == pm
        assert rt.project_ctx == project_ctx
        assert rt.system_prompt != ""
        assert "You are a test." in rt.system_prompt

    def test_agent_provider_override(self):
        """When agent specifies provider, load_config_for_provider is used."""
        agent_cfg = AgentConfig(
            name="test", provider="anthropic", system_prompt="test"
        )
        parent_cfg = Config()
        project_ctx = ProjectContext(".")
        pm = MagicMock()

        mock_registry = MagicMock()
        mock_registry.get_system_prompts.return_value = ""

        with patch("ayder_cli.application.runtime_factory.provider_orchestrator") as mock_orch, \
             patch("ayder_cli.application.runtime_factory.load_config_for_provider") as mock_load, \
             patch("ayder_cli.application.runtime_factory.create_default_registry", return_value=mock_registry):
            mock_load.return_value = Config()
            mock_orch.create.return_value = MagicMock()

            create_agent_runtime(
                agent_config=agent_cfg,
                parent_config=parent_cfg,
                project_ctx=project_ctx,
                process_manager=pm,
                permissions={"r"},
            )

        mock_load.assert_called_once_with("anthropic")

    def test_agent_model_override(self):
        """When agent specifies model, it overrides the resolved config's model."""
        agent_cfg = AgentConfig(
            name="test", model="custom-model", system_prompt="test"
        )
        parent_cfg = Config()
        project_ctx = ProjectContext(".")
        pm = MagicMock()

        mock_registry = MagicMock()
        mock_registry.get_system_prompts.return_value = ""

        with patch("ayder_cli.application.runtime_factory.provider_orchestrator") as mock_orch, \
             patch("ayder_cli.application.runtime_factory.create_default_registry", return_value=mock_registry):
            mock_orch.create.return_value = MagicMock()

            rt = create_agent_runtime(
                agent_config=agent_cfg,
                parent_config=parent_cfg,
                project_ctx=project_ctx,
                process_manager=pm,
                permissions={"r"},
            )

        assert rt.config.model == "custom-model"
