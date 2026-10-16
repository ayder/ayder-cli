"""OllamaContextManager carries folded active skills in its summary (spec 4.8).

Kind: baseline regression. On the parent, a folded skill block is simply gone
from the request.
"""

from __future__ import annotations

import json

from ayder_cli.core.ollama_context_manager import OllamaContextManager
from ayder_cli.core.skills import RESUPPLY_HEADER, unload_notice


def _block(name: str, size: int = 40) -> str:
    return f"### SKILL LOADED: {name}\nSource: user (x)\n\n{'r' * size}\n\n### END SKILL: {name}"


def _load_unit(name: str, call_id: str, size: int = 40) -> list[dict]:
    call = {"id": call_id, "type": "function",
            "function": {"name": "skill", "arguments": json.dumps({"action": "load", "name": name})}}
    return [
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": call_id, "name": "skill", "content": _block(name, size)},
    ]


HIGH = {"prompt_tokens": 600, "completion_tokens": 10}
LOW = {"prompt_tokens": 100, "completion_tokens": 10}
HEADER = "[Previous conversation summary]"


def _ollama() -> OllamaContextManager:
    # ceiling 1000, reserve 0.3 -> budget 700; threshold 0.5 -> compact at 350.
    m = OllamaContextManager(provisional_context_length=1000, reserve_ratio=0.3, compaction_threshold=0.5)
    m.freeze_system_prompt("System.", [])
    return m


def _ollama_history() -> list[dict]:
    msgs = [{"role": "system", "content": "System."}, {"role": "user", "content": "start"}]
    msgs.extend(_load_unit("eng", "c1"))
    for i in range(10):
        msgs.append({"role": "user", "content": f"q{i} question"})
        msgs.append({"role": "assistant", "content": f"q{i} answer"})
    return msgs


def test_folded_skill_rides_in_the_summary():
    """Baseline regression: the folded block is gone from the request today."""
    m, history = _ollama(), _ollama_history()
    m.update_from_response(HIGH)
    out = m.prepare_messages(history)
    summary = out[1]["content"]
    assert summary.startswith(HEADER)
    assert summary.endswith(RESUPPLY_HEADER + "\n\n" + _block("eng"))


def test_prefix_is_stable_between_compactions_with_a_resupply():
    """Preservation of F7: each later request starts with the previous one."""
    m, history = _ollama(), _ollama_history()
    m.update_from_response(HIGH)
    requests = [m.prepare_messages(history)]
    for turn in range(3):
        m.update_from_response(LOW)
        history.append({"role": "user", "content": f"turn {turn}"})
        history.append({"role": "assistant", "content": f"reply {turn}"})
        requests.append(m.prepare_messages(history))
    for before, after in zip(requests, requests[1:]):
        assert [json.dumps(x) for x in after[: len(before)]] == [json.dumps(x) for x in before]


def test_reset_drops_the_resupply_with_the_summary():
    m, history = _ollama(), _ollama_history()
    m.update_from_response(HIGH)
    m.prepare_messages(history)
    fresh = [{"role": "system", "content": "System."}, {"role": "user", "content": "new"}]
    out = m.prepare_messages(fresh)
    assert out == fresh


def test_skill_loaded_after_compaction_is_ordinary_history():
    m, history = _ollama(), _ollama_history()
    m.update_from_response(HIGH)
    m.prepare_messages(history)
    m.update_from_response(LOW)
    history.extend(_load_unit("late", "c9"))
    out = m.prepare_messages(history)
    assert "### SKILL LOADED: late" not in out[1]["content"]
    assert out[-1]["content"] == _block("late")


def _unload_unit(name: str, call_id: str) -> list[dict]:
    call = {"id": call_id, "type": "function",
            "function": {"name": "skill", "arguments": json.dumps({"action": "unload", "name": name})}}
    return [
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": call_id, "name": "skill", "content": unload_notice([name])},
    ]


def _contents(out: list[dict]) -> str:
    return "\n".join(str(m.get("content")) for m in out)


def test_summary_falls_back_to_names_when_the_composed_request_does_not_fit():
    """Review B3: the bodies fit in half the budget, but not beside the rest."""
    m = _ollama()
    history = [{"role": "system", "content": "System."}, {"role": "user", "content": "start"}]
    history.extend(_load_unit("eng", "c1", size=1000))
    for i in range(10):
        history.append({"role": "user", "content": f"q{i} " + "x" * 93})
        history.append({"role": "assistant", "content": f"a{i} " + "x" * 93})
    m.update_from_response(HIGH)
    summary = m.prepare_messages(history)[1]["content"]
    assert summary.startswith(HEADER)
    assert "### SKILLS ACTIVE BUT TRIMMED: eng" in summary
    assert "r" * 1000 not in summary


def test_cap_resupplies_a_load_it_removes_before_any_compaction():
    """Review B2: a max_history cap alone must not erase an active skill."""
    m, history = _ollama(), _ollama_history()
    out = m.prepare_messages(history, max_history=2)
    assert _block("eng") in _contents(out)
    assert out[-1] == history[-1]


def test_cap_resupplies_a_skill_loaded_after_compaction():
    m, history = _ollama(), _ollama_history()
    m.update_from_response(HIGH)
    m.prepare_messages(history)
    m.update_from_response(LOW)
    history.extend(_load_unit("late", "c9"))
    m.prepare_messages(history)
    history.extend([{"role": "user", "content": "more"}, {"role": "assistant", "content": "ok"}])
    out = m.prepare_messages(history, max_history=2)
    assert _block("late") in _contents(out)


def test_cap_keeps_the_unload_of_a_skill_in_the_summary():
    """Review B2: the summary still holds eng's body, so its unload must stay visible."""
    m, history = _ollama(), _ollama_history()
    m.update_from_response(HIGH)
    assert _block("eng") in m.prepare_messages(history)[1]["content"]
    m.update_from_response(LOW)
    history.extend(_unload_unit("eng", "c8"))
    m.prepare_messages(history)
    history.extend([{"role": "user", "content": "more"}, {"role": "assistant", "content": "ok"}])
    out = m.prepare_messages(history, max_history=2)
    assert "### SKILL UNLOADED: eng" in _contents(out)
