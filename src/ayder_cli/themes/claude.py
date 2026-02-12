"""
Claude theme for ayder-cli TUI.

Dark terminal aesthetic with minimal chrome, clean separators,
and a muted color palette inspired by modern terminal emulators.
"""

from . import Theme, register_theme

CLAUDE_CSS = """\
/* ── Variables (via Textual design tokens) ─────────────────────────── */
/* Using explicit colors because Textual tokens don't cover everything */

/* CLIConfirmScreen - Confirmation modal */
CLIConfirmScreen {
    align: center bottom;
}

CLIConfirmScreen > Vertical {
    width: 100%;
    height: auto;
    background: #12122a;
    border-top: solid #666680;
    padding: 1 2;
}

CLIConfirmScreen .prompt {
    text-style: bold;
    color: #5eaff5;
}

CLIConfirmScreen .description {
    color: #b8b8c8;
    margin-bottom: 1;
}

CLIConfirmScreen .diff-container {
    height: 15;
    border: solid #333350;
    margin: 1 0;
    padding: 1;
    overflow: auto scroll;
}

CLIConfirmScreen .option-list {
    height: auto;
    max-height: 10;
    overflow-y: auto;
    margin: 1 0;
    padding: 0 1;
}

CLIConfirmScreen #instruction-input {
    display: none;
    margin: 1 0;
    border: solid #333350;
    background: #0a0a18;
    color: #e0e0e8;
}

CLIConfirmScreen .hint {
    color: #666680;
    text-style: dim;
    margin-top: 1;
}

/* CLIPermissionScreen - Permission toggle modal */
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

/* CLISafeModeScreen - Safe mode block modal */
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

/* CLISelectScreen - Selection modal */
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

/* TaskEditScreen - In-app task editor */
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

/* Text selection highlight */
.selection {
    background: #264f78;
    color: #e0e0e8;
}

/* ChatView - Main chat display */
ChatView {
    height: 100%;
    padding: 0 1;
    background: transparent;
}

ChatView Static {
    height: auto;
    margin: 0;
    padding: 0;
    background: transparent;
}

ChatView .user-message {
    color: #5eaff5;
    margin: 1 0 0 0;
}

ChatView .assistant-message {
    color: #b8b8c8;
    margin: 1 0 0 0;
}

ChatView .assistant-message-content {
    margin: 0 0 0 2;
    color: #b8b8c8;
}

ChatView .thinking {
    color: #555570;
    margin: 0;
    padding-left: 2;
    text-style: italic;
}

ChatView .tool-call {
    color: #d4a043;
    margin: 0;
    padding-left: 2;
}

ChatView .tool-result {
    color: #5cb870;
    margin: 0;
    padding-left: 2;
}

ChatView .system-message {
    color: #666680;
    margin: 1 0 0 0;
    text-style: italic;
}

ChatView .separator {
    color: #333350;
    margin: 1 0 0 0;
}

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

/* AutoCompleteInput - Input with slash command suggestions */
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

/* CLIInputBar - Input bar with prompt */
CLIInputBar {
    height: 3;
    background: transparent;
    border-top: solid #333350;
    padding: 0;
}

CLIInputBar Static {
    width: auto;
    content-align: center middle;
    padding: 0 1;
}

CLIInputBar #chat-input {
    width: 1fr;
    height: 3;
    border: none;
    background: transparent;
    color: #e0e0e8;
    padding: 0 1;
}

CLIInputBar #chat-input:focus {
    border: none;
}

CLIInputBar .prompt {
    color: #5eaff5;
    text-style: bold;
}

/* StatusBar - Bottom status bar */
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

/* Banner spacer - pushes banner to bottom on startup */
#banner-spacer {
    height: 0;
    background: transparent;
}

/* BannerWidget - Top banner */
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

/* ToolPanel - Tool execution display */
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

/* AyderApp - Main application */
Screen {
    layout: vertical;
    background: #0d0d1a;
}

/* Inline mode - runs within terminal flow, not full-screen */
Screen:inline {
    height: 80vh;
    min-height: 20;
}

#chat-view {
    height: 1fr;
    width: 100%;
    background: transparent;
    scrollbar-size: 0 0;
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
