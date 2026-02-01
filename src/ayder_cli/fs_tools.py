import os
import json
import subprocess
import shutil
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

def get_project_structure(max_depth=3):
    """Generate a tree-style project structure summary."""
    tree_path = shutil.which("tree")

    if tree_path:
        cmd = [
            tree_path, "-L", str(max_depth),
            "-I", "__pycache__|*.pyc|*.egg-info|.venv|.ayder|.claude|htmlcov|dist|build",
            "--charset", "ascii", "--noreport"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, cwd=".")
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    # Fallback to manual tree generation
    return _generate_manual_tree(max_depth)


def _generate_manual_tree(max_depth=3, directory="."):
    """Fallback manual tree generator."""
    IGNORE_DIRS = {"__pycache__", ".venv", ".ayder", ".claude", ".git", "htmlcov", "dist", "build", "node_modules"}
    IGNORE_PATTERNS = {".pyc", ".egg-info"}

    def should_ignore(name):
        return name in IGNORE_DIRS or any(name.endswith(p) for p in IGNORE_PATTERNS)

    lines = [os.path.basename(os.path.abspath(directory)) or "."]

    def walk_dir(path, prefix="", depth=0):
        if depth >= max_depth:
            return
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return

        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e)) and not should_ignore(e)]
        files = [e for e in entries if os.path.isfile(os.path.join(path, e)) and not should_ignore(e)]

        for i, d in enumerate(dirs):
            is_last_dir = (i == len(dirs) - 1) and len(files) == 0
            connector = "`-- " if is_last_dir else "|-- "
            lines.append(f"{prefix}{connector}{d}/")
            new_prefix = prefix + ("    " if is_last_dir else "|   ")
            walk_dir(os.path.join(path, d), new_prefix, depth + 1)

        for i, f in enumerate(files):
            is_last = i == len(files) - 1
            connector = "`-- " if is_last else "|-- "
            lines.append(f"{prefix}{connector}{f}")

    walk_dir(directory)
    return "\n".join(lines)

def search_codebase(pattern, file_pattern=None, case_sensitive=True,
                   context_lines=0, max_results=50, directory="."):
    """
    Search for a pattern across the codebase using ripgrep (or grep fallback).
    Returns matching lines with file paths and line numbers.
    """
    try:
        rg_path = shutil.which("rg")

        if rg_path:
            return _search_with_ripgrep(pattern, file_pattern, case_sensitive,
                                       context_lines, max_results, directory)
        else:
            return _search_with_grep(pattern, file_pattern, case_sensitive,
                                    context_lines, max_results, directory)
    except Exception as e:
        return f"Error during search: {str(e)}"


def _search_with_ripgrep(pattern, file_pattern, case_sensitive,
                        context_lines, max_results, directory):
    """Implementation using ripgrep."""
    cmd = [shutil.which("rg"), "--line-number", "--heading",
           "--color", "never", "--no-messages", "--max-count", str(max_results)]

    if not case_sensitive:
        cmd.append("--ignore-case")
    if context_lines > 0:
        cmd.extend(["--context", str(context_lines)])
    if file_pattern:
        cmd.extend(["--glob", file_pattern])

    # Ignore common build artifacts
    for ignore in ["!.git/", "!__pycache__/", "!*.pyc", "!.venv/", "!.ayder/",
                   "!.claude/", "!dist/", "!build/", "!*.egg-info/", "!htmlcov/"]:
        cmd.extend(["--glob", ignore])

    cmd.extend([pattern, directory])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return _format_search_results(result.stdout, pattern, max_results)
        elif result.returncode == 1:
            return f"=== SEARCH RESULTS ===\nPattern: \"{pattern}\"\nNo matches found.\n=== END SEARCH RESULTS ==="
        else:
            return f"Error: ripgrep failed with exit code {result.returncode}\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Search timed out after 60 seconds."
    except Exception as e:
        return f"Error executing ripgrep: {str(e)}"


def _search_with_grep(pattern, file_pattern, case_sensitive,
                     context_lines, max_results, directory):
    """Fallback implementation using grep."""
    cmd = ["grep", "-r", "-n", "-E"]

    if not case_sensitive:
        cmd.append("-i")
    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])

    # Add exclusions
    for exclude_dir in [".git", "__pycache__", ".venv", ".ayder", ".claude",
                       "dist", "build", "htmlcov"]:
        cmd.extend([f"--exclude-dir={exclude_dir}"])
    cmd.append("--exclude=*.pyc")

    # File pattern (simplified for grep)
    if file_pattern:
        include_pattern = file_pattern.split("/")[-1]
        cmd.extend(["--include", include_pattern])

    cmd.extend([pattern, directory])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            # Grep output format is different from ripgrep, so format it
            return _format_grep_results(result.stdout, pattern, max_results)
        elif result.returncode == 1:
            return f"=== SEARCH RESULTS ===\nPattern: \"{pattern}\"\nNo matches found.\n=== END SEARCH RESULTS ==="
        else:
            return f"Error: grep failed with exit code {result.returncode}\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Search timed out after 60 seconds."
    except Exception as e:
        return f"Error executing grep: {str(e)}"


def _format_search_results(raw_output, pattern, max_results):
    """Format ripgrep --heading output for LLM consumption."""
    lines = raw_output.strip().split('\n')
    formatted = ["=== SEARCH RESULTS ===", f"Pattern: \"{pattern}\"", ""]

    current_file = None
    match_count = 0

    for line in lines:
        if match_count >= max_results:
            break

        # Ripgrep --heading format: blank line, then file path, then matches
        if not line:
            continue
        elif ':' not in line or line[0] not in '0123456789':
            # This is a file path header
            if current_file:
                formatted.append("")
            current_file = line
            formatted.append("─" * 67)
            formatted.append(f"FILE: {current_file}")
            formatted.append("─" * 67)
        elif current_file:
            # This is a match line
            formatted.append(f"Line {line}")
            match_count += 1

    formatted.insert(2, f"Matches found: {match_count}\n")
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _format_grep_results(raw_output, pattern, max_results):
    """Format grep output (file:line:content) for LLM consumption."""
    lines = raw_output.strip().split('\n')
    formatted = ["=== SEARCH RESULTS ===", f"Pattern: \"{pattern}\"", ""]

    # Group by file
    file_matches = {}
    for line in lines[:max_results]:
        if ':' in line:
            parts = line.split(':', 2)
            if len(parts) >= 3:
                file_path, line_num, content = parts[0], parts[1], parts[2]
                if file_path not in file_matches:
                    file_matches[file_path] = []
                file_matches[file_path].append((line_num, content))

    match_count = sum(len(matches) for matches in file_matches.values())
    formatted.insert(2, f"Matches found: {match_count}\n")

    for file_path, matches in file_matches.items():
        formatted.append("─" * 67)
        formatted.append(f"FILE: {file_path}")
        formatted.append("─" * 67)
        for line_num, content in matches:
            formatted.append(f"Line {line_num}: {content}")
        formatted.append("")

    formatted.append("=== END SEARCH RESULTS ===")
    return "\n".join(formatted)

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
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Search for a regex pattern across the codebase. Returns matching lines with file paths and line numbers. Use this to locate code before reading files.",
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
    elif tool_name == "search_codebase":
        return search_codebase(**args)
    else:
        return f"Error: Unknown tool '{tool_name}'"