"""DefaultContextManager re-supplies active skills a trim removes (spec 4.8).

Kind: baseline regression. On the parent (MR A), a trimmed skill block is
simply gone from the request.
"""

from __future__ import annotations

import copy
import json
from unittest.mock import MagicMock

from ayder_cli.core.default_context_manager import DefaultContextManager
from ayder_cli.core.skills import RESUPPLY_HEADER, unload_notice

MARKER = "[... history truncated for context efficiency ...]"


def _block(name: str, size: int = 40) -> str:
    return f"### SKILL LOADED: {name}\nSource: user (x)\n\n{'r' * size}\n\n### END SKILL: {name}"


def _load_unit(name: str, call_id: str, size: int = 40) -> list[dict]:
    call = {"id": call_id, "type": "function",
            "function": {"name": "skill", "arguments": json.dumps({"action": "load", "name": name})}}
    return [
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": call_id, "name": "skill", "content": _block(name, size)},
    ]


# -- DefaultContextManager -------------------------------------------------------


def _default(max_context_tokens: int = 1000) -> DefaultContextManager:
    cfg = MagicMock()
    cfg.model = "unknown"
    cfg.provider = "ollama"  # char-based estimates, no tiktoken
    cfg.num_ctx = max_context_tokens
    cfg.context_manager.enabled = True
    cfg.context_manager.max_context_tokens = max_context_tokens
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    cfg.context_manager.tool_result_compress_age = 5
    cfg.context_manager.max_tool_result_length = 2048
    cfg.context_manager.compress_tool_results = True
    cfg.context_manager.enable_compression = False
    m = DefaultContextManager.from_config(cfg)
    m.freeze_system_prompt("sys", [])
    return m


def _long_history(skill_units: list[list[dict]], filler: int = 30) -> list[dict]:
    history = [{"role": "system", "content": "sys"}, {"role": "user", "content": "start"}]
    for unit in skill_units:
        history.extend(unit)
    for i in range(filler):
        history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i} " + "x" * 120})
    history.append({"role": "user", "content": "the request"})
    return history


def test_in_budget_output_is_unchanged_with_a_skill():
    """Preservation: nothing trimmed, nothing re-supplied, byte for byte."""
    history = _long_history([_load_unit("eng", "c1")], filler=2)
    out = _default(100_000).prepare_messages(history)
    assert [json.dumps(m) for m in out] == [json.dumps(m) for m in history]


def test_trimmed_skill_is_resupplied_after_the_system_prompt():
    """Baseline regression: the trimmed block is gone from the request today."""
    history = _long_history([_load_unit("eng", "c1")])
    before = copy.deepcopy(history)
    out = _default().prepare_messages(history)
    assert out[0] == history[0]
    assert out[1]["role"] == "user"
    assert out[1]["content"].startswith(RESUPPLY_HEADER + "\n\n" + _block("eng"))
    assert out[-1] == history[-1]
    assert history == before  # the caller's history is never mutated
    roles = [m["role"] for m in out]
    assert all(not (a == b == "user") for a, b in zip(roles, roles[1:]))


def test_unloaded_skill_is_not_resupplied():
    """Preservation of the unload contract: an unloaded skill stays gone."""
    units = [_load_unit("eng", "c1"), [{"role": "tool", "tool_call_id": "c2", "name": "skill",
                                        "content": unload_notice(["eng"])}]]
    # The unload notice must follow an assistant tool call to be a valid unit.
    units[1].insert(0, {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c2", "type": "function", "function": {"name": "skill", "arguments": "{}"}}]})
    out = _default().prepare_messages(_long_history(units))
    assert all(RESUPPLY_HEADER not in str(m["content"]) for m in out)


def test_names_only_when_the_block_alone_does_not_fit():
    """Baseline regression: the request today has no trace of the skill."""
    history = _long_history([_load_unit("eng", "c1", size=6000)])
    out = _default().prepare_messages(history)
    assert out[1]["content"].startswith("### SKILLS ACTIVE BUT TRIMMED: eng\n")
    assert out[-1] == history[-1]


def test_trim_event_excludes_the_resupply(monkeypatch):
    seen: list[dict] = []
    monkeypatch.setattr(
        "ayder_cli.core.default_context_manager.emit_event",
        lambda channel, evt, **fields: seen.append(fields) if evt == "context_trim" else None,
    )
    history = _long_history([_load_unit("eng", "c1")])
    out = _default().prepare_messages(history)
    [event] = seen
    # The re-supply is either its own inserted message (ending with the
    # truncation marker) or merged into the first kept user message.
    inserted = 1 if out[1]["content"].endswith(MARKER) else 0
    assert event["after"] == len(out) - 1 - inserted


def test_compression_never_touches_a_skill_block():
    """Baseline regression: opt-in compression rewrites old skill blocks today."""
    m = _default(100_000)
    m._config.enable_compression = True
    m._config.max_tool_result_length = 10
    messages = [
        {"role": "system", "content": "sys"},
        *_load_unit("eng", "c1", size=400),
        {"role": "tool", "tool_call_id": "c9", "name": "read_file", "content": "y" * 400},
        {"role": "user", "content": "later"},
    ]
    for msg in messages:
        m.add_message(msg)
    m.compress_old_results(age_threshold=0)
    contents = [msg["content"] for msg in m._messages]
    assert _block("eng", 400) in contents
    assert "y" * 400 not in contents  # the control: other tool results are compressed


def test_only_dropped_skills_are_resupplied():
    history = _long_history([_load_unit("old", "c1")], filler=30)
    history[-1:-1] = _load_unit("new", "c2")  # just before the request: always kept
    out = _default().prepare_messages(history)
    text = out[1]["content"]
    assert _block("old") in text
    assert "### SKILL LOADED: new" not in text  # still in the window, not duplicated
    assert any(m.get("content") == _block("new") for m in out)


def test_resupply_merges_into_a_kept_user_message():
    # filler=4 ends ..., u2, a3, request; max_history=3 keeps u2, a3, request.
    history = _long_history([_load_unit("eng", "c1")], filler=4)
    out = _default(100_000).prepare_messages(history, max_history=3)
    assert len(out) == 4  # system, merged u2, a3, request: no extra message
    assert out[1]["content"] == RESUPPLY_HEADER + "\n\n" + _block("eng") + "\n\n" + history[-3]["content"]
    assert history[-3]["content"].startswith("m2 ")  # the caller's message is untouched


def test_resupply_is_its_own_message_before_a_non_user_message():
    # max_history=2 keeps a3, request: the re-supply cannot merge into a3.
    history = _long_history([_load_unit("eng", "c1")], filler=4)
    out = _default(100_000).prepare_messages(history, max_history=2)
    assert out[1] == {"role": "user", "content": RESUPPLY_HEADER + "\n\n" + _block("eng") + "\n\n" + MARKER}
    assert out[2]["role"] == "assistant"


def test_max_history_trim_resupplies():
    history = _long_history([_load_unit("eng", "c1")], filler=4)
    out = _default(100_000).prepare_messages(history, max_history=3)
    assert out[1]["content"].startswith(RESUPPLY_HEADER)


def test_names_only_when_the_newest_unit_leaves_no_room_for_the_blocks():
    """Review B1: the block fits alone, but not beside the mandatory newest unit."""
    history = _long_history([_load_unit("eng", "c1", size=2000)], filler=4)
    history[-1] = {"role": "user", "content": "q" * 2000}
    out = _default().prepare_messages(history, max_history=1)
    assert out[1]["content"].startswith("### SKILLS ACTIVE BUT TRIMMED: eng\n")
    assert "r" * 2000 not in out[1]["content"]
    assert out[-1] == history[-1]
