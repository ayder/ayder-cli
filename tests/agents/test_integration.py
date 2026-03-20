"""Integration test for the multi-agent system end-to-end."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.summary import AgentSummary
from ayder_cli.agents.tool import create_call_agent_handler
from ayder_cli.core.config import Config


class TestAgentIntegration:
    def test_config_to_dispatch_flow(self):
        """End-to-end: parse config → create registry → dispatch (fire-and-forget)."""
        # 1. Parse config with agents
        data = {
            "app": {"provider": "openai", "agent_timeout": 10},
            "llm": {"openai": {"driver": "openai", "model": "test", "api_key": "k", "num_ctx": 4096}},
            "agents": {
                "reviewer": {"system_prompt": "You review code."},
            },
        }
        cfg = Config(**data)
        assert "reviewer" in cfg.agents
        assert cfg.agent_timeout == 10

        # 2. Create registry
        registry = AgentRegistry(
            agents=cfg.agents,
            parent_config=cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r", "w"},
            agent_timeout=cfg.agent_timeout,
        )

        # 3. Verify capability prompts
        prompts = registry.get_capability_prompts()
        assert "reviewer" in prompts

        # 4. Dispatch via tool handler (sync, fire-and-forget)
        with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
            mock_runner = MockRunner.return_value
            mock_runner.agent_name = "reviewer"
            mock_runner.run = AsyncMock(return_value=AgentSummary(
                agent_name="reviewer", status="completed", summary="Found 2 issues.", error=None,
            ))

            handler = create_call_agent_handler(registry)

            # Need a mock event loop for dispatch to succeed
            mock_loop = MagicMock()
            registry.set_loop(mock_loop)

            with patch("ayder_cli.agents.registry.asyncio.run_coroutine_threadsafe"):
                result = handler(name="reviewer", task="Review auth.py")

        # dispatch() returns immediately with status message
        assert "dispatched" in result.lower()
        assert "reviewer" in result

    def test_summary_injection_format(self):
        """AgentSummary.format_for_injection produces valid system message content."""
        summary = AgentSummary(
            agent_name="test-agent",
            status="completed",
            summary="All tests pass. Coverage at 95%.",
            error=None,
        )
        text = summary.format_for_injection()
        assert "[Agent" in text
        assert "completed" in text
        assert "All tests pass" in text

    def test_config_no_agents_no_capability_prompts(self):
        """When no agents configured, capability prompts are empty."""
        cfg = Config()
        registry = AgentRegistry(
            agents=cfg.agents,
            parent_config=cfg,
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        assert registry.get_capability_prompts() == ""

    @pytest.mark.anyio
    async def test_summary_arrives_via_queue(self):
        """After agent completes, summary is available via drain_summaries."""
        registry = AgentRegistry(
            agents={"test": AgentConfig(name="test", system_prompt="test")},
            parent_config=MagicMock(),
            project_ctx=MagicMock(),
            process_manager=MagicMock(),
            permissions={"r"},
            agent_timeout=300,
        )
        # Simulate a summary being queued (as would happen after agent completion)
        summary = AgentSummary(
            agent_name="test", status="completed", summary="Done.", error=None
        )
        await registry._summary_queue.put(summary)

        # drain_summaries returns it
        summaries = registry.drain_summaries()
        assert len(summaries) == 1
        assert summaries[0].agent_name == "test"

        # Queue is now empty
        assert registry.drain_summaries() == []


@pytest.mark.anyio
async def test_batch_wakeup_pattern_only_fires_when_all_agents_complete():
    """Validates the batch wake-up pattern: only trigger when active_count == 0."""
    from ayder_cli.agents.config import AgentConfig
    from ayder_cli.agents.registry import AgentRegistry
    from ayder_cli.agents.summary import AgentSummary
    from unittest.mock import MagicMock

    wakeup_calls = []

    def on_complete(run_id, summary):
        # This is the pattern app.py will use
        if reg.active_count == 0:
            wakeup_calls.append(summary)

    configs = {
        "a": AgentConfig(name="a", system_prompt="agent a"),
        "b": AgentConfig(name="b", system_prompt="agent b"),
    }
    reg = AgentRegistry(
        agents=configs,
        parent_config=MagicMock(),
        project_ctx=MagicMock(),
        process_manager=MagicMock(),
        permissions={"r"},
        on_complete=on_complete,
    )

    mock_a = MagicMock()
    mock_a.agent_name = "a"
    mock_b = MagicMock()
    mock_b.agent_name = "b"
    reg._active[1] = mock_a
    reg._active[2] = mock_b

    summary_a = AgentSummary(agent_name="a", status="completed", summary="done a", error=None)
    await reg._summary_queue.put(summary_a)
    reg._active.pop(1)
    on_complete(1, summary_a)
    assert len(wakeup_calls) == 0  # b is still running

    summary_b = AgentSummary(agent_name="b", status="completed", summary="done b", error=None)
    await reg._summary_queue.put(summary_b)
    reg._active.pop(2)
    on_complete(2, summary_b)
    assert len(wakeup_calls) == 1  # Now all done, wake up fires
