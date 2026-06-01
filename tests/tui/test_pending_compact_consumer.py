"""Tests for consuming app._pending_compact at chat-loop boundaries."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_app(messages, pending):
    app = MagicMock()
    app.messages = messages
    app._pending_compact = pending
    app.context_manager = MagicMock()
    return app


@pytest.mark.anyio
async def test_consumer_no_pending_is_noop():
    from ayder_cli.tui.app import apply_pending_compact

    app = _make_app([{"role": "user", "content": "x"}], pending=None)
    await apply_pending_compact(app, app.messages)

    assert len(app.messages) == 1


@pytest.mark.anyio
async def test_consumer_wipes_messages_preserves_system_and_summary():
    from ayder_cli.tui.app import apply_pending_compact

    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "old1"},
        {"role": "assistant", "content": "old2"},
        {"role": "user", "content": "old3"},
    ]
    pending = {
        "summary_name": "auto-compact-X",
        "summary_content": "the summary",
        "keep_last_n": 0,
    }
    app = _make_app(messages, pending)

    await apply_pending_compact(app, app.messages)

    assert app.messages[0] == {"role": "system", "content": "SYS"}
    assert any("the summary" in str(message.get("content", "")) for message in app.messages)
    assert len(app.messages) == 2
    assert app._pending_compact is None


@pytest.mark.anyio
async def test_consumer_preserves_keep_last_n_exchanges():
    from ayder_cli.tui.app import apply_pending_compact

    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2-with-tool"},
        {"role": "tool", "content": "tool-output"},
        {"role": "assistant", "content": "a2-followup"},
    ]
    pending = {
        "summary_name": "auto",
        "summary_content": "sum",
        "keep_last_n": 1,
    }
    app = _make_app(messages, pending)

    await apply_pending_compact(app, app.messages)

    assert app.messages[0]["role"] == "system"
    assert "sum" in str(app.messages[1].get("content", ""))
    assert app.messages[2:] == [
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2-with-tool"},
        {"role": "tool", "content": "tool-output"},
        {"role": "assistant", "content": "a2-followup"},
    ]
    assert app._pending_compact is None


@pytest.mark.anyio
async def test_consumer_keep_last_n_zero_drops_all_non_system():
    from ayder_cli.tui.app import apply_pending_compact

    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]
    pending = {"summary_name": "a", "summary_content": "s", "keep_last_n": 0}
    app = _make_app(messages, pending)

    await apply_pending_compact(app, app.messages)

    assert len(app.messages) == 2
    assert app.messages[0]["role"] == "system"


@pytest.mark.anyio
async def test_consumer_resets_context_manager():
    from ayder_cli.tui.app import apply_pending_compact

    app = _make_app(
        [{"role": "system", "content": "SYS"}],
        pending={"summary_name": "a", "summary_content": "s", "keep_last_n": 0},
    )

    await apply_pending_compact(app, app.messages)

    app.context_manager.clear.assert_called_once()


@pytest.mark.anyio
async def test_composed_hook_runs_pending_compact_and_agent_summaries():
    from ayder_cli.tui.app import apply_pending_compact

    app = _make_app(
        [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "u1"},
        ],
        pending={"summary_name": "a", "summary_content": "the-summary", "keep_last_n": 0},
    )
    fake_summary = MagicMock()
    fake_summary.format_for_injection.return_value = "AGENT-SUMMARY"
    agent_registry = MagicMock()
    agent_registry.drain_summaries.return_value = [fake_summary]

    async def composed(messages):
        await apply_pending_compact(app, messages)
        summaries = agent_registry.drain_summaries()
        for summary in summaries:
            messages.append({"role": "system", "content": summary.format_for_injection()})

    await composed(app.messages)

    assert app.messages[0]["role"] == "system"
    assert app.messages[0]["content"] == "SYS"
    assert "the-summary" in app.messages[1]["content"]
    assert app.messages[-1]["content"] == "AGENT-SUMMARY"
