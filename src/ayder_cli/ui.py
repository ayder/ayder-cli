import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.status import Status
from rich.text import Text
from ayder_cli.console import console, get_language_from_path


def print_user_message(text):
    """Print user message in a cyan panel."""
    console.print(Panel(
        text, 
        title="You", 
        border_style="user",
        padding=(1, 2)
    ))


def print_assistant_message(text):
    """Print assistant message in a green panel."""
    console.print(Panel(
        text, 
        title="Assistant", 
        border_style="assistant",
        padding=(1, 2)
    ))


def print_tool_call(func_name, args):
    """Print tool execution in a yellow panel."""
    text = f"{func_name}({args})"
    console.print(Panel(
        text, 
        title="Tool Call", 
        border_style="tool_call",
        padding=(1, 2)
    ))


def draw_box(text, title="", width=80, color_code="36"):
    """
    DEPRECATED: Use Rich Panels directly.
    Kept for backward compatibility, delegates to Rich Panel.
    """
    style_map = {
        "36": "cyan",
        "32": "green", 
        "33": "yellow",
        "35": "magenta",
        "31": "red",
    }
    border_style = style_map.get(color_code, "cyan")
    
    console.print(Panel(
        text,
        title=title if title else None,
        border_style=border_style,
        width=width,
        padding=(1, 2)
    ))


def print_file_content_rich(file_path: str, content: str = None) -> None:
    """
    Display file content with syntax highlighting.
    
    Args:
        file_path: Path to the file (used for language detection)
        content: File content (if None, reads from file)
    """
    if content is None:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            console.print(Panel(
                f"Could not read file: {e}",
                title="Error",
                border_style="error"
            ))
            return
    
    language = get_language_from_path(file_path)
    
    # Create syntax-highlighted content
    syntax = Syntax(
        content,
        language,
        theme="monokai",
        line_numbers=True,
        word_wrap=True
    )
    
    console.print(Panel(
        syntax,
        title=file_path,
        border_style="info"
    ))


def print_markdown(text: str, title: str = None) -> None:
    """
    Render markdown text with proper formatting.
    
    Args:
        text: Markdown text to render
        title: Optional panel title
    """
    md = Markdown(text)
    
    if title:
        console.print(Panel(md, title=title, border_style="assistant"))
    else:
        console.print(md)


def print_code_block(code: str, language: str = "python", title: str = None) -> None:
    """
    Display a code block with syntax highlighting.
    
    Args:
        code: The code to display
        language: Programming language for highlighting
        title: Optional panel title
    """
    syntax = Syntax(
        code,
        language,
        theme="monokai",
        line_numbers=True,
        word_wrap=True
    )
    
    console.print(Panel(
        syntax,
        title=title or f"{language}",
        border_style="info"
    ))


def print_tool_result(result):
    """Print tool result with a checkmark prefix."""
    from rich.text import Text
    
    result_str = str(result)
    if len(result_str) > 300:
        result_str = result_str[:300] + "..."
    
    text = Text()
    text.append("✓ ", style="bold green")
    text.append(result_str)
    console.print(text)


def print_running():
    """Print a simple running indicator instead of echoing the user prompt."""
    console.print("\n[yellow]Running...[/yellow]")


@contextmanager
def agent_working_status(message: str = "Agent is working...") -> Generator[Status, None, None]:
    """
    Context manager for showing agent working status.
    
    Usage:
        with agent_working_status("Processing..."):
            result = call_llm(...)
    
    Args:
        message: Status message to display
        
    Yields:
        Rich Status object
    """
    with console.status(f"[bold green]{message}") as status:
        yield status


def print_running_rich(message: str = "Running...") -> None:
    """
    Print a Rich-styled running indicator.
    
    Args:
        message: Message to display
    """
    console.print(f"[yellow]{message}[/yellow]")


@contextmanager
def tool_execution_status(tool_name: str) -> Generator[Status, None, None]:
    """
    Context manager for showing tool execution status.
    
    Args:
        tool_name: Name of the tool being executed
        
    Yields:
        Rich Status object
    """
    with console.status(f"[bold yellow]Executing {tool_name}...") as status:
        yield status


@contextmanager
def file_operation_status(operation: str, file_path: str) -> Generator[Status, None, None]:
    """
    Context manager for showing file operation status.
    
    Args:
        operation: Type of operation (reading, writing, etc.)
        file_path: Path to the file
        
    Yields:
        Rich Status object
    """
    display_path = file_path
    if len(display_path) > 40:
        display_path = "..." + display_path[-37:]
    
    with console.status(f"[bold cyan]{operation} {display_path}...") as status:
        yield status


@contextmanager
def search_status(pattern: str) -> Generator[Status, None, None]:
    """
    Context manager for showing search progress.
    
    Args:
        pattern: Search pattern being used
        
    Yields:
        Rich Status object
    """
    display_pattern = pattern if len(pattern) < 30 else pattern[:27] + "..."
    with console.status(f"[bold blue]Searching for '{display_pattern}'...") as status:
        yield status


def print_tool_skipped():
    """Print a simple tool skipped indicator with icon prefix."""
    from rich.text import Text
    
    text = Text()
    text.append("✗  ", style="bold yellow")
    text.append("Tool call skipped by user.")
    console.print(text)


def describe_tool_action(fname, args):
    """Generate a human-friendly description of what a tool call will do.
    
    Uses description_template from tool schemas for schema-driven descriptions.
    Falls back to generic description if tool or template not found.
    """
    from ayder_cli.tools.schemas import tools_schema
    
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    
    # Special case for list_tasks (no schema entry but has permission)
    if fname == "list_tasks":
        return "Tasks will be listed"
    
    # Special case for search_codebase with file_pattern (needs dynamic extension)
    if fname == "search_codebase":
        pattern = args.get('pattern', 'unknown')
        file_pattern = args.get('file_pattern')
        # Use schema template as base
        desc = f"Codebase will be searched for pattern '{pattern}'"
        if file_pattern:
            desc += f" in files matching '{file_pattern}'"
        return desc
    
    # Find the tool schema and its description template
    description_template = None
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == fname:
            description_template = tool["function"].get("description_template")
            break
    
    if description_template:
        try:
            # Handle special formatting for task_id (zero-padding for integers only)
            format_args = dict(args)
            if "task_id" in format_args and isinstance(format_args["task_id"], int):
                # Format task_id with zero-padding (e.g., 1 -> 001)
                format_args["task_id"] = f"{format_args['task_id']:03d}"
            # Handle defaults for optional parameters
            if fname == "list_files" and "directory" not in format_args:
                format_args["directory"] = "."
            # Provide default 'unknown' for missing required parameters
            # Extract parameter names from template
            import re
            param_names = re.findall(r'\{(\w+)', description_template)
            for param in param_names:
                if param not in format_args:
                    format_args[param] = "unknown"
            return description_template.format(**format_args)
        except (KeyError, ValueError, TypeError):
            # Fall through to generic description if formatting fails
            pass
    
    # Fallback for tools without templates or formatting errors
    return f"{fname} will be called"


def print_file_content(file_path):
    """Read a file and print its contents in a styled box with the filename as the title."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        console.print(Panel(
            content,
            title=file_path,
            border_style="cyan",
            padding=(1, 2)
        ))
    except Exception as e:
        console.print(Panel(
            f"Could not read file: {e}",
            title="Verbose Error",
            border_style="red",
            padding=(1, 2)
        ))


def confirm_tool_call(description=""):
    """Ask user to confirm a tool call with a human-friendly description. Returns True if approved."""
    try:
        # Build the prompt text with Rich styling
        prompt_text = Text()
        if description:
            prompt_text.append(f"{description}. ", style="yellow")
        prompt_text.append("Proceed? (Y/n)", style="bold yellow")
        
        # Print the prompt and get input
        console.print(prompt_text, end=" ")
        answer = input().strip().lower()
        return answer in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False


def colorize_diff(diff_lines):
    """
    Apply Rich styling to diff lines.
    Red for deletions, Green for additions, Cyan for hunk headers.
    """
    colorized = []
    for line in diff_lines:
        text = Text(line)
        if line.startswith('@@'):
            text.stylize("cyan")
        elif line.startswith('-') and not line.startswith('---'):
            text.stylize("red")
        elif line.startswith('+') and not line.startswith('+++'):
            text.stylize("green")
        colorized.append(text)
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
    - Returns Rich Text object with styled diff or None on error/binary file
    """
    import difflib

    try:
        # Check if file exists
        if not Path(file_path).exists():
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

        # Combine Text objects into a single Text
        combined = Text()
        for i, text_obj in enumerate(truncated):
            if i > 0:
                combined.append("\n")
            combined.append(text_obj)
        
        return combined

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
        console.print(Panel(
            diff,
            title="Preview",
            border_style="magenta",
            padding=(1, 2)
        ))
    else:
        console.print("\n[yellow]Warning: Unable to generate preview (binary file or error)[/yellow]")

    return confirm_tool_call(description)


