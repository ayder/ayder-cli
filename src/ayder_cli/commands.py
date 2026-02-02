import subprocess
from pathlib import Path
from ayder_cli import fs_tools
from ayder_cli.tasks import list_tasks, _get_tasks_dir
from ayder_cli.ui import draw_box
from ayder_cli.config import load_config


# Command registry
COMMANDS = {}


def register_command(name):
    """Decorator to register a command handler."""
    def decorator(func):
        COMMANDS[name] = func
        return func
    return decorator


@register_command("/help")
def cmd_help(args, session):
    """Display help information for all available commands.

    Args:
        args: Command arguments (unused)
        session: Session dict containing messages, system_prompt, state
            (Will be updated to ChatSession object in TASK-013)
    """
    help_text = """
Available Commands:
  /tools          - List all available tools and their descriptions
  /tasks          - List all saved tasks
  /task-edit N    - Edit task N in your configured editor
  /edit <file>    - Open a file in your configured editor
  /verbose        - Toggle verbose mode (show written file contents)
  /clear          - Clear conversation history and reset context
  /undo           - Remove the last user message and assistant response
  /help           - Show this help message
  exit            - Quit the application
"""
    print(draw_box(help_text, title="Help", width=80, color_code="33"))
    return True


@register_command("/tools")
def cmd_tools(args, session):
    """List all available tools and their descriptions.

    Args:
        args: Command arguments (unused)
        session: Session dict containing messages, system_prompt, state
    """
    tools_info = ""
    for tool in fs_tools.tools_schema:
        func = tool.get('function', {})
        name = func.get('name', 'Unknown')
        desc = func.get('description', 'No description provided.')
        tools_info += f"• {name}: {desc}\n"

    print(draw_box(tools_info.strip(), title="Available Tools", width=80, color_code="35"))
    return True


@register_command("/tasks")
def cmd_tasks(args, session):
    """List all saved tasks.

    Args:
        args: Command arguments (unused)
        session: Session dict containing messages, system_prompt, state
    """
    result = list_tasks()
    print(draw_box(result, title="Tasks", width=80, color_code="35"))
    return True


@register_command("/task-edit")
def cmd_task_edit(args, session):
    """Edit a task file in the configured editor.

    Args:
        args: Task ID to edit
        session: Session dict containing messages, system_prompt, state
    """
    if not args:
        print(draw_box("Usage: /task-edit <task_id>\nExample: /task-edit 1", title="Error", width=80, color_code="31"))
        return True

    try:
        task_id = int(args.strip())
    except ValueError:
        print(draw_box(f"Invalid task ID: {args.strip()}\nTask ID must be a number.", title="Error", width=80, color_code="31"))
        return True

    task_path = _get_tasks_dir() / f"TASK-{task_id:03d}.md"
    if not task_path.exists():
        print(draw_box(f"Task TASK-{task_id:03d} not found.", title="Error", width=80, color_code="31"))
        return True

    # Get editor from config
    cfg = load_config()
    editor = cfg.editor

    # Open editor
    try:
        subprocess.run([editor, str(task_path)], check=True)
        print(draw_box(f"Task TASK-{task_id:03d} edited successfully.", title="Success", width=80, color_code="32"))
    except subprocess.CalledProcessError:
        print(draw_box(f"Error opening editor: {editor}", title="Error", width=80, color_code="31"))
    except FileNotFoundError:
        print(draw_box(f"Editor not found: {editor}\nUpdate your config at ~/.ayder/config.toml", title="Error", width=80, color_code="31"))

    return True


@register_command("/edit")
def cmd_edit(args, session):
    """Open a file in the configured editor.

    Args:
        args: File path to edit
        session: Session dict containing messages, system_prompt, state
    """
    if not args:
        print(draw_box("Usage: /edit <file_path>\nExample: /edit src/main.py", title="Error", width=80, color_code="31"))
        return True

    file_path = Path(args.strip())
    if not file_path.exists():
        print(draw_box(f"File not found: {file_path}", title="Error", width=80, color_code="31"))
        return True

    cfg = load_config()
    editor = cfg.editor

    try:
        subprocess.run([editor, str(file_path)], check=True)
        print(draw_box(f"Finished editing {file_path}", title="Success", width=80, color_code="32"))
    except subprocess.CalledProcessError:
        print(draw_box(f"Error opening editor: {editor}", title="Error", width=80, color_code="31"))
    except FileNotFoundError:
        print(draw_box(f"Editor not found: {editor}\nUpdate your config at ~/.ayder/config.toml", title="Error", width=80, color_code="31"))

    return True


@register_command("/verbose")
def cmd_verbose(args, session):
    """Toggle verbose mode.

    Args:
        args: Command arguments (unused)
        session: Session dict containing messages, system_prompt, state
    """
    state = session.get("state")
    if state is not None:
        state["verbose"] = not state["verbose"]
        status = "ON" if state["verbose"] else "OFF"
        print(draw_box(f"Verbose mode: {status}", title="System", width=80, color_code="32"))
    else:
        print(draw_box("Verbose mode is not available.", title="Error", width=80, color_code="31"))
    return True


@register_command("/clear")
def cmd_clear(args, session):
    """Clear conversation history and reset context.

    Args:
        args: Command arguments (unused)
        session: Session dict containing messages, system_prompt, state
    """
    messages = session.get("messages")
    system_prompt = session.get("system_prompt")
    messages.clear()
    messages.append({"role": "system", "content": system_prompt})
    print(draw_box("Conversation history cleared.", title="System", width=80, color_code="32"))
    return True


@register_command("/undo")
def cmd_undo(args, session):
    """Remove the last user message and assistant response.

    Args:
        args: Command arguments (unused)
        session: Session dict containing messages, system_prompt, state
    """
    messages = session.get("messages")
    # Find the last user message to revert to
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get('role') == 'user':
            last_user_idx = i
            break

    if last_user_idx > 0:  # Ensure we don't delete system prompt (idx 0)
        del messages[last_user_idx:]
        print(draw_box("Undid last interaction.", title="System", width=80, color_code="32"))
    else:
        print(draw_box("Nothing to undo.", title="System", width=80, color_code="33"))
    return True


def handle_command(cmd, messages, system_prompt, state=None):
    """Handle slash commands. Returns True if command was handled, False if unknown.

    Note: This function maintains backwards compatibility by accepting separate
    parameters (messages, system_prompt, state). These are bundled into a session
    dict for command handlers. In TASK-013, this will be updated to use a unified
    ChatSession object.
    """
    # Extract command name (lowercased) and keep raw args for case-sensitive paths
    parts = cmd.split(None, 1)
    cmd_name = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""

    # Create session dict for command handlers
    # (Will be replaced with ChatSession object in TASK-013)
    session = {
        "messages": messages,
        "system_prompt": system_prompt,
        "state": state
    }

    # Look up command in registry
    if cmd_name in COMMANDS:
        handler = COMMANDS[cmd_name]
        return handler(cmd_args, session)
    else:
        print(draw_box(f"Unknown command: {cmd}", title="Error", width=80, color_code="31"))
        return True
