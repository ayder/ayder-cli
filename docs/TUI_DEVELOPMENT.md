# TUI Development Notes (Textual)

ayder-cli's TUI is built with [Textual](https://github.com/Textualize/textual). This document captures practical findings, gotchas, and patterns discovered during development.

## Mouse Support

### Disabling Mouse Capture

Textual enables terminal mouse tracking by default. This means the terminal captures all mouse events (clicks, scrolls, selections) and forwards them to Textual widgets instead of letting the terminal handle them natively.

To disable mouse capture and restore native terminal mouse behavior (text selection, copy/paste, right-click menus, scroll wheel):

```python
# Correct - pass mouse=False to run()
app.run(mouse=False)
```

**There is no class-level setting for this.** The following does NOT work:

```python
class MyApp(App):
    # WRONG - Textual has no such class variable, this is silently ignored
    ENABLE_MOUSE_SUPPORT = False
```

`ENABLE_MOUSE_SUPPORT` is a `prompt_toolkit` concept, not a Textual one. Textual ignores any unrecognized class variables without error.

### How It Works Internally

The `mouse` parameter flows through:

1. `App.run(mouse=False)` -> `App.run_async(mouse=False)`
2. -> `App._process_messages(mouse=False)`
3. -> `Driver.__init__(app, mouse=False)` -> stored as `self._mouse`
4. -> `Driver._enable_mouse_support()` checks `self._mouse` and returns early if `False`

When `mouse=True` (the default), the driver writes these escape sequences to enable mouse tracking:

```
\x1b[?1000h  # SET_VT200_MOUSE
\x1b[?1003h  # SET_ANY_EVENT_MOUSE
\x1b[?1015h  # SET_VT200_HIGHLIGHT_MOUSE
\x1b[?1006h  # SET_SGR_EXT_MODE_MOUSE
```

When `mouse=False`, none of these are written and the terminal retains native mouse behavior.

### Consequences of Disabling Mouse

With `mouse=False`:
- Native terminal text selection works
- Native copy/paste works (Cmd+C on macOS, Ctrl+Shift+C on Linux)
- Terminal scroll wheel works natively
- `Button` widgets cannot be clicked (use keyboard shortcuts instead)
- Textual's built-in text selection (`screen.get_selected_text()`) is unavailable
- All modal screens must have keyboard navigation (already the case in ayder-cli)

### Known Issues

- **Textual v0.55.0** had a bug where `mouse=False` caused escape sequence leaks on exit, resulting in `UnicodeDecodeError` on mouse movement after the app closed ([#4376](https://github.com/Textualize/textual/issues/4376)). Fixed in [#4379](https://github.com/Textualize/textual/pull/4379). Not an issue on Textual 7.x+.

## Inline Mode

### Overview

By default, Textual apps run in **application mode** — they switch to the terminal's alternate screen buffer, blanking the terminal on start and restoring it on exit. All TUI content is lost when the app closes.

**Inline mode** renders the app within the normal terminal flow instead. Content stays visible in the terminal's scrollback after exit.

```python
# ayder-cli uses inline mode with no-clear and no mouse
app.run(inline=True, inline_no_clear=True, mouse=False)
```

| Parameter | Effect |
|---|---|
| `inline=True` | Renders below current prompt, no alternate screen buffer |
| `inline_no_clear=True` | Final frame persists in terminal after exit |
| `mouse=False` | Native terminal mouse (independent of inline) |

### Height Control

In inline mode, the app height is not full-screen. Control it with the `:inline` CSS pseudo-class:

```css
Screen:inline {
    height: 80vh;     /* 80% of terminal height */
    min-height: 20;   /* At least 20 rows */
}
```

The height is always capped at the terminal height. Do **not** use the `size=` parameter on `run()` for this — it doesn't affect inline height (it's for headless/testing).

### How It Works Internally

With `inline=True`, Textual uses `LinuxInlineDriver` instead of the fullscreen `LinuxDriver`:

1. **Writes to stderr** (not stdout), so it doesn't interfere with piped output
2. **Does NOT enter alternate screen buffer** — renders in the main terminal buffer
3. **Uses relative cursor movement** — each frame, the cursor moves back to the app's origin and rewrites content
4. **No synchronized output** — inline mode doesn't use sync escape sequences, which can cause minor flickering on rapid updates

### Limitations

- **Not supported on Windows** — silently falls back to fullscreen mode
- **Height cannot exceed terminal height** — `min(app_height, terminal_height)`
- **No synchronized output** — minor flickering possible on fast updates
- **Modal screens are constrained** to the inline height (modals and `push_screen` still work, just within the allocated space)
- **stderr is used for output** — stderr redirection will break the display

### Known Issues

- **Command palette flickering** ([#4385](https://github.com/Textualize/textual/issues/4385)) — fixed in Textual 0.56.0
- **Interactive widget lag** ([#4403](https://github.com/Textualize/textual/issues/4403)) — fixed in Textual 0.56.3
- **Dynamic height changes** can cause brief visual artifacts when the inline area shrinks between frames
- `stop_application_mode()` uses `\x1b[J` (erase to end of screen), which clears content below the app on exit

## Command Palette

Textual ships with a built-in command palette (Ctrl+P). Disable it if you don't use it:

```python
class MyApp(App):
    ENABLE_COMMAND_PALETTE = False
```

Unlike `ENABLE_MOUSE_SUPPORT`, this IS a real Textual class variable.

## Spinner Animation

Textual's `Static` widget doesn't auto-animate Rich `Spinner` objects. You must manually re-render them on a timer:

```python
from rich.spinner import Spinner
from textual.widgets import Static

spinner = Spinner("dots2", text="Thinking...", style="bold yellow")
widget = Static(spinner)

# Must call widget.update(spinner) periodically to animate
self._timer = self.set_interval(0.1, lambda: widget.update(spinner))
```

The spinner internally advances its frame based on elapsed time, but `Static` only renders once unless explicitly updated.

## Modal Screens

Modal screens (`ModalScreen`) overlay the entire app. Key patterns:

```python
class MyModal(ModalScreen[bool]):
    """Generic type determines dismiss() return type."""

    def on_key(self, event) -> None:
        """Always provide keyboard shortcuts - mouse may be disabled."""
        if event.key in ("escape", "n"):
            self.dismiss(False)
        elif event.key in ("enter", "y"):
            self.dismiss(True)
```

Push with a callback:

```python
def on_result(result: bool) -> None:
    if result:
        # confirmed
        pass

self.push_screen(MyModal(), on_result)
```

## Workers and Async

Textual workers run tasks off the main thread. For async LLM calls:

```python
# Launch a worker
self.run_worker(self._process_llm_response(), exclusive=True)

# Inside the worker, check cancellation
from textual.worker import get_current_worker

async def _process_llm_response(self):
    worker = get_current_worker()
    result = await some_async_call()
    if worker.is_cancelled:
        return
    # ... process result

# Schedule UI updates from worker context
self.call_later(self._update_ui)
```

`exclusive=True` cancels any previously running worker of the same type before starting a new one.

## CSS Patterns

### Hiding Scrollbars

```css
#my-widget {
    scrollbar-size: 0 0;
    scrollbar-size-horizontal: 0;
    scrollbar-size-vertical: 0;
}
```

### Conditionally Visible Widgets

Toggle visibility with `display` property in Python:

```python
def on_mount(self) -> None:
    self.display = False  # Hidden initially

def show(self) -> None:
    self.display = True
```

Or use CSS `display: none;` as the default, then toggle in code.

### Auto-Height Containers

```css
MyWidget {
    height: auto;      /* Shrink to fit content */
    max-height: 20%;   /* But cap at 20% of screen */
}
```

## Input with Suggestions

Textual's `SuggestFromList` works with the `Input` widget but only provides type-ahead suggestions, not a dropdown. Key behaviors:

- Suggestions are matched case-insensitively by default
- Tab key can accept the current suggestion (requires custom `on_key` handler)
- The suggestion popup is accessible via `getattr(self, "_suggestion_popup", None)` (internal API, may change)

## Valid App Class Variables

For reference, these are real Textual `App` class variables (non-exhaustive):

| Variable | Type | Default | Description |
|---|---|---|---|
| `CSS` | `str` | `""` | App-level CSS |
| `CSS_PATH` | `str \| None` | `None` | Path to CSS file |
| `BINDINGS` | `list` | `[]` | Key bindings |
| `TITLE` | `str` | `""` | App title |
| `SUB_TITLE` | `str` | `""` | App subtitle |
| `ENABLE_COMMAND_PALETTE` | `bool` | `True` | Enable Ctrl+P palette |
| `SCREENS` | `dict` | `{}` | Named screen registry |
| `AUTO_FOCUS` | `str \| None` | `"*"` | CSS selector for auto-focus |
| `INLINE_PADDING` | `int` | `1` | Blank lines above inline app |

Note: `ENABLE_MOUSE_SUPPORT` is **not** in this list. Mouse is controlled via `app.run(mouse=...)`.

## `app.run()` Parameters Reference

```python
app.run(
    headless=False,          # Run without a terminal (for testing)
    inline=False,            # Inline mode (no alternate screen)
    inline_no_clear=False,   # Keep content after exit (inline only)
    mouse=True,              # Enable terminal mouse capture
    size=None,               # Override terminal size (headless/testing only)
)
```
