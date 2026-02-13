"""
Claude theme for ayder-cli TUI.

Dark terminal aesthetic with minimal chrome, clean separators,
and a muted color palette inspired by modern terminal emulators.
"""

from . import Theme, register_theme

CLAUDE_CSS = """\
/* ── Variables (via Textual design tokens) ─────────────────────────── */
/* Using explicit colors because Textual tokens don't cover everything */

/* CLIConfirmScreen - The modal dialog that appears when a tool needs user approval.
   Targets the 'CLIConfirmScreen' class in screens.py. */
CLIConfirmScreen {
    align: center bottom;
}

/* The main container within the confirmation screen. */
CLIConfirmScreen > Vertical {
    width: 100%;
    height: auto;
    background: #12122a;
    border-top: solid #666680;
    padding: 1 2;
}

/* The question/prompt text in the confirmation dialog ("Allow tool execution?"). */
CLIConfirmScreen .prompt {
    text-style: bold;
    color: #5eaff5;
}

/* The description of the tool action ("Run command: ls -la"). */
CLIConfirmScreen .description {
    color: #b8b8c8;
    margin-bottom: 1;
}

/* The scrollable container showing the code diff for file modifications. */
CLIConfirmScreen .diff-container {
    height: 15;
    border: solid #333350;
    margin: 1 0;
    padding: 1;
    background: #0a0a18;
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
    border: solid #333350;
    background: #0a0a18;
    color: #e0e0e8;
}

/* Hint text at the bottom of the confirmation screen. */
CLIConfirmScreen .hint {
    color: #666680;
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
    background: #12122a;
    border-top: solid #666680;
    padding: 1 2;
}

CLIPermissionScreen .prompt {
    text-style: bold;
    color: #5eaff5;
}

CLIPermissionScreen .description {
    color: #b8b8c8;
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
    color: #666680;
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
    background: #12122a;
    border-top: solid #c45050;
    padding: 1 2;
}

CLISafeModeScreen .title {
    text-style: bold;
    color: #c45050;
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
    background: #12122a;
    border-top: solid #666680;
    padding: 1 2;
}

CLISelectScreen .prompt {
    text-style: bold;
    color: #5eaff5;
    margin-bottom: 1;
}

CLISelectScreen .description {
    color: #666680;
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
    color: #666680;
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
    background: #12122a;
    border-top: solid #666680;
    padding: 1 2;
}

TaskEditScreen .prompt {
    height: 1;
    text-style: bold;
    color: #5eaff5;
    margin-bottom: 1;
}

TaskEditScreen #task-editor {
    height: 1fr;
}

TaskEditScreen .hint {
    height: 1;
    color: #666680;
    text-style: dim;
    margin-top: 1;
}

/* Generic text selection highlight color. */
.selection {
    background: #264f78;
    color: #e0e0e8;
}

/* ChatView - The main scrollable area displaying the chat history.
   Targets 'ChatView' widget in widgets.py. */
ChatView {
    height: 100%;
    padding: 0 1;
    background: transparent;
}

/* Base style for all message lines within ChatView. */
ChatView Static {
    height: auto;
    margin: 0;
    padding: 0;
    background: transparent;
}

/* User message text ("> Hello"). */
ChatView .user-message {
    color: #5eaff5;
    margin: 1 0 0 0;
}

/* Assistant message prefix ("<"). */
ChatView .assistant-message {
    color: #b8b8c8;
    margin: 1 0 0 0;
}

/* The actual Markdown content of the assistant's reply. */
ChatView .assistant-message-content {
    margin: 0 0 0 2;
    color: #b8b8c8;
}

/* Styling for the <think> blocks (reasoning text). */
ChatView .thinking {
    color: #555570;
    margin: 0;
    padding-left: 2;
    text-style: italic;
}

/* Tool call display ("→ write_file ..."). */
ChatView .tool-call {
    color: #d4a043;
    margin: 0;
    padding-left: 2;
}

/* Tool result display ("✓ File written"). */
ChatView .tool-result {
    color: #5cb870;
    margin: 0;
    padding-left: 2;
}

/* System messages ("Operation cancelled", "Error: ..."). */
ChatView .system-message {
    color: #666680;
    margin: 1 0 0 0;
    text-style: italic;
}

/* Separator lines (if used). */
ChatView .separator {
    color: #333350;
    margin: 1 0 0 0;
}

/* The "Thinking..." spinner message. */
ChatView .thinking-message {
    color: #d4a043;
    margin: 1 0 0 0;
}

ChatView .tool-running {
    color: #d4a043;
    margin: 0;
    padding-left: 2;
}

ChatView .tool-completed {
    color: #5cb870;
    margin: 0;
    padding-left: 2;
}

/* AutoCompleteInput - The input field widget with slash command suggestions.
   Targets 'AutoCompleteInput' in widgets.py. */
AutoCompleteInput {
    border: none;
    background: transparent;
    color: #e0e0e8;
    padding: 0 1;
}

AutoCompleteInput:focus {
    border: none;
}

AutoCompleteInput > .input--placeholder {
    color: #666680;
}

/* The dropdown menu for slash command suggestions. */
AutoCompleteInput .suggestions {
    background: #12122a;
    border: solid #333350;
    border-top: none;
    padding: 0 1;
    max-height: 12;
}

AutoCompleteInput .suggestion {
    padding: 0 1;
}

AutoCompleteInput .suggestion--highlighted {
    background: #333350;
}

/* ActivityBar - Status bar above input showing Thinking/Tools Working spinners.
   Targets 'ActivityBar' in widgets.py. */
ActivityBar {
    height: 1;
    background: #12122a;
    color: #d4a043;
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
    max-height: 8;
    background: transparent;
    border-top: solid #333350;
    border-bottom: solid #333350;
    padding: 0;
}

CLIInputBar Static {
    width: auto;
    content-align: center middle;
    padding: 0 1;
}

/* The actual text area inside the input bar. */
CLIInputBar #chat-input {
    width: 1fr;
    height: auto;
    min-height: 1;
    max-height: 7;
    border: none;
    background: transparent;
    color: #e0e0e8;
    padding: 0 1;
}

CLIInputBar #chat-input:focus {
    border: none;
}

/* The ">" prompt character. */
CLIInputBar .prompt {
    color: #5eaff5;
    text-style: bold;
}

/* StatusBar - The bar at the very bottom showing context info (model, tokens).
   Targets 'StatusBar' in widgets.py. */
StatusBar {
    height: 1;
    background: #12122a;
    color: #666680;
    padding: 0 1;
}

StatusBar Static {
    width: auto;
}

StatusBar .spacer {
    width: 1fr;
}

StatusBar .key-hint {
    color: #555570;
}

/* Banner spacer - An invisible widget used to push the banner to the bottom initially. */
#banner-spacer {
    height: 0;
    background: transparent;
}

/* BannerWidget - The ASCII art banner shown at startup. */
BannerWidget {
    height: auto;
    background: transparent;
    padding: 1 2;
    border-bottom: solid #333350;
}

BannerWidget .banner-line {
    text-align: center;
}

BannerWidget .banner-title {
    color: #5eaff5;
    text-style: bold;
}

BannerWidget .banner-subtitle {
    color: #666680;
}

BannerWidget .banner-version {
    color: #5cb870;
}

/* ToolPanel - The panel that slides up/appears above the input bar showing running tools.
   Targets 'ToolPanel' in widgets.py. */
ToolPanel {
    layout: vertical;
    height: auto;
    min-height: 6;
    max-height: 24%;
    background: #0a0a18;
    border-top: solid #333350;
    padding: 1 1;
    overflow-y: scroll;
    display: none;
}

ToolPanel .tool-item {
    height: auto;
    color: #e0e0e8;
    padding: 0 1;
}

ToolPanel .tool-item.running {
    color: #d4a043;
}

ToolPanel .tool-item.completed {
    color: #5cb870;
}

/* AyderApp - The root application screen. */
Screen {
    layout: vertical;
    background: #0d0d1a;
}

/* Inline mode - Configures the app to run within the terminal flow rather than full screen.
   Sets the height of the 'window' seen in the terminal. */
Screen:inline {
    height: 80vh;
    min-height: 20;
}

/* ID-based selectors for the main layout components in app.py compose() */

#chat-view {
    height: 1fr; /* Takes up all available space above the input/tools */
    width: 100%;
    background: transparent;
    scrollbar-size: 0 0; /* Hides the scrollbar track */
    scrollbar-size-horizontal: 0;
    scrollbar-size-vertical: 0;
}

#chat-view:focus {
    scrollbar-size: 0 0;
}

#tool-panel {
    height: auto;
    min-height: 0;
    max-height: 20%;
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

# Create and register the theme
claude_theme = Theme(
    name="claude",
    description="Dark terminal aesthetic with minimal chrome and muted colors",
    css=CLAUDE_CSS,
)

register_theme(claude_theme)
