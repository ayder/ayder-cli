import random
from pathlib import Path


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


def print_welcome_banner(model, cwd):
    """Print the ayder-cli welcome banner in a two-column wireframe box."""
    B = "\033[1;34m"      # bold naval blue
    W = "\033[1;37m"      # bold white
    S = "\033[38;5;248m"  # dim silver
    G = "\033[38;5;243m"  # dim gray
    Y = "\033[33m"        # yellow
    D = "\033[2m"         # dim
    F = "\033[38;5;240m"  # frame color (dark gray)
    R = "\033[0m"         # reset

    # Shorten home directory
    home = str(Path.home())
    display_cwd = cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd

    # Column widths (inner content, excluding padding)
    left_w = 16   # fits the gothic A art
    right_w = 38  # info text
    total_w = left_w + right_w + 5  # 1 border + 1 pad + left + 1 border + 1 pad + right + 1 pad + 1 border

    # Right-column content (plain text for width calc, formatted for display)
    info = [
        ("", ""),
        (f"{W}ayder-cli v0.1.0{R}", "ayder-cli v0.1.0"),
        (f"{S}{model} · Ollama{R}", f"{model} · Ollama"),
        (f"{G}{display_cwd}{R}", display_cwd),
        ("", ""),
    ]

    # Pad art and info to same height
    rows = max(len(GOTHIC_A), len(info))
    art_lines = GOTHIC_A + ["" * left_w] * (rows - len(GOTHIC_A))
    info_lines = info + [("", "")] * (rows - len(info))

    # Build output
    lines = []

    # Top border
    lines.append(f"{F}╭{'─' * (left_w + 2)}┬{'─' * (right_w + 2)}╮{R}")

    for i in range(rows):
        art = art_lines[i]
        formatted, plain = info_lines[i]
        art_pad = left_w - len(art)
        info_pad = right_w - len(plain)
        lines.append(
            f"{F}│{R} {B}{art}{R}{' ' * art_pad} "
            f"{F}│{R} {formatted}{' ' * info_pad} {F}│{R}"
        )

    # Middle separator
    lines.append(f"{F}╰{'─' * (left_w + 2)}┴{'─' * (right_w + 2)}╯{R}")

    # Tip line below the box
    tip = random.choice(TIPS)
    lines.append(f" {Y}?{R} {D}Tip: {tip}{R}")

    print()
    print("\n".join(lines))
    print()
