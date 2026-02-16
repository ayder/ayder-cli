"""Tests for application.runtime_factory."""

from unittest.mock import patch, MagicMock

from ayder_cli.application.runtime_factory import RuntimeComponents, create_runtime


def _patch_factory(registry_execute_return="tree"):
    """Return a context manager that patches all factory dependencies."""
    mock_registry = MagicMock()
    mock_registry.execute.return_value = registry_execute_return

    return (
        patch("ayder_cli.application.runtime_factory.load_config"),
        patch("ayder_cli.application.runtime_factory.create_llm_provider"),
        patch("ayder_cli.application.runtime_factory.ProjectContext"),
        patch("ayder_cli.application.runtime_factory.ProcessManager"),
        patch(
            "ayder_cli.application.runtime_factory.create_default_registry",
            return_value=mock_registry,
        ),
        patch("ayder_cli.application.runtime_factory.ToolExecutor"),
        patch("ayder_cli.application.runtime_factory.CheckpointManager"),
        patch("ayder_cli.application.runtime_factory.MemoryManager"),
        mock_registry,
    )


def _make_cfg(model="test-model", max_background_processes=5):
    cfg = MagicMock()
    cfg.model = model
    cfg.max_background_processes = max_background_processes
    return cfg


def test_create_runtime_returns_all_components():
    (p_load, p_llm, p_ctx, p_pm, p_reg, p_exec, p_cm, p_mm, mock_registry) = (
        _patch_factory()
    )
    with p_load as mock_load, p_llm, p_ctx, p_pm, p_reg, p_exec, p_cm, p_mm:
        cfg = _make_cfg()
        mock_load.return_value = cfg

        rt = create_runtime()

    assert isinstance(rt, RuntimeComponents)
    assert rt.config is cfg
    assert isinstance(rt.system_prompt, str)
    assert len(rt.system_prompt) > 0


def test_create_runtime_accepts_injected_config():
    (p_load, p_llm, p_ctx, p_pm, p_reg, p_exec, p_cm, p_mm, mock_registry) = (
        _patch_factory()
    )
    with p_load as mock_load, p_llm, p_ctx, p_pm, p_reg, p_exec, p_cm, p_mm:
        cfg = _make_cfg()

        rt = create_runtime(config=cfg)

    mock_load.assert_not_called()
    assert rt.config is cfg


def test_create_runtime_handles_project_structure_error():
    mock_registry = MagicMock()
    mock_registry.execute.side_effect = Exception("unavailable")

    with (
        patch("ayder_cli.application.runtime_factory.load_config") as mock_load,
        patch("ayder_cli.application.runtime_factory.create_llm_provider"),
        patch("ayder_cli.application.runtime_factory.ProjectContext"),
        patch("ayder_cli.application.runtime_factory.ProcessManager"),
        patch(
            "ayder_cli.application.runtime_factory.create_default_registry",
            return_value=mock_registry,
        ),
        patch("ayder_cli.application.runtime_factory.ToolExecutor"),
        patch("ayder_cli.application.runtime_factory.CheckpointManager"),
        patch("ayder_cli.application.runtime_factory.MemoryManager"),
    ):
        cfg = _make_cfg()
        mock_load.return_value = cfg

        rt = create_runtime()

    assert isinstance(rt.system_prompt, str)
    assert len(rt.system_prompt) > 0
