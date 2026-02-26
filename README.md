# ayder-cli

A multi-provider AI agent chat client for your terminal. Currently ayder supports
or any OpenAI-compatible API and provides an autonomous coding assistant with file system tools and shell access.

![ayder](docs/cc.png)

## Supported LLM providers

- [Ollama](https://ollama.com)
- [Anthropic Claude](https://www.anthropic.com)
- [OpenAI](https://openai.com/)
- [Gemini](https://gemini.google.com/)

## Why ayder-cli?

Most AI coding assistants require cloud APIs, subscriptions, or heavy IDE plugins. There are many cli coding agents there doing amazing things if you have tokens and subscriptions. ayder-cli takes a different approach:

- **Multi-provider** -- switch between Ollama (local/cloud), Anthropic Claude, Gemini or any OpenAI-compatible API with a single `/provider` command. Each provider has its own config section.
- **Fully local or cloud** -- run locally with Ollama (on your machine), or connect to Gemini, Anthropic, OpenAI, or cloud-hosted Ollama.
- **Agentic workflow** -- the LLM doesn't just answer questions. It can read files, edit code, run shell commands, and iterate on its own for configurable consecutive tool calls per user message (configurable with `-I`).
- **Textual TUI** -- a full dashboard interface with chat view, tool panel, slash command auto-completion, permission toggles, and tool confirmation modals with diff previews.
- **Minimal dependencies** -- OpenAI SDK, Rich, and Textual. Gemini genai and for Gemini and Anthropic SDK optional for native  support.

### Tested Providers with Models

| Provider | Location | Model                              |
| -------- | -------- | ---------------------------------- |
| ollama   | Cloud    | deepseek-v3.2:cloud                |
| ollama   | Cloud    | gemini-3-pro-preview:latest        |
| ollama   | Local    | glm-4.7-flash:latest               |
| ollama   | Cloud    | glm-4.7:cloud                      |
| ollama   | Cloud    | glm-5:cloud                        |
| ollama   | Local    | glm-ocr:latest                     |
| ollama   | Cloud    | gpt-oss:120b-cloud                 |
| ollama   | Cloud    | kimi-k2.5:cloud                    |
| ollama   | Cloud    | minimax-m2.5:cloud                 |
| ollama   | Local    | ministral-3:14b                    |
| ollama   | Cloud    | qwen3-coder-next:cloud             |
| ollama   | Cloud    | qwen3-coder:480b-cloud             |
| ollama   | Local    | qwen3-coder:latest                 |
| anthropic| Cloud    | claude-opus-4-6                    |
| anthropic| Cloud    | claude-sonnet-4-5-20250929         |
| anthropic| Cloud    | claude-haiku-4-5-20251001          |
| openai   | Cloud    | GPT-5.3-Codex                      |
| openai   | Cloud    | GPT-5.3-Codex-Spark                |
| openai   | Cloud    | GPT-5.2                            |
| openai   | Cloud    | GPT-5                              |
| gemini   | Cloud    | gemini-3-deep-think                |
| gemini   | Cloud    | gemini-3-pro                       |
| gemini   | Cloud    | gemini-3-flash                     |

### Tools

LLMs on their own can only generate text. To be a useful coding assistant, the model needs to *act* on your codebase. ayder-cli provides a modular `tools/` package that gives the model a set of real tools it can call:
Each tool has an OpenAI-compatible JSON schema so models that support function calling can use them natively. For models that don't, ayder-cli also parses a custom XML-like syntax (`<function=name><parameter=key>value</parameter></function>`) as a fallback.

- **Path sandboxing**: All file operations are confined to the project root via `ProjectContext`. Path traversal attacks (`../`) and absolute paths outside the project are blocked.
- **Safe mode** (TUI): The TUI supports a safe mode that blocks `write_file`, `replace_string`, `insert_line`, `delete_line`, `run_shell_command`, `run_background_process`, and `kill_background_process`.
- Every tool call requires your confirmation before it runs -- you always stay in control. Use `-r`, `-w`, `-x` flags to auto-approve tool categories.
- You may also prefer to run ayder-cli in a container for additional security.

## Installation

Requires Python 3.12+.
Works best with uv tool. if you don't have uv in your path get it from
 [Astral uv](https://docs.astral.sh/uv/#highlights)

```bash
# Install it to user environemnt

uv tool install ayder-cli

# or if no uv then create a a virtual environment first,
# activate it and install from PYPI

pip install ayder-cli

# For the nightly-builds:

# Clone the repo
git clone https://github.com/ayder/ayder-cli.git
cd ayder-cli

# Install in development mode
python3.12 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install uv 

uv pip install -e .

# or (6 times slower)
pip install -e .

# Or works best as a uv tool (always on the path)
uv tool install -e .
```

### Ollama setup (default provider)

```bash
# Make sure Ollama is running with a model
ollama pull qwen3-coder
ollama serve

# Optional: optimize ollama for your model
export OLLAMA_CONTEXT_LENGTH=65536
export OLLAMA_FLASH_ATTENTION=true
export OLLAMA_MAX_LOADED_MODELS=1
```

### Anthropic setup (optional)

```bash
# Install the Anthropic SDK
pip install anthropic

# Set your API key in ~/.ayder/config.toml (see Configuration below)
# Then switch provider:
#   /provider anthropic
```

### Gemini setup (optional)

```bash
# Install the Google Generative AI SDK
pip install google-generativeai
```

Set your API key in ~/.ayder/config.toml
Then switch provider:
   /provider gemini

### Configuration

On first run, ayder-cli creates a config file at `~/.ayder/config.toml` with the v2.0 format:

```toml
config_version = "2.0"

[app]
provider = "openai"
editor = "vim"
verbose = false
max_background_processes = 5
max_iterations = 50

[logging]
file_enabled = true
file_path = ".ayder/log/ayder.log"
rotation = "10 MB"
retention = "7 days"

[temporal]
enabled = false
host = "localhost:7233"
namespace = "default"
metadata_dir = ".ayder/temporal"

[temporal.timeouts]
workflow_schedule_to_close_seconds = 7200
activity_start_to_close_seconds = 900
activity_heartbeat_seconds = 30

[temporal.retry]
initial_interval_seconds = 5
backoff_coefficient = 2.0
maximum_interval_seconds = 60
maximum_attempts = 3

[llm.openai]
driver = "openai"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
model = "qwen3-coder:latest"
num_ctx = 65536

[llm.anthropic]
driver = "anthropic"
api_key = ""
model = "claude-sonnet-4-5-20250929"
num_ctx = 8192

[llm.gemini]
driver = "google"
api_key = ""
model = "gemini-3-flash"
num_ctx = 65536

[llm.deepseek]
driver = "openai"
base_url = "http://api.deepseek.com/v1"
api_key = ""
model = "deepseek-chat"
```

The active provider is selected via `app.provider`. Provider settings are defined in `[llm.<provider>]` sections. Use `/provider` in the TUI to switch at runtime, or edit `config.toml` directly.

Please adjust *num_ctx* context size window according to your local computer ram. If your ollama gets crash, decrease this 65536 value to a proper context size.

### Config Options Reference

| Option | Section | Default | Description |
| ------ |-------- | ------- | ----------- |
| `config_version` | top-level | `2.0` | Config format version. |
| `provider` | `[app]` | `openai` | Active provider profile name. |
| `editor` | `[app]` | `vim` | Editor launched by `/task-edit` command. |
| `verbose` | `[app]` | `false` | When `true`, prints file contents after `write_file` and LLM request details. |
| `max_background_processes` | `[app]` | `5` | Maximum concurrent background processes (1-20). |
| `max_iterations` | `[app]` | `50` | Maximum agentic iterations per user message (1-100). |
| `file_enabled` | `[logging]` | `true` | Enable file logging sink. |
| `file_path` | `[logging]` | `.ayder/log/ayder.log` | Log file destination. |
| `rotation` | `[logging]` | `10 MB` | Log rotation size. |
| `retention` | `[logging]` | `7 days` | Log retention period. |
| `enabled` | `[temporal]` | `false` | Enable Temporal workflow integration. |
| `host` | `[temporal]` | `localhost:7233` | Temporal server address. |
| `namespace` | `[temporal]` | `default` | Temporal namespace. |
| `driver` | `[llm.<provider>]` | varies | Driver: `openai`, `anthropic`, or `google`. |
| `base_url` | `[llm.<provider>]` | varies | API endpoint (OpenAI-compatible). |
| `api_key` | `[llm.<provider>]` | varies | API key. Use `"ollama"` for local Ollama. |
| `model` | `[llm.<provider>]` | varies | Model name to use. |
| `num_ctx` | `[llm.<provider>]` | varies | Context window size in tokens. |

## Usage

```bash
# Start (launches TUI by default)
ayder

# Or run as a module
python3 -m ayder_cli

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

# Use a custom system prompt file
ayder --prompt prompt-file.md "refactor this code"
ayder -f code.py --prompt system-prompt.md "analyze this file"
```

### Task Commands (CLI Mode)

Execute task-related commands directly without entering the TUI:

```bash
# List all tasks
ayder --tasks

# Implement a specific task by ID or name
ayder --implement 1
ayder --implement auth

# Implement all pending tasks sequentially
ayder --implement-all
```

### Tool Permissions (-r/-w/-x/--http)

By default, every tool call requires user confirmation. Use permission flags to auto-approve tool categories:

| Flag | Category | Tools |
| ---- | -------- | ----- |
| `-r` | Read | `list_files`, `read_file`, `get_file_info`, `search_codebase`, `get_project_structure`, `load_memory`, `get_background_output`, `list_background_processes`, `list_tasks`, `show_task` |
| `-w` | Write | `write_file`, `replace_string`, `insert_line`, `delete_line`, `create_note`, `save_memory`, `manage_environment_vars`, `create_task`, `implement_task`, `implement_all_tasks` |
| `-x` | Execute | `run_shell_command`, `run_background_process`, `kill_background_process` |
| `--http` | Web/Network | `fetch_web` |

```bash
# Auto-approve read-only tools (no confirmations for file reading/searching)
ayder -r

# Auto-approve read and write tools
ayder -r -w

# Auto-approve everything (fully autonomous)
ayder -r -w -x

# Allow web fetch tool without prompts
ayder -r --http

# Combine with other flags
ayder -r -w "refactor the login module"
echo "fix the bug" | ayder -r -w -x
```

### Memory Management & Iteration Control

The agent can perform multiple consecutive tool calls per user message. However, as the conversation grows, LLM performance can degrade due to **context bloat** (context rot).

To solve this, `ayder` features an intelligent memory management system that summarizes conversation history based on a configurable iteration threshold.

#### Adjusting Iteration Threshold

You can tune how often the agent "compresses" its memory using the `-I` (Iteration) flag.

- **Small Models:** Use a lower value (e.g., `-I 50`) to keep the context lean and avoid logic errors.
- **Large/Powerful Models:** Use a higher value (e.g., `-I 200`) to maximize the model's reasoning capabilities before summarization.

#### Transferring Memory Between Models

If you switch models or providers mid-session, you can carry over your "knowledge" by manually triggering the memory system:

1. **Save current state:** `/save-memory`
2. **Switch provider or model:** `/provider anthropic` or `/model qwen3-coder:480b-cloud`
3. **Restore context:** `/load-memory`

```bash
# Allow up to 200 iterations for complex tasks
ayder -I 200

# Combine with permissions
ayder -r -w -I 150 "implement all pending tasks"
```

If you have memory problems decrease iteration size and /compact the LLM memory before it gets worse.

### Slash Commands

| Command | Description |
| ------- | ----------- |
| `/help` | Show available commands and keyboard shortcuts |
| `/tools` | List all tools and their descriptions |
| `/provider` | Switch LLM provider (openai, anthropic, gemini) with interactive selector |
| `/model` | List available models or switch model (e.g. `/model qwen2.5-coder`) |
| `/ask` | Ask a general question without using tools (e.g. `/ask explain REST vs GraphQL`) |
| `/plan` | Analyze request and create implementation tasks |
| `/tasks` | Browse and implement tasks from `.ayder/tasks/` |
| `/task-edit N` | Open task N in an in-app editor (e.g. `/task-edit 1`) |
| `/implement [id]` | Interactive task picker, or implement by ID (e.g. `/implement 1`) |
| `/verbose` | Toggle verbose mode (show file contents after `write_file` + LLM request details) |
| `/logging` | Set Loguru level for current TUI session (`NONE`, `ERROR`, `WARNING`, `INFO`, `DEBUG`) |
| `/compact` | Summarize conversation, save to memory, clear, and reload context |
| `/save-memory` | Summarize conversation and save to `.ayder/memory/current_memory.md` (no clear) |
| `/load-memory` | Load memory from `.ayder/memory/current_memory.md` and restore context |
| `/archive-completed-tasks` | Move completed tasks to `.ayder/task_archive/` |
| `/permission` | Toggle permission levels (r/w/x/http) interactively |
| `exit` | Quit the application |

### Logging

- Default behavior: when logging is enabled (`/logging` or `logging.level`), logs are written to `.ayder/log/ayder.log` (not shown on screen).
- TUI `/logging` changes are session-only and do not modify `config.toml`.
- CLI `--verbose [LEVEL]` is the explicit opt-in for stdout logging during that run (default level is `INFO` when omitted).

### Keyboard Shortcuts

| Shortcut | Action |
| -------- | ------ |
| `Ctrl+D` | Quit |
| `Ctrl+X` / `Ctrl+C` | Cancel current operation |
| `Ctrl+L` | Clear chat |
| `Tab` | Auto-complete slash commands |
| `Up/Down` | Navigate command history |

### Operational Modes

ayder-cli has three operational modes, each with a specialized system prompt and tool set:

#### Default Mode

The standard mode for general coding and chat. Uses the **System Prompt**.
> create a fibonacci function
>
#### AI writes code, runs tests, et.

## Available tools: File read/write, shell commands, search, view tasks.

### Planning Mode (`/plan`)

Activated with `/plan`. Uses the **Planning Prompt**. The AI becomes a "Task Master" focused solely on breaking down requirements into tasks.

> /plan add a user authentication to the app
>
#### The agent will analyze the codebase and create tasks...

**Available tools:** Read-only exploration + `create_task`.

#### Task Mode (`/implement`)

Activated with `/implement`. Uses the **Task Prompt**. The AI focuses on implementing tasks from the task list. Without arguments, shows an interactive task picker.

> /implement
>
Opens interactive task selector — pick a task to implement

> /implement 1
>
Running TASK-001: Add user authentication

AI implements the task, then marks it done


**Available tools:** Full file system access + task management tools.

### Task Management

ayder-cli includes a built-in task system for structured development:

1. **Plan** (`/plan`) -- Break down requirements into tasks
2. **Implement** (`/implement`) -- Work through tasks one by one

Tasks are stored as markdown files in `.ayder/tasks/` using slug-based filenames for readability (e.g., `TASK-001-add-auth-middleware.md`). Legacy `TASK-001.md` filenames are also supported.

> /tasks
>
Opens interactive task selector — pick a task to implement

> /task-edit 1    # opens TASK-001 in the in-app editor

> /implement
>
Opens interactive task selector — pick a task to implement

> /implement 1
>
AI implements TASK-001 and marks it as done

### Code Search

ayder-cli provides code search capabilities via the `search_codebase` tool. The LLM calls it automatically when you ask it to search for patterns, function definitions, or usages across the codebase.

### Web Fetch Tool

`fetch_web` retrieves URL content using async `httpx` and supports `GET` (default), `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, and `OPTIONS`.

- Requires `http` permission (`--http` in CLI or `/permission` in TUI).
- Session cookies are persisted across `fetch_web` calls within the same ayder process.

### Pluggable Tool Architecture

ayder-cli features a **pluggable tool system** with dynamic auto-discovery. Adding a new tool is as simple as:

1. **Create a definition file**: `src/ayder_cli/tools/mytool_definitions.py`
2. **Implement the tool function**: Add your logic
3. **Done!** Auto-discovery automatically registers the tool

The tool system automatically:

- Discovers all `*_definitions.py` files
- Validates for duplicates and required tools
- Registers tools with the LLM
- Handles imports and exports

Current tool categories (28 tools total):

- **Filesystem**: list_files, read_file, write_file, replace_string, insert_line, delete_line, get_file_info
- **Search**: search_codebase, get_project_structure
- **Shell**: run_shell_command
- **Python Editor**: python_editor (CST-based structural code manipulation: get, list_all, replace, delete, rename, add_decorator, add_import, verify)
- **Memory**: save_memory, load_memory
- **Notes**: create_note
- **Background Processes**: run_background_process, get_background_output, kill_background_process, list_background_processes
- **Tasks**: list_tasks, show_task
- **Environment**: manage_environment_vars
- **Virtual Environments**: create_virtualenv, install_requirements, list_virtualenvs, activate_virtualenv, remove_virtualenv
- **Web**: fetch_web
- **Workflow**: temporal_workflow

## License

MIT
