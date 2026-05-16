"""Tests for AgentRunner — wraps one ChatLoop execution per agent dispatch."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.agents.summary import AgentSummary


class TestAgentRunner:
    def _make_runner(self, **overrides):
        agent_cfg = AgentConfig(name="test-agent", system_prompt="You are a test.")
        parent_cfg = MagicMock()
        parent_cfg.model_copy.return_value = parent_cfg
        parent_cfg.model = "test-model"
        parent_cfg.num_ctx = 4096
        parent_cfg.max_output_tokens = 2048
        parent_cfg.stop_sequences = []
        parent_cfg.tool_tags = ["core"]
        parent_cfg.provider = "openai"
        parent_cfg.max_history_messages = 30

        defaults = dict(
            agent_config=agent_cfg,
            parent_config=parent_cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r", "w"},
            timeout=10,
        )
        defaults.update(overrides)
        return AgentRunner(**defaults)

    def test_init(self):
        runner = self._make_runner()
        assert runner.agent_name == "test-agent"
        assert runner.status == "idle"

    def test_parse_summary_block(self):
        """Extracts <agent-summary> from content."""
        content = (
            "I reviewed the code.\n"
            "<agent-summary>\n"
            "FINDINGS: Found 2 bugs\n"
            "FILES_CHANGED: none\n"
            "RECOMMENDATIONS: Fix bug in auth.py\n"
            "</agent-summary>"
        )
        runner = self._make_runner()
        summary = runner._parse_summary(content)
        assert "Found 2 bugs" in summary

    def test_parse_summary_fallback(self):
        """Falls back to full content when no <agent-summary> block."""
        content = "I finished reviewing the code. All looks good."
        runner = self._make_runner()
        summary = runner._parse_summary(content)
        assert summary == content

    def test_cancel(self):
        runner = self._make_runner()
        assert runner.cancel() is True
        assert runner.status == "cancelled"

    @pytest.mark.anyio
    async def test_run_returns_summary(self):
        """AgentRunner.run() returns an AgentSummary."""
        runner = self._make_runner()

        # Mock create_agent_runtime
        mock_rt = MagicMock()
        mock_rt.config = runner._parent_config
        mock_rt.llm_provider = MagicMock()
        mock_rt.tool_registry = MagicMock()
        mock_rt.system_prompt = "test prompt"

        with patch("ayder_cli.agents.runner.create_agent_runtime", return_value=mock_rt), \
             patch("ayder_cli.agents.runner.ChatLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run = AsyncMock()

            result = await runner.run("Review this code")

        assert isinstance(result, AgentSummary)
        assert result.agent_name == "test-agent"

    @pytest.mark.anyio
    async def test_run_passes_configured_agent_identity_prompt_to_chat_loop(self):
        """AgentRunner sends the configured agent name in the ChatLoop system prompt."""
        agent_cfg = AgentConfig(
            name="file_lister",
            system_prompt="You are a filesystem specialist.",
        )
        runner = self._make_runner(agent_config=agent_cfg)

        mock_rt = MagicMock()
        mock_rt.config = runner._parent_config
        mock_rt.llm_provider = MagicMock()
        mock_rt.tool_registry = MagicMock()
        mock_rt.system_prompt = (
            "You are the specialized agent named 'file_lister'.\n"
            "When asked for your agent name, report this configured name exactly.\n\n"
            "You are a filesystem specialist."
        )

        with patch("ayder_cli.agents.runner.create_agent_runtime", return_value=mock_rt), \
             patch("ayder_cli.agents.runner.ChatLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run = AsyncMock()

            result = await runner.run("What is your configured agent name?")

        messages = MockLoop.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": mock_rt.system_prompt}
        assert "specialized agent named 'file_lister'" in messages[0]["content"]
        assert messages[1] == {"role": "user", "content": "What is your configured agent name?"}
        assert result.agent_name == "file_lister"

    @pytest.mark.anyio
    async def test_run_timeout(self):
        """AgentRunner.run() produces timeout summary when exceeding timeout."""
        runner = self._make_runner(timeout=0.01)  # 10ms timeout

        mock_rt = MagicMock()
        mock_rt.config = runner._parent_config
        mock_rt.llm_provider = MagicMock()
        mock_rt.tool_registry = MagicMock()
        mock_rt.system_prompt = "test"

        async def slow_run(**kwargs):
            await asyncio.sleep(5)

        with patch("ayder_cli.agents.runner.create_agent_runtime", return_value=mock_rt), \
             patch("ayder_cli.agents.runner.ChatLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run = slow_run

            result = await runner.run("Do something")

        assert result.status == "timeout"
        assert result.agent_name == "test-agent"
