# Documentation Moved

The documentation for this project has been reorganized into two main files:

## 📋 [AGENTS.md](AGENTS.md) - Start Here

**Coding standards, workflows, and task running**

- Tech Stack
- Project Structure Overview
- Running Commands (poe, uv run, manual)
- Python Coding Standards
- Linting with Ruff
- Type Checking with Mypy
- Testing with pytest
- Pre-Commit Checklist
- Quick Reference Commands

## 🏗️ [.ayder/PROJECT_STRUCTURE.md](.ayder/PROJECT_STRUCTURE.md) - Architecture

**Detailed architecture, module relationships, and code navigation**

- Architecture Overview (layered diagram)
- Entry Points (cli.py, __main__.py, console script)
- Module Map (all modules with purposes)
- TUI Architecture (components, data flow, callbacks)
- Import Paths (patterns, conventions, circular import avoidance)

---

**Quick Start:**
```bash
# Install dependencies
/opt/homebrew/bin/uv pip install -e ".[dev]"

# Run all checks
uv run poe check-all

# Or run tests only
uv run poe test
```
