"""Convergence smoke tests for temporal runtime wiring.

Phase 14 scope:
- CLI temporal queue path wires worker config correctly.
- temporal_workflow tool routes through service action path.
- Runtime factory composes non-UI interaction defaults.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ayder_cli.cli_runner import _run_temporal_queue_cli
from ayder_cli.core.config import Config, TemporalConfig
from ayder_cli.tools.temporal import temporal_workflow


class TestTemporalRuntimeWiringConvergence:
    def test_cli_temporal_queue_runner_wiring(self):
        with patch("ayder_cli.services.temporal_worker.TemporalWorker") as mock_worker_cls:
            worker_instance = MagicMock()
            worker_instance.run.return_value = 0
            mock_worker_cls.return_value = worker_instance

            result = _run_temporal_queue_cli(
                queue_name="dev-team",
                prompt_path="prompts/dev.md",
                permissions={"r", "w"},
                iterations=33,
            )

            assert result == 0
            mock_worker_cls.assert_called_once()
            config_obj = mock_worker_cls.call_args.args[0]
            assert config_obj.queue_name == "dev-team"
            assert config_obj.prompt_path == "prompts/dev.md"
            assert config_obj.permissions == {"r", "w"}
            assert config_obj.iterations == 33
            worker_instance.run.assert_called_once()

    def test_temporal_tool_routes_to_service_action_path(self, monkeypatch):
        cfg = Config(temporal=TemporalConfig(enabled=True))
        monkeypatch.setattr(
            "ayder_cli.services.temporal_workflow_service.load_config", lambda: cfg
        )
        monkeypatch.setattr(
            "ayder_cli.services.temporal_workflow_service.TemporalClientAdapter.get_client",
            lambda self: object(),
        )

        result = temporal_workflow(
            action="start_workflow",
            workflow_id="wf-101",
            queue_name="qa-team",
        )

        body = json.loads(result)
        assert body["ok"] is True
        assert body["action"] == "start_workflow"
        assert body["workflow_id"] == "wf-101"
        assert body["queue_name"] == "qa-team"

    def test_runtime_factory_uses_non_ui_interaction_defaults(self):
        from ayder_cli.application.runtime_factory import create_runtime
        from ayder_cli.services.interactions import (
            AutoApproveConfirmationPolicy,
            NullInteractionSink,
        )

        mock_registry = MagicMock()
        mock_registry.execute.return_value = "src/"

        with patch("ayder_cli.application.runtime_factory.create_llm_provider") as mock_llm, patch(
            "ayder_cli.application.runtime_factory.create_default_registry",
            return_value=mock_registry,
        ):
            mock_llm.return_value = MagicMock()
            components = create_runtime(config=Config(temporal=TemporalConfig(enabled=False)))

        assert isinstance(components.tool_executor.interaction_sink, NullInteractionSink)
        assert isinstance(
            components.tool_executor.confirmation_policy,
            AutoApproveConfirmationPolicy,
        )
