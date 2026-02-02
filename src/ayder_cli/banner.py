import random
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
from rich.text import Text
from ayder_cli.console import console


TIPS = [
    "Use /help for available commands",
    "Ctrl+R to search command history",
    "Use /tools to see available tools",
    "Use /clear to reset conversation",
    "Use /undo to remove last exchange",
]

GOTHIC_A = [
    r"              ",
    r"  ░▒▓▓▓▒░     ",
    r"       ▓▓     ",
    r"  ▒▓▓▓▓▓▓     ",
    r"  ▓▓  ▓▓▓     ",
    r"  ░▓▓▓▓▒█     ",
    r"              ",
]


def get_app_version():
    """
    Retrieves the version from the installed package metadata.
    Returns 'unknown (dev)' if the package is not installed (e.g., running raw script).
    """
    try:
        # CRITICAL: This string must match 'name' in pyproject.toml
        return version("ayder-cli")
    except PackageNotFoundError:
        return "unknown (dev)"


# Expose version globally if other modules need it
__version__ = get_app_version()


def print_welcome_banner(model, cwd):
    """Print the ayder-cli welcome banner in a two-column wireframe box using Rich styling."""
    # Shorten home directory
    home = str(Path.home())
    display_cwd = cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd

    # Column widths (inner content, excluding padding)
    left_w = 16   # fits the gothic A art
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
        banner.append(' ' * info_pad)
        banner.append(" ")
        banner.append("│\n", style="dim")

    # Bottom border
    banner.append(f"╰{'─' * (left_w + 2)}┴{'─' * (right_w + 2)}╯\n", style="dim")

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
