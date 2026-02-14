# Ayder TUI — Visual Element Map

All Textual widgets, screens, and layout elements with ASCII mockups.

---

## Main Application Layout

**Class:** `AyderApp(App)` — `tui/app.py`
**Bindings:** `^Q` quit, `^C`/`^X` cancel, `^L` clear, `^O` toggle tools

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Screen (#0d0d1a)                            │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                                                                │  │
│  │                    ChatView  #chat-view                        │  │
│  │                    (VerticalScroll)                             │  │
│  │                      height: 1fr                               │  │
│  │                                                                │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │  #banner-spacer (Static, pushes banner to bottom)        │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────────┐  │  │
│  │  │  .banner-content (Static)  — create_tui_banner()         │  │  │
│  │  │  ASCII gradient art + tagline + version                  │  │  │
│  │  └──────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  > What files are in src/?              .user-message (cyan)   │  │
│  │                                                                │  │
│  │    ... reasoning preview ...            .thinking (dim italic) │  │
│  │                                                                │  │
│  │    The src directory contains...        .assistant-message     │  │
│  │    (rendered as Markdown)               (Markdown widget)      │  │
│  │                                                                │  │
│  │    → read_file(src/main.py)             .tool-call (yellow)    │  │
│  │    ✓ File content returned              .tool-result (green)   │  │
│  │                                                                │  │
│  │    Operation cancelled.                 .system-message (dim)  │  │
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ToolPanel  #tool-panel  (Container)                           │  │
│  │  hidden by default — toggle with ^O                            │  │
│  │  max-height: 24%                                               │  │
│  │                                                                │  │
│  │    ⠋ read_file {'file_path': 'src/m...    .tool-item.running   │  │
│  │    ✓ write_file → File written            .tool-item.completed │  │
│  │    ⠋ run_shell_command {'command': ...    .tool-item.running   │  │
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  ActivityBar  #activity-bar  (Horizontal)  height: 1           │  │
│  │  can_focus=False  can_focus_children=False                     │  │
│  │                                                                │  │
│  │  ⣾ Thinking... | Tools Working...     #activity-text (Static)  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  CLIInputBar  #input-bar  (Horizontal)  max-height: 8         │  │
│  │──────────────────────────────────────── border-top: #333350 ──│  │
│  │                                                                │  │
│  │  >  Type your message here...          #chat-input             │  │
│  │  .prompt                               (_SubmitTextArea)       │  │
│  │  (cyan bold)                           Enter=submit            │  │
│  │                                        Shift+Enter=newline     │  │
│  │──────────────────────────────────────── border-bottom ─────── │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  StatusBar  #status-bar  (Horizontal)  height: 1  bg: #12122a │  │
│  │                                                                │  │
│  │  model: qwen3  | mode: rwx  | tokens: 1,234  | iter: 3/50    │  │
│  │  #model-label   #mode-label  #token-label      #iter-label    │  │
│  │                                                                │  │
│  │  | files: 2   ·····spacer·····   ^C:cancel ^L:clear ^O:tools  │  │
│  │  #files-label   .spacer          ^Q:quit     .key-hint        │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Banner (on startup)

**Function:** `create_tui_banner(model, ver)` — `tui/helpers.py`
**Gradient:** cyan → blue → indigo → purple → magenta → pink

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│     █████╗  ██╗   ██╗ ██████╗  ███████╗ ██████╗                     │
│    ██╔══██╗ ╚██╗ ██╔╝ ██╔══██╗ ██╔════╝ ██╔══██╗                   │
│    ███████║  ╚████╔╝  ██║  ██║ █████╗   ██████╔╝                   │
│    ██╔══██║   ╚██╔╝   ██║  ██║ ██╔══╝   ██╔══██╗                   │
│    ██║  ██║    ██║    ██████╔╝ ███████╗ ██║  ██║                    │
│    ╚═╝  ╚═╝    ╚═╝    ╚═════╝  ╚══════╝ ╚═╝  ╚═╝                  │
│   ─────────────────────────────────────────────                     │
│   ◆ AI Agent for Development & Reasoning                            │
│   v0.9.x · qwen3-coder:latest · sandboxed                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## CLIConfirmScreen — Tool Approval Dialog

**Class:** `CLIConfirmScreen(ModalScreen[ConfirmResult | None])` — `tui/screens.py`
**Alignment:** bottom-center
**Keys:** `↑↓` navigate, `Enter` select, `Y` approve, `N`/`Esc` deny, `PgUp`/`PgDn` scroll diff

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│                (chat area visible above, dimmed)                      │
│                                                                      │
├══════════════════════════════════════════ border-top: #666680 ═══════╡
│  Vertical  (bg: #12122a)                                             │
│                                                                      │
│  ? Tool: write_file                              Label .prompt       │
│  Write content to src/main.py                    Label .description  │
│                                                                      │
│  ┌──────────────────────────────────────── .diff-container ───────┐  │
│  │  VerticalScroll  #diff-scroll                                  │  │
│  │  border: #333350, bg: #0a0a18, height: 15                     │  │
│  │                                                                │  │
│  │  --- a/main.py                                    (dim)        │  │
│  │  +++ b/main.py                                    (dim)        │  │
│  │  @@ -1,3 +1,5 @@                                 (cyan)       │  │
│  │   import os                                       (dim)        │  │
│  │  -old_function()                                  (red)        │  │
│  │  +new_function()                                  (green)      │  │
│  │  +added_line()                                    (green)      │  │
│  │                                                                │  │
│  │  Static  #diff-content                                         │  │
│  │                   ↕ PgUp / PgDn to scroll                      │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│   → Yes, allow this action              Static #option-list          │
│     No, deny this action                .option-list                 │
│     Provide custom instructions                                      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Type your instructions...            Input #instruction-input │  │
│  │  (hidden until "instruct" selected)   display: none by default │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ↑↓ navigate, PgUp/PgDn scroll diff, Enter select, Y/N, Esc cancel │
│                                                      Label .hint     │
└──────────────────────────────────────────────────────────────────────┘
```

**Return:** `ConfirmResult(action, instructions)` — `tui/types.py`

---

## CLIPermissionScreen — Permission Toggle

**Class:** `CLIPermissionScreen(ModalScreen[set | None])` — `tui/screens.py`
**Alignment:** bottom-center
**Keys:** `↑↓` navigate, `Space`/`Enter` toggle, `Esc` apply & close

```
├══════════════════════════════════════════ border-top: #666680 ═══════╡
│  Vertical  (bg: #12122a)                                             │
│                                                                      │
│  ? Permissions                                   Label .prompt       │
│  Toggle which tool categories are auto-approved  Label .description  │
│                                                                      │
│   → [✓] Read    Auto-approve read tools (always enabled) (locked)   │
│     [ ] Write   Auto-approve write tools (write_file, ...)          │
│     [ ] Execute Auto-approve execute tools (run_shell_command, ...)  │
│                                                                      │
│                                      Static #perm-list .option-list  │
│                                                                      │
│  ↑↓ navigate, Space/Enter toggle, Esc apply & close    Label .hint  │
└──────────────────────────────────────────────────────────────────────┘
```

**Return:** `set` of enabled permissions (e.g. `{"r", "w"}`)

---

## CLISafeModeScreen — Blocked Tool Warning

**Class:** `CLISafeModeScreen(ModalScreen)` — `tui/screens.py`
**Alignment:** bottom-center
**Keys:** any key dismisses

```
├══════════════════════════════════════════ border-top: #c45050 (red) ═╡
│  Vertical  (bg: #12122a)                                             │
│                                                                      │
│  ⛔ Safe Mode: 'run_shell_command' blocked       Label .title (red)  │
│  Restart without --safe to enable this tool.     Label               │
│  Press any key to continue...                    Label .dim          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## CLISelectScreen — Generic List Picker

**Class:** `CLISelectScreen(ModalScreen[str | None])` — `tui/screens.py`
**Alignment:** bottom-center, max-height: 60%
**Keys:** `↑↓`/`jk` navigate, `Enter` select, `Esc`/`q` cancel
**Used by:** `/model`, `/tasks` commands

```
├══════════════════════════════════════════ border-top: #666680 ═══════╡
│  Vertical  (bg: #12122a)                                             │
│                                                                      │
│  ? Select model                                  Label .prompt       │
│  Choose an LLM model to use                      Label .description  │
│                                                                      │
│     qwen3-coder:latest (current)                                     │
│   → llama3:8b                            Static #select-list         │
│     mistral:7b                           .select-list                │
│     deepseek-coder:6.7b                  max-height: 20              │
│                                                                      │
│  ↑↓ to navigate, Enter to select, Esc to cancel    Label .hint      │
└──────────────────────────────────────────────────────────────────────┘
```

**Return:** selected value `str` or `None`

---

## TaskEditScreen — In-App Task Editor

**Class:** `TaskEditScreen(ModalScreen[str | None])` — `tui/screens.py`
**Alignment:** bottom-center, height: 80%
**Bindings:** `^S` save, `Esc` cancel

```
├══════════════════════════════════════════ border-top: #666680 ═══════╡
│  Vertical  (bg: #12122a, height: 80%)                                │
│                                                                      │
│  Editing: add-auth-middleware                    Label .prompt        │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  # Add Auth Middleware                                         │  │
│  │                                                                │  │
│  │  ## Description                        TextArea #task-editor   │  │
│  │  Add JWT-based authentication          language="markdown"     │  │
│  │  middleware to all /api routes.         height: 1fr             │  │
│  │                                                                │  │
│  │  ## Acceptance Criteria                                        │  │
│  │  - [ ] Token validation                                        │  │
│  │  - [ ] 401 on invalid token                                    │  │
│  │  - [ ] Tests added                                             │  │
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Ctrl+S save  •  Esc cancel                         Label .hint     │
└──────────────────────────────────────────────────────────────────────┘
```

**Return:** edited content `str` or `None`

---

## ActivityBar States

**Class:** `ActivityBar(Horizontal)` — `tui/widgets.py`
**Properties:** `can_focus=False`, `can_focus_children=False`
**Spinners:** `dots2` for thinking, `aesthetic` for tools

```
Idle:
│                                                                      │

Thinking only:
│  ⣾ Thinking...                                   #activity-text     │

Tools only:
│  ⠋ Tools Working...                              #activity-text     │

Both active:
│  ⣾ Thinking... | Tools Working...                #activity-text     │
```

---

## ToolPanel States

**Class:** `ToolPanel(Container)` — `tui/widgets.py`
**Toggle:** `^O` (Ctrl+O) — `_user_visible` flag

```
Hidden (default):
(not rendered)

Visible with running tools:
┌────────────────────────────────────────── #tool-panel ────────────────┐
│  ⠋ read_file {'file_path': 'src/main.py'}       .tool-item.running  │
│  ⠋ search_codebase {'pattern': 'TODO'}           .tool-item.running  │
│  ✓ get_project_structure → project tree...       .tool-item.completed│
└──────────────────────────────────────────────────────────────────────┘
```

---

## CLIInputBar Detail

**Class:** `CLIInputBar(Horizontal)` — `tui/widgets.py`
**Inner widget:** `_SubmitTextArea(TextArea)` with `#chat-input`
**History:** `~/.ayder_chat_history` (shared with `--cli` mode)

```
Single line input:
┌──────────────────────────────────────────────────────────────────────┐
│  >  hello world█                                                     │
│  .prompt        #chat-input (_SubmitTextArea)                        │
└──────────────────────────────────────────────────────────────────────┘

Multi-line input (Shift+Enter for newlines, max-height: 8):
┌──────────────────────────────────────────────────────────────────────┐
│  >  Please refactor the auth module:                                 │
│     1. Extract middleware                                            │
│     2. Add JWT validation                                            │
│     3. Write tests█                                                  │
└──────────────────────────────────────────────────────────────────────┘

Slash command with tab completion:
┌──────────────────────────────────────────────────────────────────────┐
│  >  /imp█  →  Tab  →  /implement                                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## StatusBar Detail

**Class:** `StatusBar(Horizontal)` — `tui/widgets.py`

```
┌──────────────────────────────────────────────────────────────────────┐
│ model: qwen3 │ mode: rwx │ tokens: 12,345 │ iter: 5/50 │ files: 3  │
│ #model-label  #mode-label  #token-label     #iter-label  #files-lab │
│                                                                      │
│              .spacer (1fr)              ^C:cancel ^L:clear ^O:tools  │
│                                         ^Q:quit       .key-hint     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Widget Hierarchy (compose order)

```
AyderApp (App)
│
├── ChatView (VerticalScroll)                #chat-view    height: 1fr
│   ├── Static                               #banner-spacer
│   ├── Static .banner-content               (create_tui_banner)
│   ├── Static .user-message                 "> user text"
│   ├── Static .assistant-message            Markdown(content)
│   ├── Static .thinking                     "... reasoning"
│   ├── Static .tool-call                    "→ tool_name(args)"
│   ├── Static .tool-result                  "✓ result text"
│   └── Static .system-message               "error or status"
│
├── ToolPanel (Container)                    #tool-panel   hidden
│   ├── Static .tool-item.running            Spinner + tool info
│   └── Static .tool-item.completed          "✓ tool → result"
│
├── ActivityBar (Horizontal)                 #activity-bar height: 1
│   └── Static                               #activity-text
│
├── CLIInputBar (Horizontal)                 #input-bar
│   ├── Static .prompt                       ">"
│   └── _SubmitTextArea (TextArea)           #chat-input
│
└── StatusBar (Horizontal)                   #status-bar   height: 1
    ├── Label                                #model-label
    ├── Label                                #mode-label
    ├── Label                                #token-label
    ├── Label                                #iter-label
    ├── Label                                #files-label
    ├── Static .spacer                       (flex: 1fr)
    └── Label .key-hint                      "^C:cancel ..."
```

---

## Modal Screen Hierarchy

```
CLIConfirmScreen (ModalScreen)               align: center bottom
└── Vertical                                 bg: #12122a
    ├── Label .prompt                        "? Tool: {name}"
    ├── Label .description                   action description
    ├── VerticalScroll .diff-container       #diff-scroll  height: 15
    │   └── Static                           #diff-content
    ├── Static .option-list                  #option-list
    ├── Input                                #instruction-input (hidden)
    └── Label .hint                          keyboard shortcuts

CLIPermissionScreen (ModalScreen)            align: center bottom
└── Vertical                                 bg: #12122a
    ├── Label .prompt                        "? Permissions"
    ├── Label .description
    ├── Static .option-list                  #perm-list
    └── Label .hint

CLISafeModeScreen (ModalScreen)              align: center bottom
└── Vertical                                 border-top: red
    ├── Label .title                         "⛔ Safe Mode: ..."
    ├── Label                                instructions
    └── Label .dim                           "Press any key..."

CLISelectScreen (ModalScreen)                align: center bottom
└── Vertical                                 max-height: 60%
    ├── Label .prompt                        "? {title}"
    ├── Label .description                   (optional)
    ├── Static .select-list                  #select-list
    └── Label .hint

TaskEditScreen (ModalScreen)                 align: center bottom
└── Vertical                                 height: 80%
    ├── Label .prompt                        "Editing: {title}"
    ├── TextArea                             #task-editor  (1fr)
    └── Label .hint                          "^S save  Esc cancel"
```

---

## TUI Slash Commands

**Registry:** `COMMAND_MAP` — `tui/commands.py`
**Handler signature:** `(app: AyderApp, args: str, chat_view: ChatView) -> None`

| Command | Handler | Description |
|---|---|---|
| `/help` | `handle_help` | Show commands and keyboard shortcuts |
| `/model` | `handle_model` | Switch LLM model (pushes `CLISelectScreen`) |
| `/tasks` | `handle_tasks` | List tasks (pushes `CLISelectScreen`) |
| `/tools` | `handle_tools` | List all registered tools |
| `/verbose` | `handle_verbose` | Toggle verbose output |
| `/compact` | `handle_compact` | Summarize and compact conversation |
| `/plan` | `handle_plan` | Plan a task (injects planning prompt) |
| `/ask` | `handle_ask` | Ask LLM without tools |
| `/implement` | `handle_implement` | Implement a specific task |
| `/implement-all` | `handle_implement_all` | Implement all pending tasks |
| `/task-edit` | `handle_task_edit` | Edit task (pushes `TaskEditScreen`) |
| `/archive-completed-tasks` | `handle_archive` | Archive done tasks |
| `/permission` | `handle_permission` | Toggle permissions (pushes `CLIPermissionScreen`) |

---

## Keyboard Shortcuts

| Key | Action | Context |
|---|---|---|
| `Enter` | Submit message | Input bar |
| `Shift+Enter` | Insert newline | Input bar |
| `Tab` | Complete slash command | Input bar (when `/` typed) |
| `Up` / `Down` | Navigate history | Input bar |
| `Ctrl+C` / `Ctrl+X` | Cancel operation | Global |
| `Ctrl+L` | Clear chat | Global |
| `Ctrl+O` | Toggle tool panel | Global |
| `Ctrl+Q` | Quit | Global |
| `Y` | Approve | Confirm screen |
| `N` / `Esc` | Deny / Cancel | Confirm screen |
| `PgUp` / `PgDn` | Scroll diff | Confirm screen |
| `Ctrl+S` | Save | Task editor |

---

## Theme System

**Manager:** `ThemeManager` — `tui/theme_manager.py`
**Config:** `~/.ayder/config.toml` → `[ui] theme = "claude"`
**Themes:** `themes/claude.py` (default), `themes/original.py`

```
themes/
├── __init__.py          Theme dataclass, register_theme(), THEMES dict
├── claude.py            Dark terminal aesthetic (#0d0d1a base)
└── original.py          Textual design tokens ($primary, $surface, ...)
```
