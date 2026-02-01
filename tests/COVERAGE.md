# 📊 Test Coverage Report

<div align="center">

![Coverage](https://img.shields.io/badge/coverage-97%25-brightgreen)
![Tests](https://img.shields.io/badge/tests-207-blue)
![Python](https://img.shields.io/badge/python-3.12%2B-yellow)
![Status](https://img.shields.io/badge/status-passing-success)

**ayder-cli v0.1.0** · Generated on 2026-02-01

</div>

---

## 🖥️ Test Environment

<table>
<tr><td><b>Model</b></td><td><code>Qwen3 Coder 30B A3B Instruct</code></td></tr>
<tr><td><b>Architecture</b></td><td><code>qwen3moe</code></td></tr>
<tr><td><b>Quantization</b></td><td><code>Q4_K_M</code></td></tr>
<tr><td><b>Tensors</b></td><td>579</td></tr>
<tr><td><b>Key/Value Layers</b></td><td>35</td></tr>
<tr><td><b>Hardware</b></td><td>Apple M4 Max · 36 GB</td></tr>
<tr><td><b>OS</b></td><td>Tahoe 26.2</td></tr>
<tr><td><b>Version</b></td><td>ayder-cli 0.1.0</td></tr>
</table>

### Ollama Configuration

<details>
<summary><b>Click to expand environment variables</b></summary>

| Variable | Value |
|----------|-------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` |
| `OLLAMA_CONTEXT_LENGTH` | `4096` |
| `OLLAMA_DEBUG` | `INFO` |
| `OLLAMA_FLASH_ATTENTION` | `false` |
| `OLLAMA_GPU_OVERHEAD` | `0` |
| `OLLAMA_KEEP_ALIVE` | `5m0s` |
| `OLLAMA_LOAD_TIMEOUT` | `5m0s` |
| `OLLAMA_MAX_LOADED_MODELS` | `0` |
| `OLLAMA_MAX_QUEUE` | `512` |
| `OLLAMA_MODELS` | `/Users/sinanalyuruk/.ollama/models` |
| `OLLAMA_MULTIUSER_CACHE` | `false` |
| `OLLAMA_NEW_ENGINE` | `false` |
| `OLLAMA_NOHISTORY` | `false` |
| `OLLAMA_NOPRUNE` | `false` |
| `OLLAMA_NUM_PARALLEL` | `1` |
| `OLLAMA_SCHED_SPREAD` | `false` |

</details>

---

## 📈 Coverage Summary

```
Overall Coverage: 97% ████████████████████████████████████▓░
```

| Metric | Value |
|--------|-------|
| **Total Statements** | 585 |
| **Missing** | 15 |
| **Covered** | 570 |
| **Coverage** | **97%** ✅ |
| **Total Tests** | 207 |
| **Test Files** | 13 |

---

## 📋 Module Coverage Breakdown

### ✅ Excellent Coverage (≥95%)

| Module | Statements | Missed | Coverage | Status |
|--------|-----------|--------|----------|--------|
| `__init__.py` | 1 | 0 | **100%** | 🟢 |
| `parser.py` | 17 | 0 | **100%** | 🟢 |
| `config.py` | 27 | 0 | **100%** | 🟢 |
| `banner.py` | 36 | 0 | **100%** | 🟢 |
| `ui.py` | 82 | 0 | **100%** | 🟢 |
| `commands.py` | 93 | 0 | **100%** | 🟢 |
| `fs_tools.py` | 88 | 4 | **95%** | 🟢 |
| `tasks.py` | 138 | 3 | **98%** | 🟢 |

### 🟡 Good Coverage (90-94%)

| Module | Statements | Missed | Coverage | Status |
|--------|-----------|--------|----------|--------|
| `client.py` | 101 | 8 | **92%** | 🟡 |

### ⚪ Entry Point

| Module | Statements | Missed | Coverage | Status |
|--------|-----------|--------|----------|--------|
| `__main__.py` | 2 | 0 | **100%** | 🟢 |

---

## 🧪 Test Suite Overview

### Test Files (13 total)

```
tests/
├── __init__.py
├── test_agentic_workflow.py
├── test_banner.py          # 14 tests
├── test_client.py
├── test_client_v3.py
├── test_commands.py
├── test_config.py
├── test_fs_tools.py
├── test_interaction.py
├── test_interaction_v2.py
├── test_main.py            # 3 tests
├── test_tasks.py
└── test_ui.py
```

### Test Categories

| Category | Test Count | Description |
|----------|-----------|-------------|
| **File System Tools** | 40+ | `list_files`, `read_file`, `write_file`, `replace_string`, `run_shell_command` |
| **Configuration** | 15+ | Config loading, defaults, merging |
| **Task Management** | 35+ | Task creation, listing, implementation |
| **UI Components** | 30+ | Box drawing, message printing, tool descriptions |
| **Commands** | 40+ | Slash commands (`/help`, `/tools`, `/tasks`, `/edit`, etc.) |
| **Client/Integration** | 25+ | Chat loop, tool execution, OpenAI client mocking |
| **Banner** | 14 | Welcome banner, tips, formatting |
| **Parser** | 8 | Message parsing utilities |

---

## 🔍 Notable Coverage Details

### 100% Coverage Modules

<details>
<summary><b>config.py — 100% (27/27)</b></summary>

- ✅ `load_config()` first run
- ✅ `load_config()` existing config
- ✅ Default values verification
- ✅ Config merging

</details>

<details>
<summary><b>banner.py — 100% (36/36)</b></summary>

- ✅ `print_welcome_banner()` output format
- ✅ Home directory path tilde replacement
- ✅ Random tip selection
- ✅ Banner styling

</details>

<details>
<summary><b>ui.py — 100% (82/82)</b></summary>

- ✅ `draw_box()` with various inputs
- ✅ Message print functions
- ✅ `describe_tool_action()` for all tools
- ✅ `confirm_tool_call()` with different responses

</details>

<details>
<summary><b>commands.py — 100% (93/93)</b></summary>

- ✅ `/help`, `/tools`, `/tasks` commands
- ✅ `/task-edit` with valid/invalid IDs
- ✅ `/edit` command with file paths
- ✅ `/verbose` toggle
- ✅ `/clear` and `/undo` commands

</details>

### Near-Complete Coverage

<details>
<summary><b>fs_tools.py — 95% (84/88)</b></summary>

| Function | Coverage |
|----------|----------|
| `list_files()` | ✅ 100% |
| `read_file()` | ✅ 100% |
| `write_file()` | ✅ 100% |
| `replace_string()` | ✅ 100% |
| `run_shell_command()` | ✅ 100% |
| `execute_tool_call()` | ✅ 100% |

*Missing: 4 defensive exception handlers*

</details>

<details>
<summary><b>tasks.py — 98% (135/138)</b></summary>

| Function | Coverage |
|----------|----------|
| `_ensure_tasks_dir()` | ✅ 100% |
| `_extract_id()` | ✅ 100% |
| `_next_id()` | ✅ 100% |
| `create_task()` | ✅ 100% |
| `_parse_status()` | ✅ 100% |
| `_parse_title()` | ✅ 100% |
| `list_tasks()` | ✅ 100% |
| `show_task()` | ✅ 100% |
| `_update_task_status()` | ✅ 100% |
| `implement_task()` | ✅ 100% |
| `implement_all_tasks()` | ✅ 100% |

*Missing: 3 defensive exception handlers*

</details>

<details>
<summary><b>client.py — 92% (93/101)</b></summary>

| Component | Coverage |
|-----------|----------|
| Exit command handling | ✅ 100% |
| Empty input handling | ✅ 100% |
| KeyboardInterrupt handling | ✅ 100% |
| Slash command routing | ✅ 100% |
| Tool execution flow | ✅ 100% |
| Verbose mode | ✅ 100% |
| `TERMINAL_TOOLS` constant | ✅ 100% |
| `SYSTEM_PROMPT` | ✅ 100% |

*Missing: Main loop continuation paths and module guard*

</details>

---

## 🎯 Coverage Goals

| Goal | Target | Achieved | Status |
|------|--------|----------|--------|
| Overall Coverage | 80%+ | **97%** | ✅ Exceeded |
| Core Modules | 90%+ | **95-100%** | ✅ Met |
| UI Components | 90%+ | **100%** | ✅ Exceeded |
| Test Count | 100+ | **207** | ✅ Exceeded |

---

## 🚀 Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest --cov=src/ayder_cli --cov-report=term tests/

# Generate HTML coverage report
pytest --cov=src/ayder_cli --cov-report=html tests/

# Watch mode during development
pytest tests/ -v -f
```

---

## 📝 Notes

- All tests use mocking to avoid external dependencies
- File system tests use `tmp_path` fixture for isolation
- OpenAI client is fully mocked for integration tests
- Tests are deterministic and fast (< 5 seconds total)
- Edge cases and error paths are extensively covered

---

<div align="center">

**Made with ❤️ using Qwen3 Coder 30B A3B**

*Report generated by ayder-cli test suite*

</div>
