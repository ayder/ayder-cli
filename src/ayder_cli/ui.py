import json
import re
import textwrap
import os


def draw_box(text, title="", width=80, color_code="36"):
    """
    Draw an ANSI box around text with optional title.
    color_code: 36=cyan, 32=green, 33=yellow, 35=magenta, 31=red
    """
    # Box drawing characters
    top_left = "╭"
    top_right = "╮"
    bottom_left = "╰"
    bottom_right = "╯"
    horizontal = "─"
    vertical = "│"

    # Wrap text to fit within box
    wrapped_lines = []
    for line in text.split('\n'):
        if line:
            wrapped_lines.extend(textwrap.wrap(line, width=width-4))
        else:
            wrapped_lines.append("")

    # Build the box
    lines = []

    # Top border with optional title
    if title:
        title_text = f" {title} "
        remaining = width - len(title_text) - 2
        left_pad = remaining // 2
        right_pad = remaining - left_pad
        lines.append(f"\033[{color_code}m{top_left}{horizontal * left_pad}{title_text}{horizontal * right_pad}{top_right}\033[0m")
    else:
        lines.append(f"\033[{color_code}m{top_left}{horizontal * (width-2)}{top_right}\033[0m")

    # Content lines
    for line in wrapped_lines:
        padding = width - len(line) - 4
        lines.append(f"\033[{color_code}m{vertical}\033[0m {line}{' ' * padding} \033[{color_code}m{vertical}\033[0m")

    # Bottom border
    lines.append(f"\033[{color_code}m{bottom_left}{horizontal * (width-2)}{bottom_right}\033[0m")

    return "\n".join(lines)


def print_user_message(text):
    """Print user message in a cyan box."""
    print("\n" + draw_box(text, title="You", width=80, color_code="36"))


def print_assistant_message(text):
    """Print assistant message in a green box."""
    print("\n" + draw_box(text, title="Assistant", width=80, color_code="32"))


def print_tool_call(func_name, args):
    """Print tool execution in a yellow box."""
    text = f"{func_name}({args})"
    print("\n" + draw_box(text, title="Tool Call", width=80, color_code="33"))


def print_tool_result(result):
    """Print tool result in a magenta box."""
    result_str = str(result)
    if len(result_str) > 300:
        result_str = result_str[:300] + "..."
    print(draw_box(result_str, title="Tool Result", width=80, color_code="35"))


def print_running():
    """Print a simple running indicator instead of echoing the user prompt."""
    print("\n\033[33mRunning...\033[0m")


def describe_tool_action(fname, args):
    """Generate a human-friendly description of what a tool call will do."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}

    if fname == "create_task":
        title = args.get("title", "untitled")
        return f"Task TASK-XXX.md will be created in .ayder/tasks/"
    elif fname == "show_task":
        task_id = args.get("task_id", "?")
        return f"Task TASK-{task_id:03d} will be displayed" if isinstance(task_id, int) else f"Task TASK-{task_id} will be displayed"
    elif fname == "write_file":
        return f"File {args.get('file_path', 'unknown')} will be written"
    elif fname == "read_file":
        return f"File {args.get('file_path', 'unknown')} will be read"
    elif fname == "list_files":
        return f"Directory {args.get('directory', '.')} will be listed"
    elif fname == "replace_string":
        return f"File {args.get('file_path', 'unknown')} will be modified"
    elif fname == "run_shell_command":
        return f"Command `{args.get('command', 'unknown')}` will be executed"
    elif fname == "list_tasks":
        return "Tasks will be listed"
    elif fname == "search_codebase":
        pattern = args.get('pattern', 'unknown')
        file_pattern = args.get('file_pattern')
        desc = f"Codebase will be searched for pattern '{pattern}'"
        if file_pattern:
            desc += f" in files matching '{file_pattern}'"
        return desc
    else:
        return f"{fname} will be called"


def print_file_content(file_path):
    """Read a file and print its contents in a styled box with the filename as the title."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print("\n" + draw_box(content, title=file_path, width=80, color_code="36"))
    except Exception as e:
        print("\n" + draw_box(f"Could not read file: {e}", title="Verbose Error", width=80, color_code="31"))


def confirm_tool_call(description=""):
    """Ask user to confirm a tool call with a human-friendly description. Returns True if approved."""
    try:
        prompt = f"\033[33m{description}. Proceed? (Y/n)\033[0m " if description else "\033[33mProceed? (Y/n)\033[0m "
        answer = input(prompt).strip().lower()
        return answer in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def colorize_diff(diff_lines):
    """
    Apply ANSI color codes to diff lines.
    Red (31) for deletions (lines starting with - but not ---)
    Green (32) for additions (lines starting with + but not +++)
    Cyan (36) for hunk headers (lines starting with @@)
    Default color for context lines
    """
    colorized = []
    for line in diff_lines:
        if line.startswith('@@'):
            colorized.append(f"\033[36m{line}\033[0m")
        elif line.startswith('-') and not line.startswith('---'):
            colorized.append(f"\033[31m{line}\033[0m")
        elif line.startswith('+') and not line.startswith('+++'):
            colorized.append(f"\033[32m{line}\033[0m")
        else:
            colorized.append(line)
    return colorized


def truncate_diff(diff_lines, max_lines=100):
    """
    If diff <= max_lines, return unchanged.
    If diff > max_lines, return first 80 lines + separator + last 20 lines.
    """
    if len(diff_lines) <= max_lines:
        return diff_lines

    first_80 = diff_lines[:80]
    last_20 = diff_lines[-20:]
    omitted = len(diff_lines) - 80 - 20
    separator = f"\n... [{omitted} more lines omitted] ...\n"

    return first_80 + [separator] + last_20


def generate_diff_preview(file_path, new_content):
    """
    Generate a unified diff preview of file changes.
    - If file doesn't exist: create "new file" diff (all lines as additions)
    - If file exists: read current and generate diff
    - Returns formatted diff string or None on error/binary file
    """
    import difflib

    try:
        # Check if file exists
        if not os.path.exists(file_path):
            # New file - show all as additions
            new_lines = new_content.splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(
                [],
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm=''
            ))
        else:
            # File exists - read current content
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                current_content = f.read()

            # Check for binary content (null bytes in first 8KB)
            if b'\x00' in current_content[:8192].encode('utf-8', errors='ignore'):
                return None

            current_lines = current_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            diff_lines = list(difflib.unified_diff(
                current_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm=''
            ))

        if not diff_lines:
            return None

        # Colorize and truncate
        colorized = colorize_diff(diff_lines)
        truncated = truncate_diff(colorized)

        return "\n".join(truncated)

    except Exception:
        return None


def confirm_with_diff(file_path, new_content, description=""):
    """
    Show a diff preview of file changes, then prompt for confirmation.
    If diff is available, display it in a magenta box.
    Otherwise show a warning.
    """
    diff = generate_diff_preview(file_path, new_content)

    if diff:
        print("\n" + draw_box(diff, title="Preview", color_code="35"))
    else:
        print("\n\033[33mWarning: Unable to generate preview (binary file or error)\033[0m")

    return confirm_tool_call(description)


