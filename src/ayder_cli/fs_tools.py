import os
import json
import subprocess
from ayder_cli.tasks import create_task, show_task, implement_task, implement_all_tasks

# --- 1. Tool Implementations ---

def list_files(directory="."):
    """Lists files in the specified directory."""
    try:
        files = os.listdir(directory)
        return json.dumps(files)
    except Exception as e:
        return f"Error listing files: {str(e)}"

def read_file(file_path, start_line=None, end_line=None):
    """
    Reads the content of a file. 
    Can optionally read a specific range of lines (1-based indices).
    """
    try:
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Handle line filtering
        if start_line is not None or end_line is not None:
            # Default to beginning/end if one is missing
            start = int(start_line) if start_line else 1
            end = int(end_line) if end_line else len(lines)
            
            # Adjust to 0-based index
            start_idx = max(0, start - 1)
            end_idx = min(len(lines), end)
            
            selected_lines = lines[start_idx:end_idx]
            
            # Add line numbers for context
            content_with_lines = ""
            for i, line in enumerate(selected_lines):
                content_with_lines += f"{start + i}: {line}"
            
            return content_with_lines
        else:
            return "".join(lines)
            
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(file_path, content):
    """Writes content to a file (overwrites entire file)."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def replace_string(file_path, old_string, new_string):
    """Replaces a specific string in a file with a new string."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if old_string not in content:
            return f"Error: 'old_string' not found in {file_path}. No changes made."
        
        new_content = content.replace(old_string, new_string)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        return f"Successfully replaced text in {file_path}"
    except Exception as e:
        return f"Error replacing text: {str(e)}"

def run_shell_command(command):
    """Executes a shell command and returns the output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = f"Exit Code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
            
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except Exception as e:
        return f"Error executing command: {str(e)}"

# --- 2. Tool Definitions (JSON Schema) ---

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "The directory path (default: '.')"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file, optionally specifying a line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "The path to the file to read"},
                    "start_line": {"type": "integer", "description": "The line number to start reading from (1-based)."},
                    "end_line": {"type": "integer", "description": "The line number to stop reading at (1-based)."}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (overwrites entire file).",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "The path to the file to write"},
                    "content": {"type": "string", "description": "The content to write"}
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_string",
            "description": "Replace a specific string in a file with a new string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "The path to the file to modify"},
                    "old_string": {"type": "string", "description": "The exact string to replace"},
                    "new_string": {"type": "string", "description": "The new string to insert"}
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Execute a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute (e.g., 'ls -la', 'python test.py')"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a task saved as a markdown file. Use this when the user asks to create, add, or plan a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title for the task"},
                    "description": {"type": "string", "description": "Detailed description of what the task involves"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "show_task",
            "description": "Show the details of a task by its ID number. Use this when the user asks to see or show a specific task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "The task number (e.g., 1 for TASK-001)"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "implement_task",
            "description": "Implement a specific task, verify it, and set the status to done. Use this when the user asks to implement a specific task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "The task number to implement (e.g., 1 for TASK-001)"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "implement_all_tasks",
            "description": "Implement all pending tasks one by one, verify them, and set their status to done. Use this when the user asks to implement all tasks.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# --- 3. Helper to Execute Tools ---

def execute_tool_call(tool_name, arguments):
    """Executes a tool call based on name and arguments."""
    # Handle arguments being passed as a string (JSON) or a dict
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON arguments for {tool_name}"
    else:
        args = arguments
    
    if tool_name == "list_files":
        return list_files(**args)
    elif tool_name == "read_file":
        return read_file(**args)
    elif tool_name == "write_file":
        return write_file(**args)
    elif tool_name == "replace_string":
        return replace_string(**args)
    elif tool_name == "run_shell_command":
        return run_shell_command(**args)
    elif tool_name == "create_task":
        return create_task(**args)
    elif tool_name == "show_task":
        return show_task(**args)
    elif tool_name == "implement_task":
        return implement_task(**args)
    elif tool_name == "implement_all_tasks":
        return implement_all_tasks(**args)
    else:
        return f"Error: Unknown tool '{tool_name}'"