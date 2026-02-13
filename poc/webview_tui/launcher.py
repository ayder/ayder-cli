"""
POC: ayder TUI inside a native desktop window.

Architecture:
    pywebview (native window)
      └─ xterm.js (terminal emulator in the webview)
          └─ WebSocket
              └─ PTY  (pywinpty on Windows, pty on macOS/Linux)
                  └─ python -m ayder_cli  (the Textual TUI)

Requirements:
    pip install pywebview websockets

    # Windows only (provides the PTY layer):
    pip install pywinpty

Usage:
    python poc/webview_tui/launcher.py
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import signal
import socket
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

SYSTEM = platform.system()


# ── helpers ──────────────────────────────────────────────────────────

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── cross-platform PTY ──────────────────────────────────────────────

class _Pty:
    """Thin wrapper: pywinpty on Windows, stdlib pty on Unix."""

    def __init__(self, cmd: list[str], cols: int = 120, rows: int = 40):
        self._cmd = cmd
        self._cols = cols
        self._rows = rows
        self._closed = False

    # -- lifecycle ---------------------------------------------------

    def spawn(self) -> None:
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"

        if SYSTEM == "Windows":
            self._spawn_win(env)
        else:
            self._spawn_unix(env)

    def _spawn_win(self, env: dict) -> None:
        from winpty import PTY  # pywinpty >= 2.0

        self._pty = PTY(self._cols, self._rows)
        # PTY.spawn wants (appname, cmdline, cwd, env)
        # cmdline is everything *after* the executable
        cmdline = " ".join(self._cmd[1:]) if len(self._cmd) > 1 else None
        self._pty.spawn(self._cmd[0], cmdline=cmdline, cwd=os.getcwd())

    def _spawn_unix(self, env: dict) -> None:
        import pty as _pty_mod
        import fcntl
        import termios
        import subprocess

        master, slave = _pty_mod.openpty()
        ws = struct.pack("HHHH", self._rows, self._cols, 0, 0)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, ws)

        self._proc = subprocess.Popen(
            self._cmd,
            stdin=slave, stdout=slave, stderr=slave,
            env=env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(slave)
        self._fd = master

    # -- I/O ---------------------------------------------------------

    def read(self) -> bytes:
        """Blocking read with ~50 ms timeout (safe for executor threads)."""
        if self._closed:
            return b""

        if SYSTEM == "Windows":
            data = self._pty.read(4096, blocking=False)
            if not data:
                time.sleep(0.05)
            return data or b""

        import select
        r, _, _ = select.select([self._fd], [], [], 0.05)
        if r:
            try:
                return os.read(self._fd, 16384)
            except OSError:
                self._closed = True
                return b""
        return b""

    def write(self, data: bytes) -> None:
        if self._closed:
            return
        if SYSTEM == "Windows":
            self._pty.write(data)
        else:
            os.write(self._fd, data)

    # -- resize / status --------------------------------------------

    def resize(self, cols: int, rows: int) -> None:
        self._cols, self._rows = cols, rows
        if SYSTEM == "Windows":
            self._pty.set_size(cols, rows)
        else:
            import fcntl
            import termios
            ws = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, ws)
            # Notify the process group so Textual redraws
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGWINCH)
            except (ProcessLookupError, OSError):
                pass

    def is_alive(self) -> bool:
        if self._closed:
            return False
        if SYSTEM == "Windows":
            alive = self._pty.isalive()
        else:
            alive = self._proc.poll() is None
        if not alive:
            self._closed = True
        return alive

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if SYSTEM == "Windows":
            try:
                self._pty.close()
            except Exception:
                pass
        else:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass


# ── WebSocket ↔ PTY bridge ──────────────────────────────────────────

def _run_ws_bridge(
    port: int,
    tui_cmd: list[str],
    ready: threading.Event,
) -> None:
    """Start a WebSocket server that bridges xterm.js ↔ PTY.

    Runs in its own thread with a dedicated event loop.
    """
    import websockets

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def handler(websocket, *_args):
        """One PTY per WebSocket connection."""
        pty = _Pty(tui_cmd)
        pty.spawn()

        async def pty_to_ws():
            while pty.is_alive():
                data = await loop.run_in_executor(None, pty.read)
                if data:
                    try:
                        await websocket.send(data.decode("utf-8", errors="replace"))
                    except Exception:
                        break
                else:
                    await asyncio.sleep(0.02)

        async def ws_to_pty():
            try:
                async for msg in websocket:
                    if isinstance(msg, str) and msg.startswith("\x00"):
                        ctrl = json.loads(msg[1:])
                        if ctrl.get("type") == "resize":
                            pty.resize(ctrl["cols"], ctrl["rows"])
                    else:
                        raw = msg.encode("utf-8") if isinstance(msg, str) else msg
                        pty.write(raw)
            except Exception:
                pass

        try:
            reader = asyncio.ensure_future(pty_to_ws())
            writer = asyncio.ensure_future(ws_to_pty())
            done, pending = await asyncio.wait(
                [reader, writer], return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
        finally:
            pty.close()

    async def serve():
        async with websockets.serve(handler, "127.0.0.1", port):
            ready.set()
            await asyncio.Future()  # run forever

    loop.run_until_complete(serve())


# ── entry point ──────────────────────────────────────────────────────

def main() -> None:
    try:
        import webview
    except ImportError:
        print("Missing dependency: pip install pywebview", file=sys.stderr)
        sys.exit(1)

    try:
        import websockets  # noqa: F401
    except ImportError:
        print("Missing dependency: pip install websockets", file=sys.stderr)
        sys.exit(1)

    if SYSTEM == "Windows":
        try:
            from winpty import PTY  # noqa: F401
        except ImportError:
            print("Missing dependency: pip install pywinpty", file=sys.stderr)
            sys.exit(1)

    ws_port = _find_free_port()

    # Render HTML template with the WebSocket port injected
    template_path = Path(__file__).parent / "terminal.html"
    html = template_path.read_text(encoding="utf-8")
    html = html.replace("{{WS_PORT}}", str(ws_port))

    # Write to a temp file (more reliable than pywebview html= parameter
    # across platforms — avoids CSP issues with CDN script loading)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8",
    )
    tmp.write(html)
    tmp.close()
    tmp_path = tmp.name

    # Command to launch the TUI
    tui_cmd = [sys.executable, "-m", "ayder_cli"]

    # Start WS bridge in a background thread
    server_ready = threading.Event()
    ws_thread = threading.Thread(
        target=_run_ws_bridge,
        args=(ws_port, tui_cmd, server_ready),
        daemon=True,
    )
    ws_thread.start()

    if not server_ready.wait(timeout=5):
        print("WebSocket server failed to start", file=sys.stderr)
        sys.exit(1)

    # Open native window (blocks until closed)
    window = webview.create_window(
        "ayder",
        url=Path(tmp_path).as_uri(),
        width=1100,
        height=750,
        min_size=(600, 400),
    )
    webview.start()

    # Cleanup temp file
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
