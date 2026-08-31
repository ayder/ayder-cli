"""Messaging inbox — accept prompts from peer processes over a Unix socket.

An ayder session advertises itself the same way a Claude Code session does, so
existing peers discover and message it with no client changes:

    /tmp/cc-socks/<pid>.sock                     the inbox
    ~/.claude/sessions/<pid>.json                discovery entry
    ~/.claude/sessions/<pid>.<sha256>.key        {"peerToken": ...}, mode 0600

The key filename's hash is ``sha256`` of the *unresolved* socket path (verified
against a live Claude Code session: sha256("/tmp/cc-socks/44390.sock") is that
session's key filename). ``procStart`` is the OS process start time rendered as
a UTC ctime string; peers compare it against the live value to prove a pid has
not been recycled, so it must be derived from the OS rather than from our own
clock.

Wire protocol — newline-delimited JSON, auth line first::

    {"type":"auth","token":"<peerToken>"}
    {"type":"user","message":{"role":"user","content":"<prompt>"}}

The inbox never writes a reply; a sender cannot distinguish a bad token from a
delivered message. Accepted prompts are handed to ``on_message`` which enqueues
them as an ordinary user turn.

This writes into a directory owned by another tool. ``PEER_PROTOCOL`` is
asserted on read and the layout may change on a Claude Code upgrade.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ayder_cli.log import get_logger

logger = get_logger("core")

# Bump only after re-verifying the wire format and registry layout.
PEER_PROTOCOL = 1

# Cap a single line so a hostile or broken peer cannot exhaust memory.
MAX_LINE_BYTES = 1_048_576

_DIR_MODE = 0o700
_KEY_MODE = 0o600


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def sessions_dir() -> Path:
    """Directory holding peer discovery entries and auth keys."""
    return Path.home() / ".claude" / "sessions"


def socket_dir() -> Path:
    """Directory holding peer sockets.

    Prefers the shared ``cc-socks`` directory. If something else already owns
    it with different ownership, fall back to a per-uid directory rather than
    fighting over it — the same fallback Claude Code applies.
    """
    if sys.platform.startswith("linux"):
        run_user = Path(f"/run/user/{os.getuid()}")
        if run_user.is_dir():
            return run_user / "cc-socks"

    shared = Path("/tmp/cc-socks")
    try:
        if shared.exists() and shared.stat().st_uid != os.getuid():
            return Path(f"/tmp/cc-socks-{os.getuid()}")
    except OSError:
        return Path(f"/tmp/cc-socks-{os.getuid()}")
    return shared


def key_filename(pid: int, sock_path: str) -> str:
    """Return ``<pid>.<sha256(socket path)>.key``.

    The path is hashed exactly as given — NOT symlink-resolved. On macOS
    ``/tmp`` is a symlink to ``/private/tmp`` and resolving it produces a
    different digest that peers will not find.
    """
    digest = hashlib.sha256(sock_path.encode("utf-8")).hexdigest()
    return f"{pid}.{digest}.key"


def proc_start(pid: int) -> str:
    """Return a process's start time as a UTC ctime string.

    ``ps`` reports local time; the registry stores UTC, so the value is parsed
    as local and re-rendered from ``gmtime``. Returns "" when the start time
    cannot be determined — callers publish without the guard rather than fail.
    """
    try:
        out = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if not out:
            return ""
        return time.asctime(time.gmtime(time.mktime(time.strptime(out, "%a %b %d %H:%M:%S %Y"))))
    except (OSError, ValueError, subprocess.SubprocessError):
        logger.debug("Could not determine process start time for pid {}", pid)
        return ""


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


class MessagingInbox:
    """A Unix-socket inbox that turns peer messages into user turns."""

    def __init__(
        self,
        on_message: Callable[[str], None],
        *,
        session_id: str = "",
        name: str = "",
        name_source: str = "auto",
        cwd: Optional[Path] = None,
        version: str = "",
    ) -> None:
        self._on_message = on_message
        self._session_id = session_id
        self._name = name
        self._name_source = name_source
        self._cwd = str(cwd or Path.cwd())
        self._version = version

        self._pid = os.getpid()
        self._sock_path = str(socket_dir() / f"{self._pid}.sock")
        self._token = secrets.token_hex(16)
        self._started_at = int(time.time() * 1000)
        self._proc_start = proc_start(self._pid)
        self._status = "idle"

        self._server: Optional[asyncio.AbstractServer] = None

    # -- lifecycle --------------------------------------------------------

    @property
    def socket_path(self) -> str:
        return self._sock_path

    @property
    def token(self) -> str:
        return self._token

    @property
    def running(self) -> bool:
        return self._server is not None

    async def start(self) -> bool:
        """Bind the socket and publish discovery files.

        Returns True when the inbox is live. A failure is logged and swallowed:
        an unreachable inbox must never stop the session from running.
        """
        try:
            sock_dir = socket_dir()
            sock_dir.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)

            # Our path is pid-derived, so anything already there is a leftover
            # from a dead process that reused this pid.
            try:
                os.unlink(self._sock_path)
            except FileNotFoundError:
                pass

            self._server = await asyncio.start_unix_server(
                self._handle_client, path=self._sock_path
            )
            os.chmod(self._sock_path, _KEY_MODE)

            self._publish()
            logger.info("Messaging inbox listening at {}", self._sock_path)
            return True
        except Exception:  # noqa: BLE001 - inbox startup must never break the session
            logger.opt(exception=True).warning(
                "Could not start the messaging inbox; the session runs without one"
            )
            await self.stop()
            return False

    async def stop(self) -> None:
        """Close the socket and remove every file this inbox published."""
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except OSError:
                logger.debug("Inbox server close failed")
            self._server = None

        for path in (
            Path(self._sock_path),
            sessions_dir() / f"{self._pid}.json",
            sessions_dir() / key_filename(self._pid, self._sock_path),
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                logger.debug("Could not remove {}", path)

    # -- discovery --------------------------------------------------------

    def _entry(self) -> dict[str, Any]:
        now = int(time.time() * 1000)
        return {
            "pid": self._pid,
            "sessionId": self._session_id,
            "cwd": self._cwd,
            "startedAt": self._started_at,
            "procStart": self._proc_start,
            "version": self._version,
            "peerProtocol": PEER_PROTOCOL,
            # Advertise nothing we do not implement.
            "peerFeatures": [],
            "kind": "interactive",
            "entrypoint": "ayder",
            "pidDomain": sys.platform,
            "messagingSocketPath": self._sock_path,
            "name": self._name,
            "nameSource": self._name_source if self._name else "none",
            "status": self._status,
            "updatedAt": now,
            "statusUpdatedAt": now,
        }

    def _publish(self) -> None:
        sess_dir = sessions_dir()
        sess_dir.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)

        key_path = sess_dir / key_filename(self._pid, self._sock_path)
        key_payload = {
            "peerToken": self._token,
            "procStart": self._proc_start,
            "pidDomain": sys.platform,
        }
        # Create with 0600 from the start — never briefly world-readable.
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _KEY_MODE)
        with os.fdopen(fd, "w") as fh:
            json.dump(key_payload, fh)

        self._write_entry()

    def _write_entry(self) -> None:
        """Write the discovery entry atomically so readers never see a partial file."""
        sess_dir = sessions_dir()
        target = sess_dir / f"{self._pid}.json"
        tmp = sess_dir / f"{self._pid}.json.{os.getpid()}.tmp"
        try:
            tmp.write_text(json.dumps(self._entry()))
            os.replace(tmp, target)
        except OSError:
            logger.debug("Could not write the discovery entry")
            try:
                tmp.unlink()
            except OSError:
                pass

    @property
    def name(self) -> str:
        return self._name

    def set_name(self, name: str, source: str = "user") -> None:
        """Rename this session and republish so peers see the new handle."""
        self._name = name
        self._name_source = source
        if self.running:
            self._write_entry()

    def set_status(self, status: str) -> None:
        """Publish ``busy`` or ``idle`` so peers can see whether work is in flight."""
        if status == self._status or not self.running:
            return
        self._status = status
        self._write_entry()

    # -- connection handling ----------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Read newline-delimited JSON from one peer connection.

        The first meaningful line must authenticate. Anything unparseable or
        unauthenticated drops the connection without a reply.
        """
        authenticated = False
        try:
            while True:
                try:
                    raw = await reader.readline()
                except (asyncio.LimitOverrunError, ValueError):
                    logger.warning("Inbox: oversized line, dropping connection")
                    return
                if not raw:
                    return
                if len(raw) > MAX_LINE_BYTES:
                    logger.warning("Inbox: line over cap, dropping connection")
                    return

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    if not authenticated:
                        return
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Inbox: unparseable line, dropping connection")
                    return
                if not isinstance(payload, dict):
                    return

                kind = payload.get("type")

                if not authenticated:
                    if kind != "auth" or not self._check_token(payload.get("token")):
                        logger.warning("Inbox: authentication failed, dropping connection")
                        return
                    authenticated = True
                    continue

                if kind == "user":
                    text = _extract_text(payload.get("message"))
                    if text:
                        logger.info("Inbox: accepted a {}-char prompt", len(text))
                        self._on_message(text)
                    else:
                        logger.warning("Inbox: user message carried no text")
        except (ConnectionResetError, BrokenPipeError):
            return
        except Exception:  # noqa: BLE001 - one bad peer must not kill the server
            logger.opt(exception=True).warning("Inbox: connection handler failed")
        finally:
            try:
                writer.close()
            except OSError:
                pass

    def _check_token(self, supplied: Any) -> bool:
        if not isinstance(supplied, str) or not supplied:
            return False
        return secrets.compare_digest(supplied, self._token)


# Claude Code's SendMessage wraps its payload in an envelope. Passing the raw
# XML into a turn would feed the model markup instead of a prompt.
_ENVELOPE = re.compile(
    r"^<cross-session-message(?P<attrs>[^>]*)>\n(?P<body>.*)\n</cross-session-message>$",
    re.DOTALL,
)
_ATTR = re.compile(r'([a-z-]+)="([^"]*)"')


def unwrap_peer_envelope(text: str) -> str:
    """Flatten a cross-session envelope into an attributed prompt.

    Text that is not an envelope is returned unchanged, so a plain sender is
    unaffected.
    """
    match = _ENVELOPE.match(text.strip())
    if match is None:
        return text
    body = match.group("body").strip()
    if not body:
        return text
    attrs = dict(_ATTR.findall(match.group("attrs")))
    sender = attrs.get("from-name") or attrs.get("from") or "peer"
    return f"[message from peer '{sender}']\n\n{body}"


def _extract_text(message: Any) -> str:
    """Pull prompt text out of a peer message.

    ``content`` is normally a string; a block list is accepted so a peer that
    sends structured content is not silently dropped.
    """
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return unwrap_peer_envelope(content.strip())
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return unwrap_peer_envelope("\n".join(p for p in parts if p).strip())
    return ""
