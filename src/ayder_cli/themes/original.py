"""
Original theme for ayder-cli TUI.

This is the default theme with the classic ayder styling.
"""

from . import Theme, register_theme

# Original CSS styles extracted from tui.py
ORIGINAL_CSS = """\
/* CLIConfirmScreen - Confirmation modal */
CLIConfirmScreen {
    align: center bottom;
}

CLIConfirmScreen > Vertical {
    width: 100%;
    height: auto;
    background: $surface;
    border-top: solid $primary;
    padding: 1 2;
}

CLIConfirmScreen .prompt {
    text-style: bold;
    color: $primary;
}

CLIConfirmScreen .description {
    color: $text-muted;
    margin-bottom: 1;
}

CLIConfirmScreen .diff-container {
    height: 15;
    border: solid $primary-darken-2;
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
    border: solid $primary-darken-2;
    background: $surface;
    color: $text;
}

CLIConfirmScreen .hint {
    color: $text-muted;
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
    background: $surface;
    border-top: solid $primary;
    padding: 1 2;
}

CLIPermissionScreen .prompt {
    text-style: bold;
    color: $primary;
}

CLIPermissionScreen .description {
    color: $text-muted;
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
    color: $text-muted;
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
    background: $surface;
    border-top: solid $error;
    padding: 1 2;
}

CLISafeModeScreen .title {
    text-style: bold;
    color: $error;
}

/* CLISelectScreen - Selection modal */
CLISelectScreen {
    align: center bottom;
}

CLISelectScreen > Vertical {
    width: 100%;
    max-height: 60%;
    height: auto;
    background: $surface;
    border-top: solid $primary;
    padding: 1 2;
}

CLISelectScreen .prompt {
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
}

CLISelectScreen .description {
    color: $text-muted;
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
    color: $text-muted;
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
    background: $surface;
    border-top: solid $primary;
    padding: 1 2;
}

TaskEditScreen .prompt {
    height: 1;
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
}

TaskEditScreen #task-editor {
    height: 1fr;
}

TaskEditScreen .hint {
    height: 1;
    color: $text-muted;
    text-style: dim;
    margin-top: 1;
}

/* Text selection highlight */
.selection {
    background: $primary-darken-2;
    color: $text;
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
    color: $accent;
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
    color: $text-muted;
    margin: 0;
    padding-left: 2;
    text-style: italic;
}

ChatView .tool-call {
    color: $warning;
    margin: 0;
    padding-left: 2;
}

ChatView .tool-result {
    color: $success;
    margin: 0;
    padding-left: 2;
}

ChatView .system-message {
    color: $text-muted;
    margin: 1 0 0 0;
    text-style: italic;
}

ChatView .separator {
    color: $primary-darken-2;
    margin: 1 0 0 0;
}

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

/* AutoCompleteInput - Input with slash command suggestions */
AutoCompleteInput {
    border: none;
    background: transparent;
    color: $text;
    padding: 0 1;
}

AutoCompleteInput:focus {
    border: none;
}

AutoCompleteInput > .input--placeholder {
    color: $text-muted;
}

AutoCompleteInput .suggestions {
    background: $surface;
    border: solid $primary-darken-2;
    border-top: none;
    padding: 0 1;
    max-height: 12;
}

AutoCompleteInput .suggestion {
    padding: 0 1;
}

AutoCompleteInput .suggestion--highlighted {
    background: $primary-darken-2;
}

/* CLIInputBar - Input bar with prompt */
CLIInputBar {
    height: 3;
    background: $surface;
    border-top: solid $primary-darken-2;
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
    color: $text;
    padding: 0 1;
}

CLIInputBar #chat-input:focus {
    border: none;
}

CLIInputBar .prompt {
    color: $primary;
    text-style: bold;
}

/* StatusBar - Bottom status bar */
StatusBar {
    height: 1;
    background: $primary-darken-2;
    color: $text;
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

/* Banner spacer - pushes banner to bottom on startup */
#banner-spacer {
    height: 0;
    background: transparent;
}

/* BannerWidget - Top banner */
BannerWidget {
    height: auto;
    background: $surface;
    padding: 1 2;
    border-bottom: solid $primary-darken-2;
}

BannerWidget .banner-line {
    text-align: center;
}

BannerWidget .banner-title {
    color: $primary;
    text-style: bold;
}

BannerWidget .banner-subtitle {
    color: $text-muted;
}

BannerWidget .banner-version {
    color: $success;
}

/* ToolPanel - Tool execution display */
ToolPanel {
    layout: vertical;
    height: auto;
    min-height: 6;
    max-height: 16;
    background: $surface-darken-1;
    border-top: heavy $primary;
    padding: 1 1;
    overflow-y: scroll;
}

ToolPanel .tool-item {
    height: auto;
    color: $text;
    padding: 0 1;
}

ToolPanel .tool-item.running {
    color: $warning;
}

ToolPanel .tool-item.completed {
    color: $success;
}

/* AyderApp - Main application */
Screen {
    layout: vertical;
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
    max-height: 25%;
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
original_theme = Theme(
    name="original",
    description="Classic ayder theme with default terminal styling",
    css=ORIGINAL_CSS
)

register_theme(original_theme)
