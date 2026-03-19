"""Tests for application.runtime_factory."""

from unittest.mock import patch, MagicMock

from ayder_cli.agents.config import AgentConfig
from ayder_cli.application.runtime_factory import RuntimeComponents, create_runtime, create_agent_runtime
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext


def _patch_factory():
    """Helper to mock all external dependencies of the factory."""
    mock_registry = MagicMock()
    mock_registry.execute.return_value = "project tree"
    mock_registry.get_system_prompts.return_value = ""

    return (
        patch("ayder_cli.application.runtime_factory.load_config"),
        patch("ayder_cli.application.runtime_factory.provider_orchestrator.create"),
        patch("ayder_cli.application.runtime_factory.ProjectContext"),
        patch("ayder_cli.application.runtime_factory.ProcessManager"),
        patch(
            "ayder_cli.application.runtime_factory.create_default_registry",
            return_value=mock_registry,
        ),
        mock_registry,
    )

def _make_cfg(model="test-model", max_background_processes=5):
    cfg = MagicMock()
    cfg.model = model
    cfg.max_background_processes = max_background_processes
    return cfg


def test_create_runtime_returns_all_components():
    (p_load, p_llm, p_ctx, p_pm, p_reg, mock_registry) = (
        _patch_factory()
    )
    with p_load as mock_load, p_llm, p_ctx, p_pm, p_reg:
        cfg = _make_cfg()
        mock_load.return_value = cfg

        rt = create_runtime()

    assert isinstance(rt, RuntimeComponents)
    assert rt.config is cfg
    assert isinstance(rt.system_prompt, str)
    assert len(rt.system_prompt) > 0


def test_create_runtime_accepts_injected_config():
    (p_load, p_llm, p_ctx, p_pm, p_reg, mock_registry) = (
        _patch_factory()
    )
    with p_load as mock_load, p_llm, p_ctx, p_pm, p_reg:
        cfg = _make_cfg()

        rt = create_runtime(config=cfg)

    mock_load.assert_not_called()
    assert rt.config is cfg


def test_create_runtime_handles_project_structure_error():
    mock_registry = MagicMock()
    mock_registry.execute.side_effect = Exception("unavailable")
    mock_registry.get_system_prompts.return_value = ""

    with (
        patch("ayder_cli.application.runtime_factory.load_config") as mock_load,
        patch("ayder_cli.application.runtime_factory.provider_orchestrator.create"),
        patch("ayder_cli.application.runtime_factory.ProjectContext"),
        patch("ayder_cli.application.runtime_factory.ProcessManager"),
        patch(
            "ayder_cli.application.runtime_factory.create_default_registry",
            return_value=mock_registry,
        ),
    ):
        cfg = _make_cfg()
        mock_load.return_value = cfg

        rt = create_runtime()

    assert isinstance(rt.system_prompt, str)
    assert len(rt.system_prompt) > 0


class TestCreateAgentRuntime:
    """Tests for agent-specific runtime assembly."""

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
        assert rt.llm_provider == mock_provider
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

            rt = create_agent_runtime(
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
