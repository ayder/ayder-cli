"""Tests for session save/load/resolve (core/session.py)."""

import json
import re

import pytest

from ayder_cli.core.session import (
    SessionAmbiguous,
    SessionNotFound,
    load_session,
    new_session_id,
    resolve_session_id,
    save_session,
    sessions_dir,
)


def _msgs():
    return [
        {"role": "system", "content": "SYS PROMPT"},
        {"role": "user", "content": "fix the bug"},
        {
            "role": "assistant",
            "content": "on it",
            "tool_calls": [{"id": "c1", "function": {"name": "bash"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "done"},
    ]


def test_sessions_dir(tmp_path):
    assert sessions_dir(tmp_path) == tmp_path / ".ayder" / "sessions"


def test_new_session_id_format(tmp_path):
    sid = new_session_id(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{4}-[0-9a-f]{4}", sid)


def test_new_session_id_unique_vs_existing(tmp_path):
    sid1 = save_session(_msgs(), root=tmp_path)
    sid2 = new_session_id(tmp_path)
    assert sid2 != sid1


def test_save_load_roundtrip(tmp_path):
    sid = save_session(
        _msgs(), root=tmp_path, model="qwen", agent_mode=True,
        safe_mode=False, permissions={"r", "w", "x", "http"},
    )
    data = load_session(sid, root=tmp_path)
    assert data.session_id == sid
    assert data.messages == _msgs()              # verbatim, incl. system + tool_calls
    assert data.model == "qwen"
    assert data.agent_mode is True
    assert data.permissions == {"r", "w", "x", "http"}


def test_resolve_exact_and_prefix(tmp_path):
    sid = save_session(_msgs(), root=tmp_path)
    assert resolve_session_id(sid, root=tmp_path) == sid
    assert resolve_session_id(sid[:4], root=tmp_path) == sid          # prefix
    assert resolve_session_id(sid.replace("-", ""), root=tmp_path) == sid  # dash-insensitive


def test_resolve_not_found(tmp_path):
    save_session(_msgs(), root=tmp_path)
    with pytest.raises(SessionNotFound):
        resolve_session_id("zzzz", root=tmp_path)


def test_resolve_ambiguous(tmp_path):
    # Two ids sharing a prefix -> ambiguous on that prefix.
    save_session(_msgs(), root=tmp_path, session_id="abcd-0001")
    save_session(_msgs(), root=tmp_path, session_id="abcd-0002")
    with pytest.raises(SessionAmbiguous):
        resolve_session_id("abcd", root=tmp_path)


def test_resave_preserves_created_at(tmp_path):
    sid = save_session(_msgs(), root=tmp_path)
    created = json.loads((sessions_dir(tmp_path) / f"{sid}.json").read_text())["created_at"]
    save_session(_msgs() + [{"role": "user", "content": "more"}],
                 root=tmp_path, session_id=sid)
    reread = json.loads((sessions_dir(tmp_path) / f"{sid}.json").read_text())
    assert reread["created_at"] == created
    assert reread["message_count"] == 5


from ayder_cli.core.session import (
    messages_to_replay_items,
    persist_and_announce,
    resume_hint,
    should_save_session,
)


def test_should_save_session():
    assert should_save_session([{"role": "system", "content": "s"}]) is False
    assert should_save_session(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
    ) is True


def test_resume_hint_mentions_id_and_command():
    text = resume_hint("a1b2-c3d4")
    assert "a1b2-c3d4" in text
    assert "ayder --resume a1b2-c3d4" in text


def test_persist_and_announce_notes_when_nothing_to_save(tmp_path):
    printed = []
    result = persist_and_announce(
        [{"role": "system", "content": "s"}], root=tmp_path, out=printed.append
    )
    assert result is None
    # No file created for an empty conversation...
    assert list((tmp_path / ".ayder" / "sessions").glob("*.json")) == []
    # ...but the exit is not silent — the user gets feedback.
    assert any("no conversation" in line.lower() for line in printed)


def test_persist_and_announce_saves_and_prints(tmp_path):
    printed = []
    result = persist_and_announce(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}],
        root=tmp_path, out=printed.append,
    )
    assert result is not None
    assert (tmp_path / ".ayder" / "sessions" / f"{result}.json").exists()
    assert any("ayder --resume" in line for line in printed)


def test_persist_and_announce_reuses_id(tmp_path):
    result = persist_and_announce(
        [{"role": "user", "content": "hi"}],
        root=tmp_path, session_id="a1b2-c3d4", out=lambda _x: None,
    )
    assert result == "a1b2-c3d4"
    assert (tmp_path / ".ayder" / "sessions" / "a1b2-c3d4.json").exists()


def test_messages_to_replay_items():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "result"},
        {"role": "user", "content": "thanks"},
    ]
    assert messages_to_replay_items(msgs) == [
        ("user", "hi"),
        ("assistant", "hello"),
        ("user", "thanks"),
    ]
