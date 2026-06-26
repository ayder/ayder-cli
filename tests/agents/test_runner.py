"""Tests for AgentRunner — wraps one ChatLoop execution per agent dispatch."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.runner import AgentRunner, AgentRunOutcome


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

    def test_cancel(self):
        runner = self._make_runner()
        assert runner.cancel() is True
        assert runner.status == "cancelled"

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
        # The mocked loop produced no assistant message, so the deliverable is
        # vacuous -> run() settles 'error' (F1b) rather than a hollow "done".
        assert isinstance(result, AgentRunOutcome)
        assert result.status == "error"
        assert "deliverable" in (result.error or "").lower()

    @pytest.mark.anyio
    async def test_run_timeout(self):
        """AgentRunner.run() produces error outcome when exceeding timeout."""
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

        assert result.status == "error"
        assert "timeout" in result.error.lower()
        # The orchestrator must be told this was a timeout AND how to recover:
        # re-dispatch with a larger timeout, not a smaller scope (see real-run
        # misdiagnosis where the orchestrator shrank scope instead).
        assert "timeout_s" in result.error
        assert "more time" in result.error.lower()


def _fake_rt():
    rt = MagicMock()
    rt.system_prompt = "sys"
    rt.config = MagicMock(model="m", provider="p", num_ctx=1, max_output_tokens=1,
                          stop_sequences=[], tool_tags=None, max_history_messages=30)
    return rt


@pytest.mark.anyio
async def test_run_returns_final_message_not_transcript(tmp_path):
    from ayder_cli.core.context import ProjectContext
    cfg = AgentConfig(name="reporter", system_prompt="Write a report.")
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(), project_ctx=ProjectContext(str(tmp_path)),
        process_manager=MagicMock(), permissions=set(), timeout=5, run_id=42, generation=3,
    )

    def loop_ctor(**kwargs):
        msgs = kwargs["messages"]
        m = MagicMock()
        async def _run(*a, **k):
            msgs.append({"role": "assistant", "content": "Let me check the files."})
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]})
            msgs.append({"role": "tool", "content": "file contents"})
            msgs.append({"role": "assistant", "content": "# Final Report\nAll done."})
        m.run = _run
        return m

    import ayder_cli.agents.runner as rm
    with patch.object(rm, "create_agent_runtime", return_value=_fake_rt()), \
         patch.object(rm, "ChatLoop", side_effect=loop_ctor):
        out = await runner.run("Write the report")

    assert isinstance(out, AgentRunOutcome)
    assert out.status == "done"
    assert out.content == "# Final Report\nAll done."
    assert "Let me check the files." not in out.content
    assert out.note_path is not None
    assert (tmp_path / out.note_path).read_text(encoding="utf-8").count("# Final Report") == 1


@pytest.mark.anyio
async def test_run_reports_error_when_stream_fails_after_text():
    cfg = AgentConfig(name="x", system_prompt="s")
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(), project_ctx=MagicMock(),
        process_manager=MagicMock(), permissions=set(), timeout=5, run_id=1, generation=1,
    )

    def loop_ctor(**kwargs):
        cb = kwargs["callbacks"]
        msgs = kwargs["messages"]
        m = MagicMock()
        async def _run(*a, **k):
            msgs.append({"role": "assistant", "content": "intermediate text"})
            cb.last_content = "intermediate text"          # cumulative, non-empty
            cb.last_system_error = "Error: stream failed"  # late failure
        m.run = _run
        return m

    import ayder_cli.agents.runner as rm
    with patch.object(rm, "create_agent_runtime", return_value=_fake_rt()), \
         patch.object(rm, "ChatLoop", side_effect=loop_ctor):
        out = await runner.run("t")

    assert out.status == "error"               # NOT "done"
    assert out.error == "Error: stream failed"


def test_persist_note_uses_notes_ctx_not_project_ctx(tmp_path):
    """When notes_ctx differs from project_ctx (worktree case), the note is
    written under notes_ctx (the parent), not the worktree project_ctx."""
    from ayder_cli.agents.runner import AgentRunner
    from ayder_cli.core.context import ProjectContext

    parent = tmp_path / "parent"
    worktree = tmp_path / "parent" / ".ayder" / "worktrees" / "x"
    parent.mkdir(parents=True)
    worktree.mkdir(parents=True)

    class _Cfg:
        name = "coder"
        system_prompt = "x"

    runner = AgentRunner(
        agent_config=_Cfg(), parent_config=_Cfg(),
        project_ctx=ProjectContext(str(worktree)),
        notes_ctx=ProjectContext(str(parent)),
        process_manager=None, permissions={"r"}, run_id=7, generation=0,
    )
    rel = runner._persist_note(task="do x", status="done", content="did x", error=None)
    assert rel is not None
    # Note exists under the PARENT notes dir, not the worktree's.
    parent_notes = parent / ".ayder" / "notes"
    assert parent_notes.is_dir() and any(parent_notes.iterdir())
    worktree_notes = worktree / ".ayder" / "notes"
    assert not worktree_notes.exists()


def test_final_message_skips_think_blocks():
    msgs = [
        {"role": "assistant", "content": "<think>reasoning</think>"},
        {"role": "assistant", "content": "Real answer."},
    ]
    assert AgentRunner._final_message(msgs) == "Real answer."


def test_final_message_returns_last_real_skipping_trailing_think():
    msgs = [
        {"role": "assistant", "content": "First answer."},
        {"role": "assistant", "content": "<think>re-thinking</think>"},
    ]
    assert AgentRunner._final_message(msgs) == "First answer."


def test_final_message_empty_when_no_real_assistant_text():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "content": "tool output"},
    ]
    assert AgentRunner._final_message(msgs) == ""


def test_is_vacuous_detects_empty_and_echo_only():
    # empty / whitespace
    assert AgentRunner._is_vacuous("") is True
    assert AgentRunner._is_vacuous("   \n\t ") is True
    # echo-only (the mandated task_id/task_preview lines and a lone verdict)
    assert AgentRunner._is_vacuous("task_id: none") is True
    assert AgentRunner._is_vacuous("task_id: TASK-1\nVERDICT: APPROVED") is True
    assert AgentRunner._is_vacuous("task_preview: x\ntask_id: none") is True
    # real deliverable -> not vacuous
    assert AgentRunner._is_vacuous("task_id: TASK-1\nLGTM, ships.\nVERDICT: APPROVED") is False
    assert AgentRunner._is_vacuous("# Plan\n1. do the thing") is False


@pytest.mark.anyio
async def test_run_flags_echo_only_deliverable_as_error(tmp_path):
    """F1b: an agent that only echoes the task_id (no real deliverable) must
    settle 'error', not 'done' with a placeholder."""
    from ayder_cli.core.context import ProjectContext
    cfg = AgentConfig(name="coder", system_prompt="x")
    runner = AgentRunner(
        agent_config=cfg, parent_config=MagicMock(),
        project_ctx=ProjectContext(str(tmp_path)), process_manager=MagicMock(),
        permissions=set(), timeout=5, run_id=1, generation=0,
    )

    def loop_ctor(**kwargs):
        msgs = kwargs["messages"]
        m = MagicMock()
        async def _run(*a, **k):
            msgs.append({"role": "assistant", "content": "task_id: none"})
        m.run = _run
        return m

    import ayder_cli.agents.runner as rm
    with patch.object(rm, "create_agent_runtime", return_value=_fake_rt()), \
         patch.object(rm, "ChatLoop", side_effect=loop_ctor):
        out = await runner.run("do it")

    assert out.status == "error"
    assert "deliverable" in (out.error or "").lower()
