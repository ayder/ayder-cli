# ayder-cli

An interactive AI agent chat client for local LLMs. It connects to a locally running [Ollama](https://ollama.com) instance and provides an autonomous coding assistant with file system tools and shell access, all from your terminal.

## Why ayder-cli?

Most AI coding assistants require cloud APIs, subscriptions, or heavy IDE plugins. There are many cli coding agents there doing amazing things if you have tokens and subscriptions. ayder-cli takes a different approach:

- **Fully local** -- runs against Ollama on your machine. While you do not depend on a AI provider, your code never leaves your computer.
- **Agentic workflow** -- the LLM doesn't just answer questions. It can read files, edit code, run shell commands, and iterate on its own, up to 5 consecutive tool calls per user message.
- **Minimal dependencies** -- just the OpenAI SDK (for Ollama's compatible API) and prompt-toolkit for terminal input. No frameworks, no bloat.


### Why fs_tools?

LLMs on their own can only generate text. To be a useful coding assistant, the model needs to *act* on your codebase. I find it very hard to properly configure other coding agents to work with local qwen3:coder so I come up with a  `fs_tools` bridge -- it gives the model a set of real tools it can call (not limited with) :


| Tool | What it does |
|------|-------------|
| `list_files` | List files in a directory |
| `read_file` | Read a file (supports line ranges for large files) |
| `write_file` | Write content to a file |
| `replace_string` | Find and replace a specific string in a file |
| `run_shell_command` | Execute a shell command (60s timeout) |
| `create_task` | Save a task as a markdown file in `.ayder/tasks/` (current directory) |
| `show_task` | Show the details of a task by its ID number |
| `implement_task` | Mark a specific task as done and return its details |
| `implement_all_tasks` | Process all pending tasks and mark them as done |

Each tool has an OpenAI-compatible JSON schema so models that support function calling can use them natively. For models that don't, ayder-cli also parses a custom XML-like syntax (`<function=name><parameter=key>value</parameter></function>`) as a fallback.

**WARNING**: No sandboxing provided in this early technology previev version.
This cli do not have a --yolo-its-too-dangerous method as well. **it allows all shell commands to be executed**
Every tool call requires your confirmation before it runs -- you must always stay in control.
Also you may prefer to run ayder-cli agent in a container for additional security.

Of course I am greateful to GEMINI to come up with this idea, KIMI2 for reasoning tasks and CLAUDE and COPILOT to do coding and testing for me. 

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

```bash
# Start the chat
ayder

# Or run as a module
python -m ayder_cli
```

### Example session

```
╭──────────────────┬────────────────────────────────────────╮
│                  │                                        │
│  ░▒▓▓▓▒░        │ ayder-cli v0.1.0                       │
│       ▓▓        │ qwen3-coder:latest · Ollama            │
│  ▒▓▓▓▓▓▓        │ ~/projects/my-app                      │
│  ▓▓  ▓▓▓        │                                        │
│  ░▓▓▓▓▒█        │                                        │
╰──────────────────┴────────────────────────────────────────╯
 ? Tip: Use /help for available commands

❯ List the python files in this project

╭───────────────────────── Tool Call ──────────────────────────────╮
│ run_shell_command({"command": "find . -name '*.py'"})            │
╰──────────────────────────────────────────────────────────────────╯
Proceed? [Y/n] y

╭──────────────────────── Tool Result ─────────────────────────────╮
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
  client.py     -- Main chat loop and agentic execution loop
  fs_tools.py   -- Tool implementations, JSON schemas, and dispatcher
  ui.py         -- Terminal UI (ANSI box drawing, message formatting, confirmation prompts)
  parser.py     -- Custom XML-like tool call parser (fallback for models without function calling)
  commands.py   -- Slash command handler (/help, /tools, /clear, /undo, /tasks, /task-edit, /edit, /verbose)
  config.py     -- Config loading from ~/.ayder/config.toml
  tasks.py      -- Task creation, listing, and implementation (markdown files in .ayder/tasks/)
  banner.py     -- Welcome banner with gothic art and random tips
```

## License

MIT
