import json
import random
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


def draw_box(
    text: str, title: str = None, width: int = None, color_code: str = None
) -> None:
    """Draw a box around text using Rich Panel.

    Args:
        text: The text to display in the box
        title: Optional title for the panel
        width: Optional width for the panel
        color_code: Optional ANSI color code for border (36=cyan, 32=green, etc.)
    """
    border_style = None
    if color_code:
        color_map = {
            "36": "cyan",
            "32": "green",
            "33": "yellow",
            "35": "magenta",
            "31": "red",
        }
        border_style = color_map.get(color_code, "white")

    console.print(Panel(text, title=title, width=width, border_style=border_style))


def print_markdown(
    text: str, title: str = None, width: int = None, color_code: str = None
) -> None:
    """Print markdown text in a styled box.

    Args:
        text: Markdown text to display
        title: Optional title for the panel
        width: Optional width for the panel
        color_code: Optional ANSI color code for border (36=cyan, 32=green, etc.)
    """
    border_style = None
    if color_code:
        color_map = {
            "36": "cyan",
            "32": "green",
            "33": "yellow",
            "35": "magenta",
            "31": "red",
        }
        border_style = color_map.get(color_code, "white")

    console.print(
        Panel(Markdown(text), title=title, width=width, border_style=border_style)
    )


def print_user_message(text: str) -> None:
    """Print a user message in a styled box.

    Args:
        text: The message text to display
    """
    console.print(Panel(text, title="You", border_style="cyan"))


def print_assistant_message(text: str) -> None:
    """Print an assistant message in a styled box.

    Args:
        text: The message text to display
    """
    console.print(Panel(text, title="Assistant", border_style="green"))


def print_code_block(code: str, language: str = "text", title: str = None) -> None:
    """Print a code block with syntax highlighting.

    Args:
        code: The code string to display
        language: The programming language for syntax highlighting
        title: Optional title for the panel
    """
    syntax = Syntax(code, language)
    console.print(Panel(syntax, title=title, border_style="green"))


def print_tool_call(function_name: str, arguments: str) -> None:
    """Print a tool call in a styled box.

    Args:
        function_name: Name of the function being called
        arguments: JSON string of arguments
    """
    console.print(
        Panel(
            f"Function: {function_name}\nArguments: {arguments}",
            title="Tool Call",
            border_style="yellow",
        )
    )


def print_llm_request_debug(messages, model, tools=None, options=None):
    """Display formatted LLM request details in verbose mode.

    Args:
        messages: List of message dicts or objects sent to LLM
        model: Model name
        tools: List of tool schemas (optional)
        options: Model options dict (optional)
    """
    from typing import List, Dict, Any, Optional

    # Format summary line
    num_messages = len(messages) if messages else 0
    num_tools = len(tools) if tools else 0
    ctx_size = (
        options.get("num_ctx", "default")
        if options and isinstance(options, dict)
        else "default"
    )

    summary = (
        f"Messages: {num_messages} | Tools: {num_tools} | Context: {ctx_size} tokens"
    )

    # Format message preview (first 200 chars per message)
    content = Text()
    if messages:
        for i, msg in enumerate(messages, 1):
            # Handle both dict and object formats
            if isinstance(msg, dict):
                role = msg.get("role", "unknown")
                msg_content = msg.get("content", "")
            else:
                # Handle OpenAI SDK message objects
                role = getattr(msg, "role", "unknown")
                msg_content = getattr(msg, "content", "")

            # Handle non-string content (e.g., tool results)
            if not isinstance(msg_content, str):
                msg_content = str(msg_content)

            # Truncate long messages
            if len(msg_content) > 200:
                preview = msg_content[:200] + "..."
            else:
                preview = msg_content

            # Replace newlines with space for compact display
            preview = preview.replace("\n", " ")

            content.append(f"[{i}] ", style="bold")
            content.append(f"{role}: ", style="cyan")
            content.append(f"{preview}\n", style="dim")

    # Format tool list (names only)
    if tools:
        content.append("\n")
        # Handle both dict and object formats for tools
        tool_names = []
        for t in tools:
            if isinstance(t, dict):
                tool_names.append(t.get("function", {}).get("name", "?"))
            else:
                # Handle object format
                func = getattr(t, "function", None)
                if func:
                    name = (
                        getattr(func, "name", "?")
                        if hasattr(func, "name")
                        else func.get("name", "?")
                    )
                    tool_names.append(name)
                else:
                    tool_names.append("?")
        content.append("Tools: ", style="bold")
        content.append(", ".join(tool_names), style="yellow")

    console.print(
        Panel(
            content,
            title=f"🔍 LLM Request (Model: {model})",
            subtitle=summary,
            border_style="yellow",
            padding=(1, 2),
        )
    )


def print_tool_result(result: str) -> None:
    """Print a tool execution result with a checkmark, truncating long results."""
    if len(result) > 300:
        result = result[:300] + "..."
    console.print(f"✓ {result}")


def print_tool_skipped(tool_name: str = "", reason: str = "declined by user") -> None:
    """Print when a tool call is skipped, typically because user declined it."""
    console.print(f"✗ Tool call skipped by user")


def print_file_content(file_path):
    """Read a file and print its contents in a styled box with the filename as the title."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        console.print(
            Panel(content, title=file_path, border_style="cyan", padding=(1, 2))
        )
    except Exception as e:
        console.print(
            Panel(
                f"Could not read file: {e}",
                title="Verbose Error",
                border_style="red",
                padding=(1, 2),
            )
        )


def print_file_content_rich(file_path: str, content: str = None) -> None:
    """Read a file and print its contents in a styled box with the filename as the title.

    Args:
        file_path: Path to the file
        content: Optional content string to use instead of reading from file
    """
    try:
        if content is None:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        console.print(
            Panel(content, title=file_path, border_style="cyan", padding=(1, 2))
        )
    except Exception as e:
        console.print(
            Panel(
                f"Could not read file: {e}",
                title="Error",
                border_style="red",
                padding=(1, 2),
            )
        )


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
        # Remove trailing newlines but preserve leading whitespace (diff context lines start with space)
        text = Text(line.rstrip("\n"))
        if line.startswith("@@"):
            text.stylize("cyan")
        elif line.startswith("-") and not line.startswith("---"):
            text.stylize("red")
        elif line.startswith("+") and not line.startswith("+++"):
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
            diff_lines = list(
                difflib.unified_diff(
                    [],
                    new_lines,
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                    lineterm="",
                )
            )
        else:
            # File exists - read current content
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                current_content = f.read()

            # Check for binary content (null bytes in first 8KB)
            if b"\x00" in current_content[:8192].encode("utf-8", errors="ignore"):
                return None

            current_lines = current_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            diff_lines = list(
                difflib.unified_diff(
                    current_lines,
                    new_lines,
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                    lineterm="",
                )
            )

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
        console.print(
            Panel(diff, title="Preview", border_style="magenta", padding=(1, 2))
        )
    else:
        console.print(
            "\n[yellow]Warning: Unable to generate preview (binary file or error)[/yellow]"
        )

    return confirm_tool_call(description)


def describe_tool_action(fname, args):
    """Generate a human-friendly description of what a tool call will do.

    Uses description_template from ToolDefinition for schema-driven descriptions.
    Falls back to generic description if tool or template not found.
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}

    # Special case for search_codebase with file_pattern (needs dynamic extension)
    if fname == "search_codebase":
        pattern = args.get("pattern", "unknown")
        file_pattern = args.get("file_pattern")
        desc = f"Codebase will be searched for pattern '{pattern}'"
        if file_pattern:
            desc += f" in files matching '{file_pattern}'"
        return desc

    from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

    tool_def = TOOL_DEFINITIONS_BY_NAME.get(fname)
    if tool_def and tool_def.description_template:
        try:
            format_args = dict(args)
            if "task_id" in format_args and isinstance(format_args["task_id"], int):
                format_args["task_id"] = f"{format_args['task_id']:03d}"
            if fname == "list_files" and "directory" not in format_args:
                format_args["directory"] = "."
            # Provide default 'unknown' for missing template parameters
            param_names = re.findall(r"\{(\w+)", tool_def.description_template)
            for param in param_names:
                if param not in format_args:
                    format_args[param] = "unknown"
            return tool_def.description_template.format(**format_args)
        except (KeyError, ValueError, TypeError):
            pass

    return f"{fname} will be called"


@contextmanager
def agent_working_status(
    message: str = "Agent is working...",
) -> Generator[Status, None, None]:
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


def print_running() -> None:
    """Print a running indicator with a leading newline."""
    console.print("\n[yellow]Running...[/yellow]")


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
def file_operation_status(
    operation: str, file_path: str
) -> Generator[Status, None, None]:
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


def print_welcome_banner(model, cwd):
    """Print the ayder-cli welcome banner in a two-column wireframe box using Rich styling."""
    from ayder_cli.version import __version__

    # Shorten home directory
    home = str(Path.home())
    display_cwd = cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd

    # Column widths (inner content, excluding padding)
    left_w = 16  # fits the gothic A art
    right_w = 38  # info text

    # Right-column content (plain text for width calc)
    app_ver = __version__
    info = [
        ("", ""),
        (f"ayder-cli v{app_ver}", "bold white"),
        (f"{model} · Ollama", "bright_black"),
        (display_cwd, "dim"),
        ("", ""),
    ]

    # Art pattern for the 'A' in AYDER
    GOTHIC_A = [
        r"              ",
        r"  ░▒▓▓▓▒░     ",
        r"       ▓▓     ",
        r"  ▒▓▓▓▓▓▓     ",
        r"  ▓▓  ▓▓▓     ",
        r"  ░▓▓▓▓▒█     ",
        r"              ",
    ]

    # Pad art and info to same height
    rows = max(len(GOTHIC_A), len(info))
    art_lines = GOTHIC_A + ["" * left_w] * (rows - len(GOTHIC_A))
    info_lines = info + [("", "")] * (rows - len(info))

    # Build banner with Rich Text
    banner = Text()

    # Top border
    banner.append(f"╭{'─' * (left_w + 2)}┬{'─' * (right_w + 2)}╮\n", style="dim")

    for i in range(rows):
        art = art_lines[i]
        text_content, style = info_lines[i]
        art_pad = left_w - len(art)
        info_pad = right_w - len(text_content)

        # Build each row
        banner.append("│", style="dim")
        banner.append(f" {art}{' ' * art_pad} ", style="bold bright_blue")
        banner.append("│", style="dim")
        banner.append(" ")
        if text_content:
            banner.append(text_content, style=style)
        banner.append(" " * info_pad)
        banner.append(" ")
        banner.append("│\n", style="dim")

    # Bottom border
    banner.append(f"╰{'─' * (left_w + 2)}┴{'─' * (right_w + 2)}╯\n", style="dim")

    # Tips for users
    TIPS = [
        "Use /help for available commands",
        "Use /tools to see available tools",
        "Use /compact to summarize, save, and reset",
        "Use /model to change LLM model",
        "Use /plan type your plan to split into small PRD files",
        "Use /tasks to list current tasks",
        "Use /implement N to implement the task (N = 1 on TASK-001)",
    ]

    # Tip line below the box
    tip = random.choice(TIPS)
    tip_line = Text()
    tip_line.append(" ")
    tip_line.append("?", style="yellow")
    tip_line.append(" ")
    tip_line.append("Tip: ", style="dim")
    tip_line.append(tip, style="dim")

    console.print()
    console.print(banner)
    console.print(tip_line)
    console.print()
