# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ayder-cli is an interactive AI agent chat client for local LLMs. It connects to an Ollama instance running `qwen3-coder:latest` and provides an autonomous coding assistant with file system tools and shell access. Built with Python 3.12+, using the OpenAI SDK (for Ollama compatibility) and prompt-toolkit for terminal UI.

## Commands

```bash
# Install in development mode
pip install -e .

# Run the CLI
ayder
python -m ayder_cli

# Run tests (requires Ollama running locally)
python tests/test_interaction.py
python tests/test_interaction_v2.py
python tests/test_agentic_workflow.py
python tests/test_client_v3.py
```

There is no formal test framework (pytest), linter, or CI configured. Tests are standalone scripts that communicate directly with Ollama — no mocking.

## Architecture

The entire application is two modules:

- **`src/ayder_cli/client.py`** — Main chat loop and terminal UI. Handles user input via prompt-toolkit (emacs keybindings, persistent history at `~/.ayder_chat_history`), slash commands (`/help`, `/tools`, `/clear`, `/undo`), and the agentic loop that allows up to 5 consecutive tool calls per user message.

- **`src/ayder_cli/fs_tools.py`** — Tool implementations (`list_files`, `read_file`, `write_file`, `replace_string`, `run_shell_command`) plus their OpenAI-format JSON schemas in `tools_schema` and a dispatcher `execute_tool_call()`.

Entry point: `ayder_cli.client:run_chat` (registered as the `ayder` CLI script in pyproject.toml).

## Key Design Details

- **Dual tool calling**: Supports both standard OpenAI function calling (`msg.tool_calls`) and a custom XML-like fallback parsed by `parse_custom_tool_calls()` using `<function=name><parameter=key>value</parameter></function>` syntax. Standard calls feed results back as `tool` role messages; custom calls feed results back as `user` role messages.

- **Shell command timeout**: `run_shell_command` has a 60-second timeout.

