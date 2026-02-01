import subprocess
from pathlib import Path
from ayder_cli import fs_tools
from ayder_cli.tasks import list_tasks, TASKS_DIR
from ayder_cli.ui import draw_box
from ayder_cli.config import load_config


def handle_command(cmd, messages, system_prompt, state=None):
    """Handle slash commands. Returns True if command was handled, False if unknown."""
    # Extract command name (lowercased) and keep raw args for case-sensitive paths
    parts = cmd.split(None, 1)
    cmd_name = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd_name == '/help':
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

    elif cmd_name == '/tools':
        tools_info = ""
        for tool in fs_tools.tools_schema:
            func = tool.get('function', {})
            name = func.get('name', 'Unknown')
            desc = func.get('description', 'No description provided.')
            tools_info += f"• {name}: {desc}\n"

        print(draw_box(tools_info.strip(), title="Available Tools", width=80, color_code="35"))
        return True

    elif cmd_name == '/tasks':
        result = list_tasks()
        print(draw_box(result, title="Tasks", width=80, color_code="35"))
        return True

    elif cmd_name == '/task-edit':
        if not cmd_args:
            print(draw_box("Usage: /task-edit <task_id>\nExample: /task-edit 1", title="Error", width=80, color_code="31"))
            return True

        try:
            task_id = int(cmd_args.strip())
        except ValueError:
            print(draw_box(f"Invalid task ID: {cmd_args.strip()}\nTask ID must be a number.", title="Error", width=80, color_code="31"))
            return True

        task_path = Path(TASKS_DIR) / f"TASK-{task_id:03d}.md"
        if not task_path.exists():
            print(draw_box(f"Task TASK-{task_id:03d} not found.", title="Error", width=80, color_code="31"))
            return True
        
        # Get editor from config
        cfg = load_config()
        editor = cfg.get("editor", "vim")
        
        # Open editor
        try:
            subprocess.run([editor, str(task_path)], check=True)
            print(draw_box(f"Task TASK-{task_id:03d} edited successfully.", title="Success", width=80, color_code="32"))
        except subprocess.CalledProcessError:
            print(draw_box(f"Error opening editor: {editor}", title="Error", width=80, color_code="31"))
        except FileNotFoundError:
            print(draw_box(f"Editor not found: {editor}\nUpdate your config at ~/.ayder/config.toml", title="Error", width=80, color_code="31"))
        
        return True

    elif cmd_name == '/edit':
        if not cmd_args:
            print(draw_box("Usage: /edit <file_path>\nExample: /edit src/main.py", title="Error", width=80, color_code="31"))
            return True

        file_path = Path(cmd_args.strip())
        if not file_path.exists():
            print(draw_box(f"File not found: {file_path}", title="Error", width=80, color_code="31"))
            return True

        cfg = load_config()
        editor = cfg.get("editor", "vim")

        try:
            subprocess.run([editor, str(file_path)], check=True)
            print(draw_box(f"Finished editing {file_path}", title="Success", width=80, color_code="32"))
        except subprocess.CalledProcessError:
            print(draw_box(f"Error opening editor: {editor}", title="Error", width=80, color_code="31"))
        except FileNotFoundError:
            print(draw_box(f"Editor not found: {editor}\nUpdate your config at ~/.ayder/config.toml", title="Error", width=80, color_code="31"))

        return True

    elif cmd_name == '/verbose':
        if state is not None:
            state["verbose"] = not state["verbose"]
            status = "ON" if state["verbose"] else "OFF"
            print(draw_box(f"Verbose mode: {status}", title="System", width=80, color_code="32"))
        else:
            print(draw_box("Verbose mode is not available.", title="Error", width=80, color_code="31"))
        return True

    elif cmd_name == '/clear':
        messages.clear()
        messages.append({"role": "system", "content": system_prompt})
        print(draw_box("Conversation history cleared.", title="System", width=80, color_code="32"))
        return True

    elif cmd_name == '/undo':
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

    else:
        print(draw_box(f"Unknown command: {cmd}", title="Error", width=80, color_code="31"))
        return True
