"""
Ayder themes for ayder-cli TUI.

A "linux console" LAYOUT that, by default, respects the user's own terminal, but
can be overlaid on ANY Textual palette (``ayder-monokai``, ``ayder-dracula`` …).

Two axes:

  * **Layout** — this CSS (``AYDER_CSS``). It styles ayder's chrome (chat, input
    bar, status bar, panels, banner) using Textual *design tokens* (``$background``,
    ``$foreground``, ``$primary``, ``$accent``, ``$success`` …) so the colours
    come from whichever palette is active.
  * **Palette** — a Textual ``App.theme``. The default is the ANSI passthrough
    pair below (``ayder-dark``/``ayder-light``), where every surface token is
    ``ansi_default`` so the terminal paints its own background — no solid fills.
    Pick any RGB Textual theme instead (monokai, dracula, nord …) via
    ``[ui] palette`` and the same layout adopts that palette's colours.

Because the chrome is tokenised, switching palette is all it takes:

  * ``ansi-dark`` / ``ansi-light`` (default) → terminal passthrough, the user's
    own background and palette are honoured on every terminal.
  * ``monokai`` / ``dracula`` / … → a fixed RGB look. NOTE: these paint their
    own background and therefore do NOT respect the terminal background — that
    is a deliberate, opt-in trade-off, distinct from the ansi default.

Floating overlays (modals, the autocomplete dropdown) keep an opaque
``ansi_black`` box so they stay readable over content under every palette;
``$surface``/``$panel`` are transparent under the ansi palette, so they cannot
be used there.

Three CSS themes are registered (all share this layout):

  * ``ayder-dark``  — layout + default palette ``ayder-dark`` (ansi, dark)
  * ``ayder-light`` — layout + default palette ``ayder-light`` (ansi, light)
  * ``ayder``       — alias for ``ayder-dark``

``[ui] palette`` overrides the default palette without changing the layout.
"""

from textual.theme import Theme as TextualTheme

from . import Theme, register_theme

AYDER_CSS = """\
/* ── Design tokens (resolved from the active palette / App.theme) ─────────
   $background  -> terminal bg (ansi palette) or the palette's RGB background
   $foreground  -> terminal fg (ansi palette) or the palette's RGB foreground
   $primary     -> separator/prompt accent  (#5eaff5 under the ansi palette)
   $accent      -> user/banner heading accent
   $success     -> tool-result / completed   ($warning -> running / activity)
   $error       -> agent error               ($text-muted -> dim chrome text)
   Overlays (modals, dropdown) deliberately keep an opaque ANSI box
   (ansi_black/ansi_white/…) because $surface/$panel are transparent under the
   ansi palette. Only the always-visible chrome is tokenised.
   ───────────────────────────────────────────────────────────────────────── */

/* CLIConfirmScreen - The modal dialog that appears when a tool needs user approval.
   Targets the 'CLIConfirmScreen' class in screens.py. */
CLIConfirmScreen {
    align: center bottom;
}

/* The main container within the confirmation screen. */
CLIConfirmScreen > Vertical {
    width: 100%;
    height: auto;
    background: ansi_black;
    border-top: solid ansi_bright_black;
    padding: 1 2;
}

/* The question/prompt text in the confirmation dialog ("Allow tool execution?"). */
CLIConfirmScreen .prompt {
    text-style: bold;
    color: ansi_bright_blue;
}

/* The description of the tool action ("Run command: ls -la"). */
CLIConfirmScreen .description {
    color: ansi_white;
    margin-bottom: 1;
}

/* The scrollable container showing the code diff for file modifications. */
CLIConfirmScreen .diff-container {
    height: 15;
    border: solid ansi_bright_black;
    margin: 1 0;
    padding: 1;
    background: ansi_black;
}

CLIConfirmScreen #diff-content {
    width: auto;
    height: auto;
}

/* The list of options (Approve, Deny, etc.) in the confirmation dialog. */
CLIConfirmScreen .option-list {
    height: auto;
    max-height: 10;
    overflow-y: auto;
    margin: 1 0;
    padding: 0 1;
}

/* The input field for providing custom instructions when denying a tool. */
CLIConfirmScreen #instruction-input {
    display: none;
    margin: 1 0;
    border: solid ansi_bright_black;
    background: ansi_black;
    color: ansi_white;
}

/* Hint text at the bottom of the confirmation screen. */
CLIConfirmScreen .hint {
    color: ansi_bright_black;
    text-style: dim;
    margin-top: 1;
}

/* CLIPermissionScreen - The modal for changing tool permissions (/permission command).
   Targets 'CLIPermissionScreen' in screens.py. */
CLIPermissionScreen {
    align: center bottom;
}

CLIPermissionScreen > Vertical {
    width: 100%;
    height: auto;
    background: ansi_black;
    border-top: solid ansi_bright_black;
    padding: 1 2;
}

CLIPermissionScreen .prompt {
    text-style: bold;
    color: ansi_bright_blue;
}

CLIPermissionScreen .description {
    color: ansi_white;
    margin-bottom: 1;
}

CLIPermissionScreen .option-list {
    height: auto;
    max-height: 10;
    overflow-y: auto;
    margin: 1 0;
    padding: 0 1;
}

CLIPermissionScreen .hint {
    color: ansi_bright_black;
    text-style: dim;
    margin-top: 1;
}

/* CLISafeModeScreen - The modal warning when a tool is blocked by safe mode.
   Targets 'CLISafeModeScreen' in screens.py. */
CLISafeModeScreen {
    align: center bottom;
}

CLISafeModeScreen > Vertical {
    width: 100%;
    height: auto;
    background: ansi_black;
    border-top: solid ansi_red;
    padding: 1 2;
}

CLISafeModeScreen .title {
    text-style: bold;
    color: ansi_red;
}

/* CLISelectScreen - A generic selection modal (used for picking tasks, etc.).
   Targets 'CLISelectScreen' in screens.py. */
CLISelectScreen {
    align: center bottom;
}

CLISelectScreen > Vertical {
    width: 100%;
    max-height: 60%;
    height: auto;
    background: ansi_black;
    border-top: solid ansi_bright_black;
    padding: 1 2;
}

CLISelectScreen .prompt {
    text-style: bold;
    color: ansi_bright_blue;
    margin-bottom: 1;
}

CLISelectScreen .description {
    color: ansi_bright_black;
    margin-bottom: 1;
}

CLISelectScreen .select-list {
    height: auto;
    max-height: 20;
    overflow-y: auto;
    margin: 1 0;
    padding: 0 1;
}

CLISelectScreen .hint {
    color: ansi_bright_black;
    text-style: dim;
    margin-top: 1;
}

/* CLIMultiSelectScreen - A multi-selection modal (used for /plugin command, etc.).
   Targets 'CLIMultiSelectScreen' in screens.py. */
CLIMultiSelectScreen {
    align: center bottom;
}

CLIMultiSelectScreen > Vertical {
    width: 100%;
    max-height: 60%;
    height: auto;
    background: ansi_black;
    border-top: solid ansi_bright_black;
    padding: 1 2;
}

CLIMultiSelectScreen .prompt {
    text-style: bold;
    color: ansi_bright_blue;
    margin-bottom: 1;
}

CLIMultiSelectScreen .description {
    color: ansi_bright_black;
    margin-bottom: 1;
}

CLIMultiSelectScreen .select-list {
    height: auto;
    max-height: 20;
    overflow-y: auto;
    margin: 1 0;
    padding: 0 1;
}

CLIMultiSelectScreen .hint {
    color: ansi_bright_black;
    text-style: dim;
    margin-top: 1;
}

/* AgentListScreen - The /agent popup that lists configured agents and their live status.
   Targets 'AgentListScreen' in screens.py. */
AgentListScreen {
    align: center bottom;
}

AgentListScreen > Vertical {
    width: 100%;
    max-height: 60%;
    height: auto;
    background: ansi_black;
    border-top: solid ansi_bright_black;
    padding: 1 2;
}

AgentListScreen .prompt {
    text-style: bold;
    color: ansi_bright_blue;
    margin-bottom: 1;
}

AgentListScreen .description {
    color: ansi_bright_black;
    margin-bottom: 1;
}

AgentListScreen .select-list {
    height: auto;
    max-height: 20;
    overflow-y: auto;
    margin: 1 0;
    padding: 0 1;
}

AgentListScreen .hint {
    color: ansi_bright_black;
    text-style: dim;
    margin-top: 1;
}

/* TaskEditScreen - The full-screen(ish) editor for editing task descriptions.
   Targets 'TaskEditScreen' in screens.py. */
TaskEditScreen {
    align: center bottom;
}

TaskEditScreen > Vertical {
    width: 100%;
    height: 80%;
    background: ansi_black;
    border-top: solid ansi_bright_black;
    padding: 1 2;
}

TaskEditScreen .prompt {
    height: 1;
    text-style: bold;
    color: ansi_bright_blue;
    margin-bottom: 1;
}

TaskEditScreen #task-editor {
    height: 1fr;
}

TaskEditScreen .hint {
    height: 1;
    color: ansi_bright_black;
    text-style: dim;
    margin-top: 1;
}

/* CLIHelpScreen - Centered help modal showing keybindings.
   Targets 'CLIHelpScreen' in screens.py. */
CLIHelpScreen {
    align: center middle;
}

CLIHelpScreen > Vertical {
    width: 50;
    height: auto;
    max-height: 80%;
    background: ansi_black;
    border: solid ansi_bright_blue;
    padding: 1 2;
}

CLIHelpScreen .prompt {
    text-style: bold;
    color: ansi_bright_blue;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

CLIHelpScreen #help-content {
    color: ansi_white;
    height: auto;
}

/* Generic text selection highlight color. */
.selection {
    background: ansi_blue;
    color: ansi_white;
}

/* ChatView - The main scrollable area displaying the chat history.
   Targets 'ChatView' widget in widgets.py. */
ChatView {
    height: 100%;
    padding: 0 1;
    background: $background;
}

/* Base style for all message lines within ChatView. */
ChatView Static {
    height: auto;
    margin: 0;
    padding: 0;
    background: $background;
}

/* User message text ("> Hello"). */
ChatView .user-message {
    color: $accent;
    margin: 1 0 0 0;
}

/* Assistant message prefix ("<"). */
ChatView .assistant-message {
    color: $foreground;
    margin: 1 0 0 0;
}

/* The actual Markdown content of the assistant's reply. */
ChatView .assistant-message-content {
    margin: 0 0 0 2;
    color: $foreground;
}

/* Styling for the <think> blocks (reasoning text). */
ChatView .thinking {
    color: $text-muted;
    margin: 0;
    padding-left: 2;
    text-style: italic;
}

/* Tool call display ("→ write_file ..."). */
ChatView .tool-call {
    color: $warning;
    margin: 0;
    padding-left: 2;
}

/* Tool result display ("✓ File written"). */
ChatView .tool-result {
    color: $success;
    margin: 0;
    padding-left: 2;
}

/* System messages ("Operation cancelled", "Error: ..."). */
ChatView .system-message {
    color: $text-muted;
    margin: 1 0 0 0;
    text-style: italic;
}

/* Separator lines (if used). */
ChatView .separator {
    color: $text-muted;
    margin: 1 0 0 0;
}

/* The "Thinking..." spinner message. */
ChatView .thinking-message {
    color: $warning;
    margin: 1 0 0 0;
}

ChatView .tool-running {
    color: $warning;
    margin: 0;
    padding-left: 2;
}

ChatView .tool-completed {
    color: $success;
    margin: 0;
    padding-left: 2;
}

/* AutoCompleteInput - The input field widget with slash command suggestions.
   Targets 'AutoCompleteInput' in widgets.py. */
AutoCompleteInput {
    border: none;
    background: $background;
    color: $foreground;
    padding: 0 1;
}

AutoCompleteInput:focus {
    border: none;
}

AutoCompleteInput > .input--placeholder {
    color: $text-muted;
}

/* The dropdown menu for slash command suggestions (a floating overlay — opaque
   ANSI box, not tokenised, so it stays readable over content on every palette). */
AutoCompleteInput .suggestions {
    background: ansi_black;
    border: solid ansi_bright_black;
    border-top: none;
    padding: 0 1;
    max-height: 12;
}

AutoCompleteInput .suggestion {
    padding: 0 1;
}

AutoCompleteInput .suggestion--highlighted {
    background: ansi_bright_black;
}

/* ActivityBar - Status bar above input showing Thinking/Tools Working spinners.
   Targets 'ActivityBar' in widgets.py. */
ActivityBar {
    height: 1;
    background: $background;
    color: $warning;
    padding: 0 1;
}

ActivityBar Static {
    width: 1fr;
    height: 1;
}

#activity-bar {
    height: 1;
    width: 100%;
}

/* CLIInputBar - The container at the bottom holding the prompt ">" and the input field.
   Targets 'CLIInputBar' in widgets.py. */
CLIInputBar {
    height: auto;
    /* Grow with the message (height: auto) up to ~20 visible lines, then the
       TextArea scrolls internally. 24 = 20 input rows + the heavy border (1) and
       vertical padding (2). The bar only gets this tall when you actually type a
       long message; a single line stays one row. */
    max-height: 24;
    background: $background;
    /* The separator follows the palette's primary. Under the ansi palette
       $primary is a fixed blue (#5eaff5) — reliable on every terminal, where
       the terminal's own bright-blue can render oddly for heavy borders; under
       an RGB palette it adopts that palette's primary. */
    border-top: heavy $primary;
    padding: 1 0;
}

CLIInputBar Static {
    width: auto;
    content-align: center middle;
    padding: 0 1;
}

/* The actual text area inside the input bar.
   transparent (not $background) so the TextArea composites onto whatever is
   behind it instead of filling its strip with the underlying black of an
   ansi_default background. This matches Textual's own
   `TextArea:ansi { background: transparent }`. */
CLIInputBar #chat-input {
    width: 1fr;
    height: auto;
    min-height: 1;
    /* Up to 20 visible input lines (was 7); beyond that the TextArea scrolls
       internally and keeps the cursor in view. Kept just under the bar's
       max-height so the whole field stays visible. */
    max-height: 20;
    border: none;
    background: transparent;
    color: $foreground;
    padding: 0 1;
}

CLIInputBar #chat-input:focus {
    border: none;
}

/* The "❯" prompt character — matches the separator (see CLIInputBar border-top). */
CLIInputBar .prompt {
    color: $primary;
    text-style: bold;
}

/* Placeholder hint text inside the input area. */
#input-placeholder {
    color: $text-muted;
    text-style: italic;
    width: 1fr;
    height: 1;
    padding: 0 1;
}

/* StatusBar - The bar at the very bottom showing context info (model, tokens).
   Targets 'StatusBar' in widgets.py. */
StatusBar {
    height: 1;
    background: $background;
    color: $text-muted;
    padding: 0 1;
}

StatusBar Static {
    width: auto;
}

StatusBar .spacer {
    width: 1fr;
}

StatusBar .key-hint {
    color: $text-muted;
}

/* Banner spacer - An invisible widget used to push the banner to the bottom initially. */
#banner-spacer {
    height: 0;
    background: $background;
}

/* BannerWidget - The ASCII art banner shown at startup. */
BannerWidget {
    height: auto;
    background: $background;
    padding: 1 2;
    /* Gray separators use the literal ANSI grey: it is a concrete colour valid
       for borders under every palette (the $text-muted token is auto-contrast
       and rejected by border properties on RGB palettes). */
    border-bottom: solid ansi_bright_black;
}

BannerWidget .banner-line {
    text-align: center;
}

BannerWidget .banner-title {
    color: $accent;
    text-style: bold;
}

BannerWidget .banner-subtitle {
    color: $text-muted;
}

BannerWidget .banner-version {
    color: $success;
}

/* ToolPanel - The panel that slides up/appears above the input bar showing running tools.
   Targets 'ToolPanel' in widgets.py. */
ToolPanel {
    layout: vertical;
    height: auto;
    min-height: 6;
    max-height: 24%;
    background: $background;
    border-top: solid ansi_bright_black;
    padding: 1 1;
    overflow-y: scroll;
    display: none;
}

ToolPanel .tool-item {
    height: auto;
    color: $foreground;
    padding: 0 1;
}

ToolPanel .tool-item.running {
    color: $warning;
}

ToolPanel .tool-item.completed {
    color: $success;
}

/* AgentPanel - Scrollable panel for agent run history.
   Toggled with Ctrl+G. Targets 'AgentPanel' in widgets.py. */
AgentPanel {
    layout: vertical;
    height: auto;
    max-height: 40%;
    background: $background;
    border-top: solid ansi_bright_black;
    padding: 1 1;
    overflow-y: scroll;
    display: none;
}

AgentPanel .agent-entry {
    height: auto;
    padding: 0 1;
}

AgentPanel .agent-status {
    height: auto;
    color: $warning;
    padding: 0 1;
}

AgentPanel .agent-status.running {
    color: $warning;
}

AgentPanel .agent-status.completed {
    color: $success;
}

AgentPanel .agent-status.error {
    color: $error;
}

AgentPanel .agent-status.timeout {
    color: $warning;
}

AgentPanel .agent-detail {
    height: auto;
    color: $text-muted;
    padding: 0 0 0 4;
}

/* ThinkingPanel - Scrollable panel showing the model's reasoning stream.
   Toggled with Ctrl+T. Taller than the tool/agent panels because reasoning is
   long-form. Targets 'ThinkingPanel' in widgets.py. */
ThinkingPanel {
    layout: vertical;
    height: auto;
    max-height: 60%;
    background: $background;
    border-top: solid ansi_bright_black;
    padding: 1 1;
    overflow-y: scroll;
    display: none;
}

ThinkingPanel .thinking-content {
    height: auto;
    color: $foreground;
    text-style: italic;
    padding: 0 1;
}

/* AyderApp - The root application screen. */
Screen {
    layout: vertical;
    background: $background;
}

/* Inline mode - Configures the app to run within the terminal flow rather than full screen. */
Screen:inline {
    height: 100vh;
    min-height: 20;
}

/* ID-based selectors for the main layout components in app.py compose() */

#chat-view {
    height: 1fr;
    width: 100%;
    background: $background;
    scrollbar-size: 0 0;
    scrollbar-size-horizontal: 0;
    scrollbar-size-vertical: 0;
}

#tool-panel {
    height: auto;
    min-height: 0;
    max-height: 20%;
    width: 100%;
}

#agent-panel {
    min-height: 0;
    max-height: 40%;
    width: 100%;
}

#thinking-panel {
    min-height: 0;
    max-height: 60%;
    width: 100%;
}

#input-bar {
    height: auto;
    min-height: 1;
    width: 100%;
}

#status-bar {
    height: 1;
    width: 100%;
}
"""


# ── Textual ANSI palettes (the default ayder palette) ────────────────────
# Our own ansi-dark / ansi-light (Textual 8.2.5+): every surface token is
# ansi_default (terminal passthrough) and ansi=True emits real ANSI escapes so
# the user's terminal colours are respected. Modelled on Textual's built-in
# ansi-dark / ansi-light, with two deliberate tunings so AYDER_CSS resolves to
# ayder's signature look under the ansi palette:
#   * primary = "#5eaff5"  -> the separator/prompt stay a reliable blue (the
#     terminal's own bright-blue can render oddly for heavy borders); a hex
#     stays truecolor on capable terminals and downsamples to blue elsewhere.
#   * text-muted = "ansi_bright_black" -> dim chrome uses the terminal's grey
#     palette colour rather than dimmed foreground.
# Any RGB Textual theme (monokai, dracula …) can be used instead via
# [ui] palette; the same AYDER_CSS then adopts that palette's tokens.

AYDER_DARK_TEXTUAL = TextualTheme(
    name="ayder-dark",
    ansi=True,
    primary="#5eaff5",
    secondary="ansi_cyan",
    warning="ansi_yellow",
    error="ansi_red",
    success="ansi_green",
    accent="ansi_bright_blue",
    foreground="ansi_default",
    background="ansi_default",
    surface="ansi_default",
    panel="ansi_default",
    boost="ansi_default",
    dark=True,
    variables={
        "text-muted": "ansi_bright_black",
        "ansi-background": "ansi_black",
        "ansi-foreground": "ansi_white",
        "border-blurred": "ansi_black",
        "block-cursor-foreground": "ansi_black",
        "block-cursor-background": "ansi_white",
        "input-cursor-background": "ansi_black",
        "input-cursor-foreground": "ansi_bright_white",
        "input-cursor-text-style": "none",
        "input-selection-background": "ansi_bright_blue",
        "input-selection-foreground": "ansi_black",
        "screen-selection-background": "ansi_bright_blue",
        "screen-selection-foreground": "ansi_black",
    },
)

AYDER_LIGHT_TEXTUAL = TextualTheme(
    name="ayder-light",
    ansi=True,
    primary="#5eaff5",
    secondary="ansi_cyan",
    warning="ansi_bright_red",
    error="ansi_red",
    success="ansi_green",
    accent="ansi_blue",
    foreground="ansi_default",
    background="ansi_default",
    surface="ansi_default",
    panel="ansi_default",
    boost="ansi_default",
    dark=False,
    variables={
        "text-muted": "ansi_bright_black",
        "border": "ansi_blue",
        "border-blurred": "ansi_white",
        "block-cursor-foreground": "ansi_bright_white",
        "block-cursor-background": "ansi_blue",
        "ansi-background": "ansi_white",
        "ansi-foreground": "ansi_black",
        "input-cursor-background": "ansi_bright_white",
        "input-cursor-foreground": "ansi_black",
        "input-cursor-text-style": "reverse",
        "input-selection-background": "ansi_cyan",
        "input-selection-foreground": "ansi_white",
        "scrollbar": "ansi_bright_blue",
        "scrollbar-hover": "ansi_blue",
        "scrollbar-active": "ansi_blue",
        "scrollbar-background": "ansi_white",
        "scrollbar-corner-color": "ansi_default",
        "scrollbar-background-hover": "ansi_white",
        "scrollbar-background-active": "ansi_white",
        "block-hover-background": "ansi_white",
        "screen-selection-background": "ansi_cyan",
        "screen-selection-foreground": "ansi_bright_white",
    },
)

# Registered with the Textual App (see app.py).
AYDER_TEXTUAL_THEMES = [AYDER_DARK_TEXTUAL, AYDER_LIGHT_TEXTUAL]


# ── Register the CSS themes (our [ui] theme registry) ────────────────────
_AYDER_DESC = "Linux-console layout; respects the terminal by default, overlays any palette"

register_theme(
    Theme(
        name="ayder-dark",
        description=f"{_AYDER_DESC} (dark terminals)",
        css=AYDER_CSS,
        ansi=True,
        textual_theme="ayder-dark",
    )
)

register_theme(
    Theme(
        name="ayder-light",
        description=f"{_AYDER_DESC} (light terminals)",
        css=AYDER_CSS,
        ansi=True,
        textual_theme="ayder-light",
    )
)

# Backwards-compatible alias: "ayder" -> "ayder-dark".
register_theme(
    Theme(
        name="ayder",
        description=f"{_AYDER_DESC} (alias for ayder-dark)",
        css=AYDER_CSS,
        ansi=True,
        textual_theme="ayder-dark",
    )
)
