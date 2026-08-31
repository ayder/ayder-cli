"""The messaging inbox accepts authenticated peer prompts and publishes discovery files.

The socket path hash and the UTC ``procStart`` format are load-bearing: peers
locate the auth key by hashing the socket path, and compare ``procStart``
against the live process to reject a recycled pid. Both are pinned here.
"""

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from ayder_cli.services import messaging_inbox as mi


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def isolated(monkeypatch):
    """Redirect both directories away from the real ~/.claude/sessions.

    The socket directory is kept short: a Unix socket path is capped near 104
    bytes and pytest's tmp_path is long enough to blow it on macOS.
    """
    sock_dir = Path(tempfile.mkdtemp(dir="/tmp", prefix="ayd-s-"))
    sess_dir = Path(tempfile.mkdtemp(dir="/tmp", prefix="ayd-r-"))
    monkeypatch.setattr(mi, "socket_dir", lambda: sock_dir)
    monkeypatch.setattr(mi, "sessions_dir", lambda: sess_dir)
    yield sock_dir, sess_dir
    shutil.rmtree(sock_dir, ignore_errors=True)
    shutil.rmtree(sess_dir, ignore_errors=True)


async def _send(path, lines):
    reader, writer = await asyncio.open_unix_connection(path)
    for line in lines:
        writer.write((json.dumps(line) + "\n").encode())
    await writer.drain()
    writer.close()


def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


# ---------------------------------------------------------------------------
# Pinned wire/registry facts
# ---------------------------------------------------------------------------


def test_key_filename_is_sha256_of_unresolved_socket_path():
    """Verified against a live Claude Code session's key file."""
    sock = "/tmp/cc-socks/44390.sock"
    expected = hashlib.sha256(sock.encode()).hexdigest()
    assert mi.key_filename(44390, sock) == f"44390.{expected}.key"
    assert (
        mi.key_filename(44390, sock)
        == "44390.ea16a80a5fc8ae5ee03cda5589fa895da03f06aebdde51196bc57ed147f8207b.key"
    )


def test_key_filename_does_not_resolve_symlinks():
    """/tmp and /private/tmp must hash differently — peers look up the literal path."""
    a = mi.key_filename(1, "/tmp/cc-socks/1.sock")
    b = mi.key_filename(1, "/private/tmp/cc-socks/1.sock")
    assert a != b


def test_proc_start_is_utc_and_near_now():
    started = mi.proc_start(os.getpid())
    assert started, "expected a process start time for our own pid"
    parsed = time.strptime(started, "%a %b %d %H:%M:%S %Y")
    # Interpreted as UTC it must be in the past, and not by days.
    delta = time.time() - (time.mktime(parsed) - time.timezone)
    assert 0 <= delta < 86400, f"procStart {started!r} is not a plausible UTC time"


def test_proc_start_missing_pid_returns_empty():
    assert mi.proc_start(999_999_999) == ""


def test_extract_text_accepts_string_and_blocks():
    assert mi._extract_text({"content": "hello"}) == "hello"
    assert (
        mi._extract_text(
            {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
        )
        == "a\nb"
    )
    assert mi._extract_text({"content": 5}) == ""
    assert mi._extract_text(None) == ""


# ---------------------------------------------------------------------------
# Live socket behaviour
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_accepts_authenticated_prompt(isolated):
    got = []
    inbox = mi.MessagingInbox(got.append, name="t", session_id="s")
    assert await inbox.start()
    try:
        await _send(inbox.socket_path, [
            {"type": "auth", "token": inbox.token},
            _user("do the thing"),
        ])
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.02)
        assert got == ["do the thing"]
    finally:
        await inbox.stop()


@pytest.mark.anyio
async def test_rejects_bad_token(isolated):
    got = []
    inbox = mi.MessagingInbox(got.append)
    assert await inbox.start()
    try:
        await _send(inbox.socket_path, [
            {"type": "auth", "token": "wrong"},
            _user("should not run"),
        ])
        await asyncio.sleep(0.2)
        assert got == []
    finally:
        await inbox.stop()


@pytest.mark.anyio
async def test_rejects_message_before_auth(isolated):
    got = []
    inbox = mi.MessagingInbox(got.append)
    assert await inbox.start()
    try:
        await _send(inbox.socket_path, [_user("unauthenticated")])
        await asyncio.sleep(0.2)
        assert got == []
    finally:
        await inbox.stop()


@pytest.mark.anyio
async def test_survives_a_bad_peer_and_serves_the_next(isolated):
    """One malformed connection must not take the server down."""
    got = []
    inbox = mi.MessagingInbox(got.append)
    assert await inbox.start()
    try:
        reader, writer = await asyncio.open_unix_connection(inbox.socket_path)
        writer.write(b"this is not json\n")
        await writer.drain()
        writer.close()
        await asyncio.sleep(0.1)

        await _send(inbox.socket_path, [
            {"type": "auth", "token": inbox.token},
            _user("still alive"),
        ])
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.02)
        assert got == ["still alive"]
    finally:
        await inbox.stop()


@pytest.mark.anyio
async def test_publishes_then_removes_discovery_files(isolated):
    _, sess_dir = isolated
    inbox = mi.MessagingInbox(lambda _t: None, name="named", session_id="sid")
    assert await inbox.start()

    entry_path = sess_dir / f"{os.getpid()}.json"
    key_path = sess_dir / mi.key_filename(os.getpid(), inbox.socket_path)

    assert entry_path.exists()
    assert key_path.exists()
    assert oct(key_path.stat().st_mode)[-3:] == "600"

    entry = json.loads(entry_path.read_text())
    assert entry["peerProtocol"] == mi.PEER_PROTOCOL
    assert entry["messagingSocketPath"] == inbox.socket_path
    assert entry["name"] == "named"
    assert entry["status"] == "idle"
    assert json.loads(key_path.read_text())["peerToken"] == inbox.token

    inbox.set_status("busy")
    assert json.loads(entry_path.read_text())["status"] == "busy"

    await inbox.stop()
    assert not entry_path.exists()
    assert not key_path.exists()
    assert not Path(inbox.socket_path).exists()


@pytest.mark.anyio
async def test_start_failure_is_survivable(isolated, monkeypatch):
    """A session must still run when the inbox cannot bind."""
    async def boom(*a, **k):
        raise OSError("no socket for you")

    monkeypatch.setattr(asyncio, "start_unix_server", boom)
    inbox = mi.MessagingInbox(lambda _t: None)
    assert await inbox.start() is False
    assert inbox.running is False


# ---------------------------------------------------------------------------
# Cross-session envelope
# ---------------------------------------------------------------------------


def test_unwraps_the_envelope_claude_actually_sends():
    """Captured verbatim from a real Claude Code SendMessage delivery."""
    raw = (
        '<cross-session-message from="uds:/tmp/cc-socks/44390.sock" '
        'from-name="stubborn-agent" from-mode="prompting">\n'
        "NATIVE-SENDMESSAGE-TEST: delivered by Claude Code's built-in SendMessage.\n"
        "</cross-session-message>"
    )
    out = mi.unwrap_peer_envelope(raw)
    assert out.startswith("[message from peer 'stubborn-agent']")
    assert "NATIVE-SENDMESSAGE-TEST" in out
    assert "<cross-session-message" not in out
    assert "uds:/tmp" not in out


def test_plain_text_is_left_alone():
    assert mi.unwrap_peer_envelope("just a prompt") == "just a prompt"


def test_envelope_without_a_name_falls_back_to_the_address():
    raw = (
        '<cross-session-message from="uds:/tmp/cc-socks/1.sock">\n'
        "body here\n"
        "</cross-session-message>"
    )
    assert "uds:/tmp/cc-socks/1.sock" in mi.unwrap_peer_envelope(raw)


def test_empty_envelope_body_is_not_swallowed():
    raw = '<cross-session-message from-name="x">\n\n</cross-session-message>'
    assert mi.unwrap_peer_envelope(raw) == raw


def test_extract_text_unwraps_through_both_content_shapes():
    raw = '<cross-session-message from-name="peer1">\nhello\n</cross-session-message>'
    assert mi._extract_text({"content": raw}).endswith("hello")
    assert mi._extract_text(
        {"content": [{"type": "text", "text": raw}]}
    ).endswith("hello")


@pytest.mark.anyio
async def test_set_name_republishes_the_entry(isolated):
    _, sess_dir = isolated
    inbox = mi.MessagingInbox(lambda _t: None, name="before", name_source="auto")
    assert await inbox.start()
    try:
        entry_path = sess_dir / f"{os.getpid()}.json"
        assert json.loads(entry_path.read_text())["nameSource"] == "auto"

        inbox.set_name("after")
        entry = json.loads(entry_path.read_text())
        assert entry["name"] == "after"
        assert entry["nameSource"] == "user"
        assert inbox.name == "after"
    finally:
        await inbox.stop()


def test_unnamed_session_reports_no_name_source():
    inbox = mi.MessagingInbox(lambda _t: None, name="")
    assert inbox._entry()["nameSource"] == "none"
