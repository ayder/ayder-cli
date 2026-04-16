"""Regression: OllamaContextManager must honor max_history parameter.

Opus47 finding #3: max_history was accepted to satisfy the Protocol but
never read in the body. ChatLoop passes config.max_history expecting
truncation; for Ollama it was a silent no-op.
"""
from ayder_cli.core.ollama_context_manager import OllamaContextManager


def make_manager(ctx_length=1_000_000):
    return OllamaContextManager(
        provisional_context_length=ctx_length,
        reserve_ratio=0.3,
        compaction_threshold=0.7,
    )


def test_max_history_zero_keeps_everything():
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])
    msgs = [{"role": "system", "content": "S"}]
    for i in range(6):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})

    out = mgr.prepare_messages(msgs, max_history=0)
    # system + 12 others
    assert len(out) == 13


def test_max_history_trims_from_head():
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])
    msgs = [{"role": "system", "content": "S"}]
    for i in range(6):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})

    out = mgr.prepare_messages(msgs, max_history=4)

    # system + 4 recent (u4, a4, u5, a5)
    assert len(out) == 5
    assert out[0]["role"] == "system"
    assert out[1]["content"] == "u4"
    assert out[2]["content"] == "a4"
    assert out[3]["content"] == "u5"
    assert out[4]["content"] == "a5"


def test_max_history_respects_tool_call_units():
    """An assistant+tool_calls unit and its tool_result must stay together."""
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])
    msgs = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "u1"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "t1",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }],
        },
        {"role": "tool", "tool_call_id": "t1", "name": "read_file", "content": "x"},
        {"role": "assistant", "content": "a1"},
    ]

    # Ask for last 3 messages — that cuts through the tool-call unit.
    out = mgr.prepare_messages(msgs, max_history=3)

    body = out[1:] if out and out[0]["role"] == "system" else out
    # Every tool message must be preceded by an assistant-with-tool_calls
    for i, m in enumerate(body):
        if m.get("role") == "tool":
            assert i > 0, "tool message orphaned at head of history"
            prev = body[i - 1]
            assert prev.get("role") == "assistant" and prev.get("tool_calls"), \
                "tool message not preceded by its assistant tool_calls unit"
    # We should not have partial units; allow up to 4 for unit atomicity
    assert 0 < len(body) <= 4


def test_max_history_handles_compaction_summary_position():
    """When compaction produces a summary and max_history is set, both survive correctly."""
    mgr = OllamaContextManager(
        provisional_context_length=1000,
        reserve_ratio=0.3,
        compaction_threshold=0.7,
    )
    mgr.freeze_system_prompt("S", [])

    # Force compaction trigger by setting real tokens over budget
    mgr._real_prompt_tokens = 600  # > 700 * 0.7 = 490

    msgs = [{"role": "system", "content": "S"}]
    for i in range(8):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})

    out = mgr.prepare_messages(msgs, max_history=4)

    assert out[0]["role"] == "system"
    # A summary message may be present after system
    body_without_summary = [m for m in out[1:] if not str(m.get("content", "")).startswith(
        "[Previous conversation summary]"
    )]
    # Body-without-summary should be <= max_history
    assert len(body_without_summary) <= 4
