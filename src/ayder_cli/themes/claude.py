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

/* CLIMultiSelectScreen - A multi-selection modal (used for /plugin command, etc.).
   Targets 'CLIMultiSelectScreen' in screens.py. */
CLIMultiSelectScreen {
    align: center bottom;
}

CLIMultiSelectScreen > Vertical {
    width: 100%;
    max-height: 60%;
    height: auto;
    background: #12122a;
    border-top: solid #666680;
    padding: 1 2;
}

CLIMultiSelectScreen .prompt {
    text-style: bold;
    color: #5eaff5;
    margin-bottom: 1;
}

CLIMultiSelectScreen .description {
    color: #666680;
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
    color: #666680;
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
    background: #12122a;
    border-top: solid #666680;
    padding: 1 2;
}

AgentListScreen .prompt {
    text-style: bold;
    color: #5eaff5;
    margin-bottom: 1;
}

AgentListScreen .description {
    color: #666680;
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

/* CLIHelpScreen - Centered help modal showing keybindings.
   Targets 'CLIHelpScreen' in screens.py. */
CLIHelpScreen {
    align: center middle;
}

CLIHelpScreen > Vertical {
    width: 50;
    height: auto;
    max-height: 80%;
    background: #12122a;
    border: solid #5eaff5;
    padding: 1 2;
}

CLIHelpScreen .prompt {
    text-style: bold;
    color: #5eaff5;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

CLIHelpScreen #help-content {
    color: #b8b8c8;
    height: auto;
}

/* EvrenTermsScreen - evren terms-of-use modal with Approve / Deny.
   Targets 'EvrenTermsScreen' in screens.py. */
EvrenTermsScreen {
    align: center middle;
}

EvrenTermsScreen > Vertical {
    width: 90%;
    height: 85%;
    background: #12122a;
    border: solid #5eaff5;
    padding: 1 2;
}

EvrenTermsScreen .prompt {
    text-style: bold;
    color: #5eaff5;
    text-align: center;
    width: 100%;
    margin-bottom: 1;
}

EvrenTermsScreen #terms-scroll {
    height: 1fr;
    color: #b8b8c8;
}

EvrenTermsScreen #terms-buttons {
    height: auto;
    align: center middle;
    margin-top: 1;
}

EvrenTermsScreen Button {
    margin: 0 2;
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

/* Base style for the message widgets. Direct children only: the blocks inside
   an assistant reply are Statics too and are styled by the reply rules below. */
ChatView > Static {
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

/* AssistantReply - An assistant reply: Textual's Markdown widget, so its text can
   be selected with the mouse (AssistantReply in widgets.py). One blank row
   between blocks and none around the reply, as rich.markdown drew it. */
ChatView > AssistantReply {
    height: auto;
    margin: 0;
    padding: 0;
    background: transparent;
    color: #b8b8c8;
}

ChatView AssistantReply > MarkdownBlock {
    margin: 1 0 0 0;
}

/* Not :first-child: Textual restyles every block on each mount for an
   order-dependent rule (see AssistantReply). */
ChatView AssistantReply > .-first-block {
    margin: 0;
}

/* Headings: bold, no background bar; the top two levels in the accent blue. */
ChatView AssistantReply MarkdownHeader {
    background: transparent;
    color: #e0e0e8;
    text-style: bold;
}

ChatView AssistantReply MarkdownH1 {
    content-align: center middle;
    color: #5eaff5;
}

ChatView AssistantReply MarkdownH2 {
    color: #5eaff5;
}

/* Code blocks: a navy box with one row and two columns of padding, as
   rich.markdown's padded code box; long lines wrap. */
ChatView AssistantReply MarkdownFence {
    background: #12122a;
    overflow-x: hidden;
}

ChatView AssistantReply MarkdownFence > Label {
    width: 1fr;
    padding: 1 2;
    text-wrap: wrap;
}

/* Tables: as wide as their content. */
ChatView AssistantReply MarkdownTable {
    width: auto;
    background: transparent;
}

/* In-chat items: thinking, tool calls and agent runs. Statics built from Content, so the mouse can
   select their text. Tool and agent items are one line until expanded (Ctrl+O,
   Ctrl+G), then a bordered box; the thinking item is a bordered box that grows
   with the reasoning up to 8 rows and stays. Borders only, never a
   background. */
ChatView > .thinking-item {
    width: 100%;
    color: #b8b8c8;
    background: transparent;
    margin: 1 0 0 0;
    padding: 0 1;
    border: round #333350;
}

ChatView > .toolbox,
ChatView > .agentbox {
    color: #b8b8c8;
    background: transparent;
    margin: 0;
}

ChatView > .toolbox.-expanded,
ChatView > .agentbox.-expanded {
    width: 100%;
    margin: 1 0 0 0;
    padding: 0 1;
    border: round #333350;
}

ChatView > .toolbox.-expanded.-error,
ChatView > .agentbox.-expanded.-error {
    border: round #ff5555;
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
    background: #1a1a35;
    border-top: heavy #5eaff5;
    padding: 1 0;
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

/* The "❯" prompt character. */
CLIInputBar .prompt {
    color: #5eaff5;
    text-style: bold;
}

/* Placeholder hint text inside the input area. */
#input-placeholder {
    color: #555570;
    text-style: italic;
    width: 1fr;
    height: 1;
    padding: 0 1;
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

/* AyderApp - The root application screen. */
Screen {
    layout: vertical;
    background: #0d0d1a;
}

/* ID-based selectors for the main layout components in app.py compose() */

#chat-view {
    height: 1fr;
    width: 100%;
    background: transparent;
    scrollbar-size: 0 0;
    scrollbar-size-horizontal: 0;
    scrollbar-size-vertical: 0;
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
