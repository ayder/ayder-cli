# Tool Development Guide

This guide explains how to register a new tool in **ayder-cli**. The tool system uses a schema-driven, centralized definition pattern with clear separation of concerns.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Detailed Steps](#detailed-steps)
- [ToolDefinition Reference](#tooldefinition-reference)
- [Best Practices](#best-practices)
- [Example: Complete Tool Implementation](#example-complete-tool-implementation)

---

## Architecture Overview

The tools package follows a modular architecture:

```
src/ayder_cli/tools/
├── definition.py   # Source of truth: ToolDefinition dataclasses
├── schemas.py      # Auto-generated OpenAI schemas from definitions
├── registry.py     # ToolRegistry: execution, middleware, callbacks
├── impl.py         # Actual tool implementations
├── utils.py        # Helper utilities
└── __init__.py     # Public API exports
```

### Data Flow

1. **Define** → `ToolDefinition` in `definition.py`
2. **Generate** → `tools_schema` auto-generated for OpenAI API
3. **Implement** → Function in `impl.py`
4. **Register** → Added to `create_default_registry()` in `registry.py`
5. **Export** → Added to `__all__` in `__init__.py`

---

## Quick Start

To add a new tool, you need to modify **4 files**:

| File | Change |
|------|--------|
| `src/ayder_cli/tools/definition.py` | Add `ToolDefinition` to `TOOL_DEFINITIONS` |
| `src/ayder_cli/tools/impl.py` | Implement the tool function |
| `src/ayder_cli/tools/registry.py` | Register in `create_default_registry()` |
| `src/ayder_cli/tools/__init__.py` | Export in `__all__` |

---

## Detailed Steps

### Step 1: Define the Tool in `definition.py`

Add a new `ToolDefinition` to the `TOOL_DEFINITIONS` tuple. This is the **single source of truth** for all tool metadata.

```python
TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    # ... existing tools ...
    
    ToolDefinition(
        name="my_tool",
        description="Brief description of what the tool does",
        description_template="Action {param} will be performed",  # UI display
        parameters={
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "Description of this parameter",
                },
            },
            "required": ["param"],
        },
        permission="r",  # "r", "w", or "x"
        is_terminal=False,
        safe_mode_blocked=False,
        exposed_to_llm=True,
        parameter_aliases=(),
        path_parameters=(),
    ),
)
```

#### ToolDefinition Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Unique identifier for the tool |
| `description` | `str` | Description sent to the LLM |
| `parameters` | `dict` | OpenAI function parameters schema |
| `permission` | `str` | `"r"` (read), `"w"` (write), or `"x"` (execute) |
| `is_terminal` | `bool` | If `True`, ends the agentic loop after execution |
| `safe_mode_blocked` | `bool` | If `True`, blocked when safe mode is enabled |
| `exposed_to_llm` | `bool` | If `False`, hidden from LLM (internal use only) |
| `description_template` | `str` | Template for UI confirmation dialogs |
| `parameter_aliases` | `tuple` | Map alternate param names to canonical names |
| `path_parameters` | `tuple` | Param names auto-validated via `ProjectContext` |

#### Parameter Aliases

Use aliases to support different parameter naming conventions:

```python
parameter_aliases=(
    ("path", "file_path"),      # path → file_path
    ("filepath", "file_path"),  # filepath → file_path
    ("dir", "directory"),       # dir → directory
)
```

#### Path Parameters

Parameters listed here are automatically:
- Validated against path traversal attacks
- Resolved to absolute paths via `ProjectContext`
- Sandboxed to the project root

```python
path_parameters=("file_path", "directory")
```

---

### Step 2: Implement the Tool in `impl.py`

Create the implementation function. All tools receive `project_ctx: ProjectContext` as the first parameter.

```python
def my_tool(project_ctx: ProjectContext, param: str) -> str:
    """
    Implementation of my_tool.
    
    Args:
        project_ctx: Project context for path validation and sandboxing
        param: The parameter description
    
    Returns:
        ToolSuccess or ToolError result
    """
    try:
        # If using paths, validate them first
        # abs_path = project_ctx.validate_path(file_path)
        
        # Your implementation logic here
        result = f"Processed: {param}"
        
        return ToolSuccess(result)
        
    except ValueError as e:
        # Path validation errors (security)
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        # General execution errors
        return ToolError(f"Error: {str(e)}", "execution")
```

#### Return Types

Import from `ayder_cli.core.result`:

```python
from ayder_cli.core.result import ToolSuccess, ToolError
```

- `ToolSuccess(content: str)` → Successful execution
- `ToolError(message: str, category: str)` → Failed execution
  - `category` can be `"security"`, `"validation"`, or `"execution"`

#### Path Security

Always validate paths through `ProjectContext`:

```python
abs_path = project_ctx.validate_path(user_provided_path)
# Returns absolute Path object or raises ValueError for traversal attempts
```

Convert back to relative for display:

```python
rel_path = project_ctx.to_relative(abs_path)
```

---

### Step 3: Register in `registry.py`

Add your tool to `create_default_registry()`:

```python
def create_default_registry(project_ctx: ProjectContext) -> ToolRegistry:
    from ayder_cli.tools.impl import (
        # ... existing imports ...
        my_tool,  # Add your import
    )
    
    registry = ToolRegistry(project_ctx)
    
    # ... existing registrations ...
    registry.register("my_tool", my_tool)  # Register your tool
    
    return registry
```

---

### Step 4: Export in `__init__.py`

Add to the public API:

```python
from ayder_cli.tools.impl import (
    # ... existing imports ...
    my_tool,  # Add your import
)

__all__ = [
    # ... existing exports ...
    "my_tool",  # Add to __all__
]
```

---

## ToolDefinition Reference

### Permission Categories

| Permission | Meaning | Example Tools |
|------------|---------|---------------|
| `"r"` | Read-only operations | `read_file`, `list_files`, `search_codebase` |
| `"w"` | Write/modify operations | `write_file`, `replace_string` |
| `"x"` | Execute operations | `run_shell_command` |

### Terminal Tools

Set `is_terminal=True` for tools that should end the agentic loop:

- Task management tools (`create_task`, `implement_task`)
- Tools that complete a user request

### Safe Mode Blocking

Set `safe_mode_blocked=True` for dangerous operations:

- `write_file` - Can overwrite files
- `replace_string` - Can modify files
- `run_shell_command` - Can execute arbitrary commands

When safe mode is enabled, these tools are blocked with a permission error.

---

## Best Practices

### 1. Always Validate Paths

```python
# Good
try:
    abs_path = project_ctx.validate_path(file_path)
except ValueError as e:
    return ToolError(f"Security Error: {str(e)}", "security")

# Bad - never use raw paths
data = open(file_path).read()  # Security risk!
```

### 2. Handle Exceptions Gracefully

```python
try:
    result = some_operation()
    return ToolSuccess(result)
except ValueError as e:
    return ToolError(f"Security Error: {str(e)}", "security")
except FileNotFoundError:
    return ToolError(f"File not found: {rel_path}", "execution")
except Exception as e:
    return ToolError(f"Error: {str(e)}", "execution")
```

### 3. Use Appropriate Error Categories

- `"security"` - Path traversal, permission denied
- `"validation"` - Missing parameters, invalid arguments
- `"execution"` - Runtime errors, file not found, etc.

### 4. Define Clear Descriptions

The `description` field is sent to the LLM. Make it clear and actionable:

```python
# Good
description=(
    "Search for a regex pattern across the codebase. "
    "Returns matching lines with file paths and line numbers. "
    "Use this to locate code before reading files."
)

# Bad
description="Search tool"
```

### 5. Use Description Templates

Templates appear in confirmation dialogs:

```python
description_template="File {file_path} will be written"
# Displays: "File src/main.py will be written"
```

---

## Example: Complete Tool Implementation

Here's a complete example implementing a `count_lines` tool:

### 1. `definition.py`

```python
ToolDefinition(
    name="count_lines",
    description="Count the number of lines in a file",
    description_template="Lines in {file_path} will be counted",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to count lines in",
            },
        },
        "required": ["file_path"],
    },
    permission="r",
    parameter_aliases=(
        ("path", "file_path"),
        ("filepath", "file_path"),
    ),
    path_parameters=("file_path",),
),
```

### 2. `impl.py`

```python
def count_lines(project_ctx: ProjectContext, file_path: str) -> str:
    """Count lines in a file."""
    try:
        abs_path = project_ctx.validate_path(file_path)
        
        if not abs_path.exists():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: File '{rel_path}' does not exist.")
        
        if not abs_path.is_file():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: '{rel_path}' is not a file.")
        
        with open(abs_path, 'r', encoding='utf-8') as f:
            line_count = sum(1 for _ in f)
        
        rel_path = project_ctx.to_relative(abs_path)
        return ToolSuccess(f"{rel_path}: {line_count} lines")
        
    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error counting lines: {str(e)}", "execution")
```

### 3. `registry.py`

```python
from ayder_cli.tools.impl import (
    # ... existing imports ...
    count_lines,
)

def create_default_registry(project_ctx: ProjectContext) -> ToolRegistry:
    registry = ToolRegistry(project_ctx)
    
    # ... existing registrations ...
    registry.register("count_lines", count_lines)
    
    return registry
```

### 4. `__init__.py`

```python
from ayder_cli.tools.impl import (
    # ... existing imports ...
    count_lines,
)

__all__ = [
    # ... existing exports ...
    "count_lines",
]
```

---

## Testing Your Tool

After implementing, test your tool:

```python
# Quick test via Python
PYTHONPATH=src python3 -c "
from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.registry import create_default_registry

ctx = ProjectContext('.')
registry = create_default_registry(ctx)
result = registry.execute('count_lines', {'file_path': 'README.md'})
print(result)
"
```

Add proper tests in `tests/tools/` following the existing patterns.

---

# Slash Command Development Guide

This guide explains how to register a new `/slash` command in **ayder-cli**. Slash commands are user-facing CLI commands that start with `/` (e.g., `/help`, `/clear`).

## Table of Contents

- [Architecture Overview](#slash-command-architecture-overview)
- [Quick Start](#slash-command-quick-start)
- [Detailed Steps](#slash-command-detailed-steps)
- [SessionContext Reference](#sessioncontext-reference)
- [Example: Complete Command Implementation](#example-complete-command-implementation)

---

## Slash Command Architecture Overview

The commands package follows a class-based registry pattern:

```
src/ayder_cli/commands/
├── base.py       # BaseCommand abstract class
├── registry.py   # CommandRegistry and @register_command decorator
├── __init__.py   # handle_command entry point and module imports
├── system.py     # System commands: /help, /clear, /verbose
├── tools.py      # Tool commands: /tools
├── tasks.py      # Task commands: /tasks, /task-edit
└── files.py      # File commands: /edit
```

### Data Flow

1. **User types** → `/command args`
2. **Dispatcher** → `handle_command()` in `__init__.py`
3. **Lookup** → `CommandRegistry` finds command by name
4. **Execute** → `command.execute(args, session)`

---

## Slash Command Quick Start

To add a new slash command, you need to modify **1 file** (or create a new one):

| File | Change |
|------|--------|
| `src/ayder_cli/commands/*.py` | Create command class with `@register_command` decorator |

If creating a new module, also add the import to `src/ayder_cli/commands/__init__.py`.

---

## Slash Command Detailed Steps

### Step 1: Create the Command Class

Commands are classes that inherit from `BaseCommand` and use the `@register_command` decorator:

```python
from ayder_cli.core.context import SessionContext
from ayder_cli.ui import draw_box
from .base import BaseCommand
from .registry import register_command

@register_command
class MyCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/mycommand"
        
    @property
    def description(self) -> str:
        return "Description shown in /help"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        # args: string after the command (e.g., "/mycommand arg1 arg2")
        # session: SessionContext with config, project, messages, state
        
        draw_box(f"Executed with args: {args}", title="MyCommand", width=80)
        return True
```

#### BaseCommand Interface

| Property/Method | Description |
|-----------------|-------------|
| `name` | The command name including `/` (e.g., `/help`) |
| `description` | Short description for the `/help` listing |
| `execute(args, session)` | Execute the command, return `True` if handled |

#### SessionContext

The `session` object provides access to:

```python
@dataclass
class SessionContext:
    config: Config              # Configuration settings
    project: ProjectContext     # Path validation and sandboxing
    messages: list              # Chat message history
    state: dict                 # Runtime state (verbose mode, etc.)
```

Access examples:

```python
def execute(self, args: str, session: SessionContext) -> bool:
    # Access configuration
    model = session.config.model
    
    # Access project context for path operations
    abs_path = session.project.validate_path("src/main.py")
    
    # Access/modify message history
    session.messages.append({"role": "user", "content": "Hello"})
    
    # Access/modify runtime state
    current = session.state.get("my_key", False)
    session.state["my_key"] = not current
    
    return True
```

---

### Step 2: Register the Command Module

If you created a new file (e.g., `mycommands.py`), add it to `__init__.py`:

```python
# src/ayder_cli/commands/__init__.py

# Import modules to register commands
from . import system, tools, tasks, files, mycommands  # Add your module
```

Commands are auto-registered when the module is imported due to the `@register_command` decorator.

---

## SessionContext Reference

### Config Object

```python
session.config.model           # LLM model name
session.config.base_url        # API base URL
session.config.num_ctx         # Context window size
session.config.temperature     # Temperature setting
```

### ProjectContext Object

```python
# Validate and resolve paths
abs_path = session.project.validate_path("src/main.py")

# Convert to relative for display
rel_path = session.project.to_relative(abs_path)

# Access project root
root = session.project.root
```

### Messages List

The conversation history as OpenAI-format messages:

```python
# Clear all messages except system prompt
if session.messages[0].get("role") == "system":
    system_msg = session.messages[0]
    session.messages.clear()
    session.messages.append(system_msg)
else:
    session.messages.clear()
```

### State Dictionary

Runtime state for the session:

```python
# Toggle verbose mode
session.state["verbose"] = not session.state.get("verbose", False)

# Store custom state
session.state["my_custom_key"] = some_value
```

---

## Example: Complete Command Implementation

Here's a complete example implementing a `/timestamp` command that displays the current time:

### `src/ayder_cli/commands/system.py` (or new file)

```python
from datetime import datetime
from ayder_cli.core.context import SessionContext
from ayder_cli.ui import draw_box
from .base import BaseCommand
from .registry import register_command

@register_command
class TimestampCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/timestamp"
        
    @property
    def description(self) -> str:
        return "Display the current timestamp"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        """Execute the timestamp command."""
        # Parse optional format argument
        fmt = args.strip() if args else "%Y-%m-%d %H:%M:%S"
        
        try:
            now = datetime.now().strftime(fmt)
            draw_box(f"Current time: {now}", title="Timestamp", width=80, color_code="36")
        except ValueError as e:
            draw_box(f"Invalid format: {e}", title="Error", width=80, color_code="31")
            
        return True
```

### Usage in Chat

```
You: /timestamp
╭────────────────────────── Timestamp ───────────────────────────╮
│ Current time: 2024-01-15 14:30:45                              │
╰────────────────────────────────────────────────────────────────╯

You: /timestamp %H:%M
╭────────────────────────── Timestamp ───────────────────────────╮
│ Current time: 14:30                                            │
╰────────────────────────────────────────────────────────────────╯
```

### Appears in /help

```
You: /help
╭─────────────────────────── Help ───────────────────────────────╮
│ Available Commands:                                            │
│   /clear          - Clear conversation history and reset context│
│   /help           - Show this help message                     │
│   /timestamp      - Display the current timestamp              │
│   /tools          - List all available tools and their descriptions│
│   /verbose        - Toggle verbose mode                        │
╰────────────────────────────────────────────────────────────────╯
```

---

## Best Practices for Slash Commands

### 1. Use draw_box for Output

```python
from ayder_cli.ui import draw_box

# Good
draw_box("Operation completed", title="Success", width=80, color_code="32")

# color_code values: "31"=red, "32"=green, "33"=yellow, "34"=blue, "35"=magenta, "36"=cyan
```

### 2. Handle Empty Args Gracefully

```python
def execute(self, args: str, session: SessionContext) -> bool:
    if not args.strip():
        draw_box("Usage: /mycommand <arg>", title="Error", width=80, color_code="31")
        return True
    # ... process args
```

### 3. Return True Even on Errors

Returning `True` prevents the CLI from showing an additional "Unknown command" error:

```python
def execute(self, args: str, session: SessionContext) -> bool:
    try:
        # ... do something
        return True
    except Exception as e:
        draw_box(f"Error: {e}", title="Error", width=80, color_code="31")
        return True  # Still return True - command was recognized
```

### 4. Use Path Validation for File Operations

```python
def execute(self, args: str, session: SessionContext) -> bool:
    file_path = args.strip()
    try:
        abs_path = session.project.validate_path(file_path)
        # ... work with abs_path
    except ValueError as e:
        draw_box(f"Security Error: {e}", title="Error", width=80, color_code="31")
    return True
```

### 5. Keep Descriptions Concise

```python
# Good
description = "Clear conversation history and reset context"

# Bad - too long
description = "This command clears the conversation history and resets the context to the initial state"
```

---

## Testing Your Command

After implementing, test your command:

```python
# Quick test via Python
PYTHONPATH=src python3 -c "
from ayder_cli.commands import handle_command
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext, SessionContext

# Create session context
config = Config()
project = ProjectContext('.')
session = SessionContext(config=config, project=project, messages=[], state={})

# Test the command
handle_command('/timestamp', session)
"
```

Or run the CLI and test interactively:

```bash
.venv/bin/python3 -m ayder_cli
# Then type: /timestamp
```
