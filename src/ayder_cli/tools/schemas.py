"""
Tool schema definitions for ayder-cli.

This module contains the JSON schemas for all available tools in OpenAI function calling format.
"""

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory",
            "description_template": "Directory {directory} will be listed",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "The directory path (default: '.')", "default": "."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file, optionally specifying a line range.",
            "description_template": "File {file_path} will be read",
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
            "description_template": "File {file_path} will be written",
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
            "description_template": "File {file_path} will be modified",
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
            "description_template": "Command `{command}` will be executed",
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
            "description_template": "Task TASK-XXX.md will be created in .ayder/tasks/",
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
            "description_template": "Task TASK-{task_id} will be displayed",
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
            "description_template": "Task TASK-{task_id} will be implemented",
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
            "description_template": "All pending tasks will be implemented",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Search for a regex pattern across the codebase. Returns matching lines with file paths and line numbers. Use this to locate code before reading files.",
            "description_template": "Codebase will be searched for pattern '{pattern}'",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regex pattern to search for (e.g., 'def read_file', 'class.*Test', 'TODO.*bug')"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Optional file glob pattern to limit search (e.g., '*.py', 'src/**/*.js')"
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Whether the search is case-sensitive (default: true)"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Number of context lines to show before/after each match (default: 0)"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return (default: 50)"
                    },
                    "directory": {
                        "type": "string",
                        "description": "Root directory to search (default: '.')"
                    }
                },
                "required": ["pattern"]
            }
        }
    }
]

# Permission categories for each tool: r=read, w=write, x=execute
TOOL_PERMISSIONS = {
    "list_files": "r",
    "read_file": "r",
    "search_codebase": "r",
    "get_project_structure": "r",
    "show_task": "r",
    "list_tasks": "r",
    "write_file": "w",
    "replace_string": "w",
    "create_task": "w",
    "implement_task": "w",
    "implement_all_tasks": "w",
    "run_shell_command": "x",
}
