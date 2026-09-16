# ayder-cli 2.3.1

- Added a local messaging inbox for peer prompts, optional `--name`, `/rename`, and session names derived from resume IDs.
- Built MCP into the standard agent toolset, using `.ayder/mcp.json` with shared connections and automatic handling of legacy plugin installations.
- Added `/effort` for OpenAI and Ollama, configurable LLM/agent defaults, and effort display immediately after the model name in the status bar.
- Kept the TUI responsive during long reasoning streams by buffering thinking-panel updates.
- Fixed Ollama parallel tool-call IDs, required-argument aliases, and validation of unexpected tool arguments.
- Added tool-call metadata tracing before validation and warnings for conflicting call IDs.
- Clarified full-file writes and enforced the file editor's 10 MB UTF-8 content limit before modifying files.
