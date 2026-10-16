"""Ollama compaction persists with a stable message prefix (finding F7).

``prepare_messages`` compacted a copy of the history. The next response
reported fewer prompt tokens, ``should_compact()`` turned false, and the full
old history came back without the summary. Near the threshold the request's
message prefix therefore changed on every turn, defeating prefix (KV) cache
reuse, and a single oversized unit could be folded into the summary so the
model never saw the request.

These tests prove message-level prefix stability under the manager's contract
(same model/tools, ``max_history=0``, append-only history, no in-place edits).
They do not, and cannot, prove a server-side cache hit.
"""

from __future__ import annotations

import copy
import json

from ayder_cli.core.ollama_context_manager import OllamaContextManager

HIGH = {"prompt_tokens": 600, "completion_tokens": 10}
LOW = {"prompt_tokens": 100, "completion_tokens": 10}
HEADER = "[Previous conversation summary]"


def _manager() -> OllamaContextManager:
    # ceiling 1000, reserve 0.3 -> budget 700; threshold 0.5 -> compact at 350.
    m = OllamaContextManager(
        provisional_context_length=1000, reserve_ratio=0.3, compaction_threshold=0.5
    )
    m.freeze_system_prompt("System.", [])
    return m


def _history(pairs: int, tag: str = "q") -> list[dict]:
    msgs = [{"role": "system", "content": "System."}]
    for i in range(pairs):
        msgs.append({"role": "user", "content": f"{tag}{i} question"})
        msgs.append({"role": "assistant", "content": f"{tag}{i} answer"})
    return msgs


def _summary(request: list[dict]) -> dict | None:
    if len(request) > 1 and str(request[1].get("content", "")).startswith(HEADER):
        return request[1]
    return None


def _compacted(m: OllamaContextManager) -> int:
    return m.get_stats().compaction_count


def test_summary_survives_the_next_low_usage_turn():
    """Baseline regression: the next turn sends the full history, no summary."""
    m, history = _manager(), _history(10)
    m.update_from_response(HIGH)
    first = m.prepare_messages(history)
    assert _summary(first) is not None
    m.update_from_response(LOW)
    history.append({"role": "user", "content": "next"})
    second = m.prepare_messages(history)
    assert _summary(second) is not None
    assert len(second) == len(first) + 1


def test_request_after_compaction_extends_previous_request():
    """Baseline regression: each later request starts with the previous one."""
    m, history = _manager(), _history(10)
    m.update_from_response(HIGH)
    requests = [m.prepare_messages(history)]
    for turn in range(3):
        m.update_from_response(LOW)
        history.append({"role": "user", "content": f"turn {turn}"})
        history.append({"role": "assistant", "content": f"reply {turn}"})
        requests.append(m.prepare_messages(history))
    for before, after in zip(requests, requests[1:]):
        assert after[: len(before)] == before
        assert [json.dumps(x) for x in after[: len(before)]] == [
            json.dumps(x) for x in before
        ]


def test_summary_is_the_same_object_between_compactions():
    """Baseline regression: there is no summary on the next turn today."""
    m, history = _manager(), _history(10)
    m.update_from_response(HIGH)
    first = m.prepare_messages(history)
    m.update_from_response(LOW)
    history.append({"role": "user", "content": "next"})
    second = m.prepare_messages(history)
    assert _summary(first) is not None and _summary(second) is _summary(first)


def test_caller_history_and_dicts_are_never_mutated():
    """Preservation: the caller's list and message dicts are left untouched."""
    m, history = _manager(), _history(10)
    snapshot = copy.deepcopy(history)
    ids = [id(x) for x in history]
    for usage in (HIGH, LOW, HIGH, LOW):
        m.update_from_response(usage)
        m.prepare_messages(history)
    assert history == snapshot
    assert [id(x) for x in history] == ids


def test_newest_unit_is_never_compacted():
    """Baseline regression: a lone oversized request is folded into the summary."""
    m = _manager()
    history = [{"role": "system", "content": "System."},
               {"role": "user", "content": "please refactor " + "x" * 3000}]
    m.update_from_response(HIGH)
    request = m.prepare_messages(history)
    assert request[-1] is history[-1]
    assert _summary(request) is None


def test_tool_units_stay_atomic_across_the_boundary():
    """Preservation: survivors start on a unit boundary; tool results keep
    their assistant call."""
    m = _manager()
    history = [{"role": "system", "content": "System."}]
    for i in range(6):
        history.append({"role": "user", "content": f"q{i}"})
        history.append({"role": "assistant", "content": "",
                        "tool_calls": [{"id": f"c{i}", "type": "function",
                                        "function": {"name": "read_file",
                                                     "arguments": "{}"}}]})
        history.append({"role": "tool", "tool_call_id": f"c{i}", "name": "read_file",
                        "content": "r"})
    m.update_from_response(HIGH)
    request = m.prepare_messages(history)
    assert _summary(request) is not None
    for i, msg in enumerate(request):
        if msg["role"] == "tool":
            prior = request[i - 1]
            assert prior["role"] == "tool" or prior.get("tool_calls"), i


def test_no_second_compaction_before_new_measurement():
    """Baseline regression: a stale reading compacts again on the next call."""
    m, history = _manager(), _history(10)
    m.update_from_response(HIGH)
    m.prepare_messages(history)
    history.append({"role": "user", "content": "retry"})
    m.prepare_messages(history)  # no update_from_response in between
    assert _compacted(m) == 1


def test_rewritten_history_is_not_compacted_on_stale_usage():
    """Baseline regression: a replacement history is compacted at once using
    the old history's measurement."""
    for rewrite in ("pending_compact", "session_load"):
        m, history = _manager(), _history(10)
        m.update_from_response(HIGH)
        m.prepare_messages(history)
        assert _compacted(m) == 1
        if rewrite == "pending_compact":
            new = [history[0], {"role": "user", "content": "[Previous session summary]"}]
            new += history[-4:]
        else:
            new = copy.deepcopy(history)  # equal content, new objects
        request = m.prepare_messages(new)
        assert _compacted(m) == 1, rewrite
        assert request[1:] == new[1:], rewrite
        m.update_from_response(HIGH)
        m.prepare_messages(new)
        assert _compacted(m) == 2, rewrite


def test_usage_without_prompt_tokens_keeps_compaction_blocked():
    """Baseline regression: a response lacking prompt_tokens must not unblock."""
    m, history = _manager(), _history(10)
    m.update_from_response(HIGH)
    m.prepare_messages(history)
    new = copy.deepcopy(history)
    m.prepare_messages(new)
    m.update_from_response({"completion_tokens": 5})
    m.prepare_messages(new)
    assert _compacted(m) == 1


def test_empty_history_resets_generation():
    """An empty history ends the generation: the old summary must not
    reappear, and nothing compacts until a fresh measurement."""
    m, history = _manager(), _history(10)
    m.update_from_response(HIGH)
    m.prepare_messages(history)
    assert m.prepare_messages(history[:1]) == [{"role": "system", "content": "System."}]
    request = m.prepare_messages(history)
    assert _summary(request) is None
    assert request[1:] == history[1:]
    assert _compacted(m) == 1


def test_repeated_compaction_keeps_one_header_and_prior_lines():
    """Three compactions: one header, the first summary's lines retained,
    the summary object stable between compactions."""
    m, history = _manager(), _history(12)
    summaries = []
    for round_ in range(3):
        m.update_from_response(HIGH)
        request = m.prepare_messages(history)
        summaries.append(_summary(request))
        m.update_from_response(LOW)
        history.append({"role": "user", "content": f"r{round_}"})
        history.append({"role": "assistant", "content": f"a{round_}"})
        between = m.prepare_messages(history)
        assert _summary(between) is summaries[-1]
    assert _compacted(m) == 3
    first_lines = summaries[0]["content"].split("\n")[1:]
    last = summaries[-1]["content"]
    assert last.count(HEADER) == 1
    assert all(line in last.split("\n") for line in first_lines)


def test_summary_cap_and_single_overlong_line():
    """New interface: the merged body is capped at 8000 chars, keeping the
    newest lines; one line over the cap is cut to 7999 chars plus '…'."""
    m = _manager()
    lines = [f"User asked: {i:05d} " + "z" * 90 for i in range(200)]
    merged = m._merge_summary(None, lines)
    head, body = merged.split("\n", 1)
    assert head == HEADER
    assert len(body) <= 8000
    assert body.split("\n")[-1] == lines[-1]
    assert lines[0] not in body

    again = m._merge_summary(merged, ["Tool read_file returned result"])
    assert again.count(HEADER) == 1
    assert again.endswith("Tool read_file returned result")

    huge = m._merge_summary(None, ["y" * 9000])
    body = huge.split("\n", 1)[1]
    assert len(body) == 8000 and body.endswith("…")
