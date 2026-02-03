# ayder-cli

An interactive AI agent chat client for local LLMs. It connects to a locally running [Ollama](https://ollama.com) instance and provides an autonomous coding assistant with file system tools and shell access, all from your terminal.

## Why ayder-cli?

Most AI coding assistants require cloud APIs, subscriptions, or heavy IDE plugins. There are many cli coding agents there doing amazing things if you have tokens and subscriptions. ayder-cli takes a different approach:

- **Fully local** -- runs against Ollama on your machine. While you do not depend on a AI provider, your code never leaves your computer.
- **Agentic workflow** -- the LLM doesn't just answer questions. It can read files, edit code, run shell commands, and iterate on its own, up to 5 consecutive tool calls per user message.
- **Two interfaces** -- a classic prompt-toolkit CLI and an optional Textual TUI dashboard with chat view, context panel, and tool confirmation modals.
- **Minimal dependencies** -- OpenAI SDK (for Ollama's compatible API), prompt-toolkit, Rich, and Textual. No frameworks, no bloat.


### Why fs_tools?

LLMs on their own can only generate text. To be a useful coding assistant, the model needs to *act* on your codebase. I find it very hard to properly configure other coding agents to work with local qwen3:coder so I come up with a  `fs_tools` bridge -- it gives the model a set of real tools it can call (not limited with) :


| Tool | What it does |
|------|-------------|
| `list_files` | List files in a directory |
| `read_file` | Read a file (supports line ranges for large files) |
| `write_file` | Write content to a file |
| `replace_string` | Find and replace a specific string in a file |
| `run_shell_command` | Execute a shell command (60s timeout) |
| `search_codebase` | Search for patterns across the codebase using ripgrep/grep |
| `get_project_structure` | Generate a tree-style project structure summary |
| `create_task` | Save a task as a markdown file in `.ayder/tasks/` (current directory) |
| `show_task` | Show the details of a task by its ID number |
| `implement_task` | Mark a specific task as done and return its details |
| `implement_all_tasks` | Process all pending tasks and mark them as done |

Each tool has an OpenAI-compatible JSON schema so models that support function calling can use them natively. For models that don't, ayder-cli also parses a custom XML-like syntax (`<function=name><parameter=key>value</parameter></function>`) as a fallback.

  - **Path sandboxing**: All file operations are confined to the project root via `ProjectContext`. Path traversal attacks (`../`) and absolute paths outside the project are blocked.
  - **Safe mode** (TUI): The Textual TUI supports a safe mode that blocks `write_file`, `replace_string`, and `run_shell_command`.
  - Every tool call requires your confirmation before it runs -- you always stay in control.
  - You may also prefer to run ayder-cli in a container for additional security.

Of course I am grateful to GEMINI to come up with this idea, KIMI2 for reasoning tasks and CLAUDE and COPILOT to do coding and testing for me. 

## Installation

Requires Python 3.12+ and a running Ollama instance.

```bash
# Clone the repo
git clone https://github.com/ayder/ayder-cli.git
cd ayder-cli

# Install in development mode
pip install -e .

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
# Show written file contents after write_file tool calls
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
| `verbose` | `[ui]` | `false` | When `true`, prints file contents after each `write_file` call. |

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
╭──────────────────┬────────────────────────────────────────╮
│                  │                                        │
│  ░▒▓▓▓▒░        │ ayder-cli v0.7.0                       │
│       ▓▓        │ qwen3-coder:latest · Ollama            │
│  ▒▓▓▓▓▓▓        │ ~/projects/my-app                      │
│  ▓▓  ▓▓▓        │                                        │
│  ░▓▓▓▓▒█        │                                        │
╰──────────────────┴────────────────────────────────────────╯
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
│ ./src/ayder_cli/fs_tools.py                                      │
│ ...                                                              │
╰──────────────────────────────────────────────────────────────────╯

╭──────────────────────── Assistant ───────────────────────────────╮
│ Here are the Python files in the project: ...                    │
╰──────────────────────────────────────────────────────────────────╯
```

### Task management

ayder-cli includes a built-in task system. Ask the model to create tasks, then manage them with slash commands or let the model implement them.

```
❯ Create a task to add input validation to the login form

╭───────────────────────── Tool Call ──────────────────────────────╮
│ create_task({"title": "Add input validation to login form",      │
│   "description": "Validate email format and password length..."})│
╰──────────────────────────────────────────────────────────────────╯
Proceed? [Y/n] y

╭──────────────────────── Tool Result ─────────────────────────────╮
│ Task TASK-001 created.                                           │
╰──────────────────────────────────────────────────────────────────╯

❯ /tasks

╭──────────────────────── Tasks ───────────────────────────────────╮
│  Task ID  | Task Name                          | Status          │
│  ---------+------------------------------------+---------        │
│  TASK-001 | Add input validation to login form  | pending         │
╰──────────────────────────────────────────────────────────────────╯

❯ /task-edit 1    # opens TASK-001.md in your configured editor

❯ Implement task 1

╭───────────────────────── Tool Call ──────────────────────────────╮
│ implement_task({"task_id": 1})                                   │
╰──────────────────────────────────────────────────────────────────╯
Proceed? [Y/n] y
...
```

Tasks are stored as markdown files in `.ayder/tasks/` within the current working directory.

### Code Search

ayder-cli provides powerful code search capabilities:

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

╭───────────────────────── Tool Call ──────────────────────────────╮
│ get_project_structure({"max_depth": 3})                          │
╰──────────────────────────────────────────────────────────────────╯
Proceed? [Y/n] y

╭──────────────────────── Tool Result ─────────────────────────────╮
│ ayder-cli                                                        │
│ ├── src/                                                         │
│ │   └── ayder_cli/                                               │
│ │       ├── client.py                                            │
│ │       ├── commands.py                                          │
│ │       ├── config.py                                            │
│ │       ├── fs_tools.py                                          │
│ │       ├── parser.py                                            │
│ │       ├── tasks.py                                             │
│ │       ├── ui.py                                                │
│ │       └── tools/                                               │
│ │           ├── impl.py                                          │
│ │           ├── schemas.py                                       │
│ │           └── registry.py                                      │
│ ├── tests/                                                       │
│ └── README.md                                                    │
╰──────────────────────────────────────────────────────────────────╯
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
| `/tasks` | List saved tasks from `.ayder/tasks/` |
| `/task-edit N` | Open task N in your configured editor (e.g. `/task-edit 1`) |
| `/edit <file>` | Open a file in your configured editor (e.g. `/edit src/main.py`) |
| `/verbose` | Toggle verbose mode (show written file contents after `write_file`) |
| `/clear` | Clear conversation history and reset context |
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
  cli.py           -- Command-line interface (argparse, --tui/--file/--stdin flags, piped input auto-detection)
  client.py        -- ChatSession + Agent classes, run_chat() entry point
  commands.py      -- Slash command handler with decorator-based registry
  config.py        -- Configuration loading with Pydantic validation
  fs_tools.py      -- Backwards compatibility layer (re-exports from tools/)
  ui.py            -- Rich terminal UI (boxes, message formatting, diff previews)
  tui.py           -- Textual TUI dashboard (chat view, context panel, modals)
  tui_helpers.py   -- TUI helper functions (safe mode checks)
  parser.py        -- XML tool call parser (standard + lazy format fallback)
  prompts.py       -- System prompts and prompt templates
  tasks.py         -- Task creation, listing, and implementation (.ayder/tasks/)
  banner.py        -- Welcome banner with version detection and tips
  console.py       -- Centralized Rich console with custom theme
  path_context.py  -- ProjectContext for path sandboxing and security
  tools/           -- Modular tools package
    impl.py        -- Tool implementations (file ops, shell, search)
    schemas.py     -- OpenAI-format JSON schemas for all 10 tools
    registry.py    -- ToolRegistry with middleware, callbacks, and execution timing
    utils.py       -- Tool utilities (content preparation for diffs)
```

## Recent Changes (v0.7.0)

### CLI Enhancements
- **Command Mode**: Execute single commands non-interactively: `ayder "create file.py"`
- **Piped Input Auto-Detection**: Unix-style piping works without flags: `echo "text" | ayder`
- **File Input**: Read instructions from files: `ayder -f instructions.txt`
- **Multiple Entry Points**: CLI (`cli:main`), programmatic (`client:run_chat`), TUI (`tui.py`)
- **Improved Exit Codes**: Command mode returns proper exit codes (0=success, 1=error, 2=no response)

### Testing Infrastructure
- **pytest Plugins**: Added xdist (parallel), timeout (hang prevention), instafail (fast feedback), sugar (progress bar)
- **38 CLI Tests**: Comprehensive coverage for file/stdin input, piped input auto-detection, TUI flag handling
- **464+ Total Tests**: 96% code coverage across all modules

### Previous Changes (v0.6.0)

### Textual TUI Dashboard
- **Interactive TUI**: New `tui.py` module provides a full Textual-based dashboard with chat view, context panel (model info, token usage, file tree), input bar, and keyboard shortcuts (Ctrl+Q, Ctrl+C, Ctrl+L).
- **Tool confirmation modals**: `ConfirmActionScreen` with inline diff previews for file-modifying tools. `SafeModeBlockScreen` for blocked operations.
- **Safe mode**: Blocks destructive tools (`write_file`, `replace_string`, `run_shell_command`) via registry middleware.
- **Async LLM calls**: `call_llm_async()` runs synchronous OpenAI calls in a thread pool so the TUI stays responsive.

### Path Security & Sandboxing
- **`ProjectContext`**: New `path_context.py` module sandboxes all file operations to the project root. Blocks path traversal (`../`), validates absolute paths, and handles tilde expansion.
- **Propagated at startup**: `set_project_context_for_modules()` in `client.py` pushes the context to all tool modules (`impl.py`, `utils.py`, `registry.py`, `tasks.py`).

### ChatSession & Agent Architecture
- **`ChatSession` class**: Manages conversation state, prompt-toolkit input, message history, and welcome banner display. Replaces the inline logic that was previously in `run_chat()`.
- **`Agent` class**: Handles the agentic loop (up to 5 consecutive tool calls), tool validation, diff preview for file-modifying tools, and both standard OpenAI and custom XML-parsed tool calls.
- **`run_chat()` preserved**: Still the entry point, now accepts `project_root` parameter in addition to `openai_client` and `config`.

### Enhanced Tool Registry
- **Middleware support**: `ToolRegistry.add_middleware()` for pre-execution checks (used by TUI safe mode).
- **Callbacks**: Pre/post-execute callbacks with `ToolExecutionResult` (includes timing, status, error details).
- **`ToolExecutionStatus`/`ToolExecutionResult`**: Structured result objects for execution tracking.

### Enhanced Parser
- **Lazy format**: Single-param tools can now use `<function=name>value</function>` without explicit `<parameter>` tags. Parameter name is inferred via `_infer_parameter_name()`.
- **Error reporting**: Malformed tool calls return `{"error": "message"}` objects instead of silently failing.

### Test Coverage
- **464 tests** (up from 243), **96% coverage** across all modules.
- New test files: `test_parser.py`, `tools/test_path_security.py`, and coverage-focused test files for `client.py`, `tools/impl.py`, `tools/registry.py`, `ui.py`, `config.py`, `tools/utils.py`.

### Other Improvements
- **Rich console** (`console.py`): Centralized console instance with custom theme and 20+ file extension syntax mappings.
- **Welcome banner** (`banner.py`): Version detection via `importlib.metadata`, gothic ASCII art, and random tips.
- **Pydantic config validation**: Field validators for `base_url` (http/https) and `num_ctx` (positive integer).
- **Modular tools package**: `fs_tools.py` is now a thin re-export layer; all logic lives in `tools/`.

## License

MIT
