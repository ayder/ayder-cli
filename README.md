# ayder-cli

An interactive AI agent chat client for local LLMs. It connects to a locally running [Ollama](https://ollama.com) instance and provides an autonomous coding assistant with file system tools and shell access, all from your terminal.

## Why ayder-cli?

Most AI coding assistants require cloud APIs, subscriptions, or heavy IDE plugins. There are many cli coding agents there doing amazing things if you have tokens and subscriptions. ayder-cli takes a different approach:

- **Fully local** -- runs against Ollama on your machine. While you do not depend on a AI provider, your code never leaves your computer.
- **Agentic workflow** -- the LLM doesn't just answer questions. It can read files, edit code, run shell commands, and iterate on its own, up to 10 consecutive tool calls per user message (configurable with `-I`).
- **Two interfaces** -- a classic prompt-toolkit CLI and an optional Textual TUI dashboard with chat view, context panel, and tool confirmation modals.
- **Minimal dependencies** -- OpenAI SDK (for Ollama's compatible API), prompt-toolkit, Rich, and Textual.


### Tools

LLMs on their own can only generate text. To be a useful coding assistant, the model needs to *act* on your codebase. ayder-cli provides a modular `tools/` package that gives the model a set of real tools it can call:


| Tool | What it does |
|------|-------------|
| `list_files` | List files in a directory |
| `read_file` | Read a file (supports line ranges for large files) |
| `write_file` | Write content to a file |
| `replace_string` | Find and replace a specific string in a file |
| `insert_line` | Insert content at a specific line number |
| `delete_line` | Delete a specific line from a file |
| `get_file_info` | Get file metadata (size, line count, type, symlink status) |
| `run_shell_command` | Execute a shell command (60s timeout, use for quick commands) |
| `search_codebase` | Search for patterns across the codebase (supports `full`, `files_only`, `count` output formats) |
| `get_project_structure` | Generate a tree-style project structure summary (configurable depth) |
| `create_note` | Create a markdown note in `.ayder/notes/` with YAML frontmatter and tags |
| `save_memory` | Save context or insights to persistent cross-session memory |
| `load_memory` | Load saved memories, filterable by category or search query |
| `run_background_process` | Start a long-running command in the background (servers, watchers, builds) |
| `get_background_output` | Get recent stdout/stderr output from a background process |
| `kill_background_process` | Kill a running background process (SIGTERM, then SIGKILL) |
| `list_background_processes` | List all background processes and their status |
| `list_tasks` | List pending task files in `.ayder/tasks/` (default: pending only, use status parameter for all/done) |
| `show_task` | Show task contents by path, filename, task ID, or slug |

Each tool has an OpenAI-compatible JSON schema so models that support function calling can use them natively. For models that don't, ayder-cli also parses a custom XML-like syntax (`<function=name><parameter=key>value</parameter></function>`) as a fallback.

  - **Path sandboxing**: All file operations are confined to the project root via `ProjectContext`. Path traversal attacks (`../`) and absolute paths outside the project are blocked.
  - **Safe mode** (TUI): The Textual TUI supports a safe mode that blocks `write_file`, `replace_string`, `insert_line`, `delete_line`, `run_shell_command`, `run_background_process`, and `kill_background_process`.
  - Every tool call requires your confirmation before it runs -- you always stay in control. Use `-r`, `-w`, `-x` flags to auto-approve tool categories.
  - You may also prefer to run ayder-cli in a container for additional security.

## Installation

Requires Python 3.12+ and a running Ollama instance.

```bash
# Clone the repo
git clone https://github.com/ayder/ayder-cli.git
cd ayder-cli

# Install in development mode
pip install -e .

# Or best as a uv tool (always on the path)
uv tool install .

# Make sure Ollama is running with a model
ollama pull qwen3-coder

# optimize ollama for qwen3-coder
export OLLAMA_CONTEXT_LENGTH=65536
export OLLAMA_FLASH_ATTENTION=true
export OLLAMA_MAX_LOADED_MODELS=1

ollama serve
```

## Configuration

On first run, ayder-cli creates a config file at `~/.ayder/config.toml`:

```toml
[llm]
# Ollama API endpoint (or any OpenAI-compatible server)
base_url = "http://localhost:11434/v1"
# API key (use "ollama" for local Ollama)
api_key = "ollama"
# Model name as shown in `ollama list`
model = "qwen3-coder:latest"
# Context window size in tokens
num_ctx = 65536

[editor]
# Editor for /task-edit and /edit commands (vim, nano, code, etc.)
editor = "vim"

[ui]
# Show written file contents after write_file tool calls and LLM request details
verbose = false
```

Please adjust *num_ctx* context size window according to your local computer ram. If your ollama gets crash, decrease this 65536 value to a proper context size.

| Option | Section | Default | Description |
|--------|---------|---------|-------------|
| `base_url` | `[llm]` | `http://localhost:11434/v1` | API endpoint. Works with any OpenAI-compatible server. |
| `api_key` | `[llm]` | `ollama` | API key. Set to `"ollama"` for local Ollama. |
| `model` | `[llm]` | `qwen3-coder:latest` | Model to use. Must be pulled in Ollama (`ollama list`). |
| `num_ctx` | `[llm]` | `65536` | Context window size in tokens. Larger values use more VRAM. |
| `editor` | `[editor]` | `vim` | Editor launched by `/task-edit` and `/edit` commands. |
| `verbose` | `[ui]` | `false` | When `true`, prints file contents after `write_file` and LLM request details before API calls. |
| `max_background_processes` | `[ui]` | `5` | Maximum number of concurrent background processes (1-20). |

## Usage

### Interactive Mode

```bash
# Start interactive chat
ayder

# Or run as a module
python -m ayder_cli
```

### Command Mode (Non-Interactive)

```bash
# Execute a single command and exit
ayder "create a hello.py script"

# Pipe input (auto-detected, no flag needed)
echo "create a test.py file" | ayder

# Read from file
ayder -f instructions.txt
ayder --file instructions.txt

# Explicit stdin mode
ayder --stdin < prompt.txt
```

### Task Commands (CLI Mode)

Execute task-related commands directly without entering interactive mode:

```bash
# List all tasks
ayder --tasks

# Implement a specific task by ID or name
ayder --implement 1
ayder --implement auth

# Implement all pending tasks sequentially
ayder --implement-all
```

### Tool Permissions (-r/-w/-x)

By default, every tool call requires user confirmation. Use permission flags to auto-approve tool categories:

| Flag | Category | Tools |
|------|----------|-------|
| `-r` | Read | `list_files`, `read_file`, `get_file_info`, `search_codebase`, `get_project_structure`, `load_memory`, `get_background_output`, `list_background_processes`, `list_tasks`, `show_task` |
| `-w` | Write | `write_file`, `replace_string`, `insert_line`, `delete_line`, `create_note`, `save_memory`, `create_task`, `implement_task`, `implement_all_tasks` |
| `-x` | Execute | `run_shell_command`, `run_background_process`, `kill_background_process` |

```bash
# Auto-approve read-only tools (no confirmations for file reading/searching)
ayder -r

# Auto-approve read and write tools
ayder -r -w

# Auto-approve everything (fully autonomous)
ayder -r -w -x

# Combine with other flags
ayder -r -w "refactor the login module"
echo "fix the bug" | ayder -r -w -x
```

### Agentic Iterations (-I)

The agent can make up to 50 consecutive tool calls per user message (default). Use `-I` to adjust:

```bash
# Allow up to 200 iterations for complex tasks
ayder -I 200

# Combine with permissions
ayder -r -w -I 150 "implement all pending tasks"
```

If you have memory problems decrease iteration size and /compact the LLM memory before it gets worse

### TUI Mode (Dashboard)

```bash
# Launch Textual TUI dashboard
ayder --tui
```

### Command Examples

```bash
# Quick code generation
ayder "write a fibonacci function in Python"

# Multi-line piped input
cat <<EOF | ayder
Read the README.md file and create a summary.
Save it to SUMMARY.md.
EOF

# Combine file input with additional command
ayder -f requirements.txt "install these dependencies and verify"

# Non-interactive automation
echo "run all tests and show results" | ayder
```

### Example session

```
╭─────────────────┬────────────────────────────────────────╮
│                 │                                        │
│  ░▒▓▓▓▒░        │ ayder-cli v0.7.0                       │
│       ▓▓        │ qwen3-coder:latest · Ollama            │
│  ▒▓▓▓▓▓▓        │ ~/projects/my-app                      │
│  ▓▓  ▓▓▓        │                                        │
│  ░▓▓▓▓▒█        │                                        │
╰─────────────────┴────────────────────────────────────────╯
 ? Tip: Use /help for available commands

❯ create a pyhon script to calculate prime numbers > 10000

Running...
File prime_calculator.py will be written. Proceed? (Y/n) Y
╭──────────────────────────────── Tool Result ─────────────────────────────────╮
│ Successfully wrote to prime_calculator.py                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
Command `python prime_calculator.py` will be executed. Proceed? (Y/n) Y
╭──────────────────────────────── Tool Result ─────────────────────────────────╮
│ Exit Code: 0                                                                 │
│ STDOUT:                                                                      │
│ Prime Number Calculator                                                      │
│ ==============================                                               │
│                                                                              │
│ First 10 prime numbers greater than 10000:                                   │
│  1. 10007                                                                    │
│  2. 10009                                                                    │
│  3. 10037                                                                    │
│  4. 10039                                                                    │
│  5. 10061                                                                    │
│  6. 10067                                                                    │
│  7. 10069                                                                    │
│  8. 10079                                                                    │
│  9. 10091                                                                    │
│ 10. 10093                                                                    │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

❯ List the python files in this project

╭───────────────────────── Tool Call ──────────────────────────────╮
│ run_shell_command({"command": "find . -name '*.py'"})            │
╰──────────────────────────────────────────────────────────────────╯
Proceed? [Y/n] y

╭──────────────────────── Tool Result ─────────────────────────────╮
│ ./prime_calculator.py                                            │
│ ./src/ayder_cli/client.py                                        │
│ ./src/ayder_cli/cli.py                                           │
│ ...                                                              │
╰──────────────────────────────────────────────────────────────────╯

╭──────────────────────── Assistant ───────────────────────────────╮
│ Here are the Python files in the project: ...                    │
╰──────────────────────────────────────────────────────────────────╯
```

### Operational Modes

ayder-cli has three operational modes, each with a specialized system prompt and tool set:

#### Default Mode
The standard mode for general coding and chat. Uses the **System Prompt**.

```
❯ create a fibonacci function
# AI writes code, runs tests, etc.
```

**Available tools:** File read/write, shell commands, search, view tasks.

#### Planning Mode (`/plan`)
Activated with `/plan`. Uses the **Planning Prompt**. The AI becomes a "Task Master" focused solely on breaking down requirements into tasks.

```
❯ /plan add a user authentication to the app

# The agent will analyze the codebase and create tasks...

╭──────────────────────── Tool Result ─────────────────────────────╮
│ Task TASK-001-add-auth-middleware.md created.                    │
╰──────────────────────────────────────────────────────────────────╯

```

**Available tools:** Read-only exploration + `create_task`.

#### Task Mode (`/task`)
Activated with `/task`. Uses the **Task Prompt**. The AI focuses on implementing tasks from the task list.

```

❯ /implement 1

╭────────────────────────── Running ───────────────────────────────╮
│ Running TASK-001: Add user authentication                        │
╰──────────────────────────────────────────────────────────────────╯

# AI implements the task, then marks it done
```

**Available tools:** Full file system access + task management tools.

**How it works:** Commands inject specialized prompts to guide the AI:
- `/plan` -- Injects Planning Prompt for task creation focus

### Task Management

ayder-cli includes a built-in task system for structured development:

1. **Plan** (`/plan`) -- Break down requirements into tasks
2. **Implement** (`/implement`) -- Work through tasks one by one

The typical workflow:

Tasks are stored as markdown files in `.ayder/tasks/` using slug-based filenames for readability (e.g., `TASK-001-add-auth-middleware.md`). Legacy `TASK-001.md` filenames are also supported.

```
❯ /tasks

╭──────────────────────── Tasks ───────────────────────────────────╮
│  Task ID  | Task Name                          | Status          │
│  ---------+------------------------------------+---------        │
│  TASK-001 | Add input validation to login form | pending         │
╰──────────────────────────────────────────────────────────────────╯

❯ /task-edit 1    # opens TASK-001-add-input-validation-to.md in your editor

❯ /implement 1

# AI implements TASK-001 and marks it as done

> /implement-all

# Sequentially implements all tasks one after each other. Consider iteration size!
...
```

### Code Search

ayder-cli provides code search capabilities:

```
❯ Search for all function definitions in Python files

╭───────────────────────── Tool Call ──────────────────────────────╮
│ search_codebase({"pattern": "^def ", "file_pattern": "*.py"})     │
╰──────────────────────────────────────────────────────────────────╯
Proceed? [Y/n] y

╭──────────────────────── Tool Result ─────────────────────────────╮
│ === SEARCH RESULTS ===                                           │
│ Pattern: "^def "                                                 │
│ Matches found: 42                                                │
│                                                                  │
│ ──────────────────────────────────────────────────────────────── │
│ FILE: src/ayder_cli/client.py                                    │
│ ──────────────────────────────────────────────────────────────── │
│ Line 45: def run_chat(openai_client=None, config=None):          │
│ Line 123: def handle_tool_call(tool_call, config):               │
│ ...                                                              │
╰──────────────────────────────────────────────────────────────────╯
```

### Project Structure

Quickly get an overview of your project:

```
❯ Show me the project structure

╭──────────────────────────────────── Assistant ────────────────────────────────────╮
│                                                                                   │
│  I've analyzed the project structure for you. The project has a standard Flask    │
│  application layout with:                                                         │
│                                                                                   │
│  - **app/** directory containing main application components                      │
│  - **models/** directory for database models and authentication                   │
│  - **templates/** directory for HTML templates                                    │
│  - **static/** directory for static files                                         │
│  - **tests/** directory for test files                                            │
│  - Configuration files like config.py and requirements.txt                        │
│  - Main application file app.py                                                   │
│                                                                                   │
│  The application appears to be a web application with user authentication         │
│  (jwt_auth.py, auth.py) and database interaction (database.py, user.py).          │
│                                                                                   │
│  Is there anything specific about this structure you'd like me to explore or      │
│  modify?                                                                          │
│                                                                                   │
╰───────────────────────────────────────────────────────────────────────────────────╯
```

### Editing files

You can open any file in your configured editor directly from the chat:

```
❯ /edit src/main.py    # opens the file in vim (or your configured editor)
```

### Slash commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/tools` | List all tools and their descriptions |
| `/plan` | Toggle Planning Mode (Task Master) for task creation |
| `/task` | Enter Task Mode for implementing tasks |
| `/tasks` | List saved tasks from `.ayder/tasks/` |
| `/task-edit N` | Open task N in your configured editor (e.g. `/task-edit 1`) |
| `/implement <id/name>` | Run a task by ID, name, or pattern (e.g. `/implement 1`) |
| `/implement-all` | Implement all undone tasks sequentially without stopping |
| `/edit <file>` | Open a file in your configured editor (e.g. `/edit src/main.py`) |
| `/verbose` | Toggle verbose mode (show file contents after `write_file` + LLM request details) |
| `/clear` | Clear conversation history and reset context |
| `/compact` | Summarize conversation, save to memory, clear, and reload context |
| `/summary` | Prompt AI to summarize conversation and save to `.ayder/current_memory.md` |
| `/load` | Prompt AI to load memory from `.ayder/current_memory.md` |
| `/undo` | Remove the last user message and assistant response |
| `exit` | Quit the application |

### Keyboard shortcuts

ayder-cli uses emacs-style keybindings via prompt-toolkit:

- **Ctrl+A / Ctrl+E** -- Jump to start / end of line
- **Ctrl+K** -- Delete to end of line
- **Ctrl+R** -- Reverse history search
- **Ctrl+C** -- Cancel current input
- **Ctrl+D** -- Exit

## Project structure

```
src/ayder_cli/
  cli.py           -- Command-line interface (argparse, --tui/--file/--stdin/--tasks/--implement/--implement-all flags, piped input)
  client.py        -- ChatSession + Agent classes, run_chat() entry point
  parser.py        -- XML tool call parser (standard + lazy format fallback)
  prompts.py       -- System prompts and prompt templates
  tasks.py         -- Task creation, listing, and implementation (.ayder/tasks/)
  notes.py         -- Note management (.ayder/notes/)
  memory.py        -- Cross-session memory storage (.ayder/memory/)
  process_manager.py -- Background process management (ProcessManager + 4 tool functions)
  ui.py            -- Rich terminal UI (boxes, message formatting, diff previews)
  tui.py           -- Textual TUI dashboard (chat view, context panel, modals)
  tui_helpers.py   -- TUI helper functions (safe mode checks)
  banner.py        -- Welcome banner with version detection and tips
  console.py       -- Centralized Rich console with custom theme
  commands/        -- Slash command handlers with decorator-based registry
    base.py        -- BaseCommand abstract class
    registry.py    -- Command registry and dispatch
    files.py       -- /edit command
    tools.py       -- /tools command
    tasks.py       -- /tasks, /task-edit, /implement, /implement-all commands
    system.py      -- /help, /clear, /compact, /summary, /load, /undo, /verbose, /plan commands
  core/            -- Core infrastructure
    config.py      -- Configuration loading with Pydantic validation
    context.py     -- ProjectContext for path sandboxing and security
    result.py      -- Shared result types (ToolSuccess, ToolError)
  services/        -- Service layer
    llm.py         -- OpenAI-compatible LLM provider
    tools/         -- ToolExecutor for tool confirmation and execution
  tools/           -- Modular tools package (19 tools)
    definition.py  -- ToolDefinition dataclass and registry
    impl.py        -- Tool implementations (file ops, line editing, file info, shell, search)
    schemas.py     -- OpenAI-format JSON schemas for all tools
    registry.py    -- ToolRegistry with middleware, callbacks, and execution timing
    utils.py       -- Tool utilities (content preparation for diffs)
```

## License

MIT
