# Webview TUI — Proof of Concept

Run the ayder Textual TUI inside a native desktop window using pywebview + xterm.js.

## Architecture

```
pywebview (native OS window)
  └─ xterm.js (terminal emulator rendered in the webview)
      └─ WebSocket (127.0.0.1, random port)
          └─ PTY (pywinpty on Windows, stdlib pty on macOS/Linux)
              └─ python -m ayder_cli (the Textual TUI, unchanged)
```

No changes to the TUI itself — it runs in a real PTY and thinks it's inside a normal terminal.

## Requirements

```bash
pip install pywebview websockets
```

Windows only (provides the PTY layer):

```bash
pip install pywinpty
```

### Platform notes

| Platform | Webview engine       | PTY backend       |
|----------|----------------------|-------------------|
| Windows  | EdgeChromium/WebView2| pywinpty (ConPTY) |
| macOS    | WKWebView            | stdlib `pty`      |
| Linux    | WebKitGTK            | stdlib `pty`      |

- **Windows 10 1809+** required for ConPTY support.
- **macOS**: No extra dependencies beyond pywebview and websockets.
- **Linux**: You may need `sudo apt install python3-gi gir1.2-webkit2-4.1` (or equivalent) for pywebview's GTK backend.

## Usage

From the project root:

```bash
python poc/webview_tui/launcher.py
```

A native window opens with the full ayder TUI running inside it.

## How it works

1. **launcher.py** finds a free port and starts a WebSocket server in a background thread.
2. The WebSocket handler spawns the TUI process inside a PTY (`pywinpty.PTY` on Windows, `pty.openpty()` on Unix).
3. **terminal.html** is rendered with the port injected, written to a temp file, and opened by pywebview.
4. xterm.js in the webview connects to the WebSocket. Keystrokes flow to the PTY; terminal output flows back to xterm.js.
5. Window resizes propagate through: `ResizeObserver` → xterm.js `FitAddon` → WebSocket → `pty.set_size()` + `SIGWINCH`.
6. When the window is closed, the daemon thread and PTY process are cleaned up automatically.

## Files

| File | Purpose |
|------|---------|
| `launcher.py` | Entry point — PTY, WebSocket bridge, pywebview window |
| `terminal.html` | xterm.js frontend with ayder's color theme |

## Troubleshooting

**Blank window / xterm.js doesn't load**
CDN scripts require internet access. Check connectivity or vendor the xterm.js files locally.

**Rendering glitches on Windows**
Ensure WebView2 Runtime is installed (ships with Windows 11; downloadable for Windows 10). If ConPTY mangles escape sequences, try setting `TEXTUAL=1` in the environment.

**Window opens but terminal is unresponsive**
Check the console for WebSocket connection errors. The WS server binds to `127.0.0.1` — firewalls or VPNs that intercept localhost traffic can cause issues.
