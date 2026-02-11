import random
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
from rich.text import Text
from rich.console import Console, Group
from rich.panel import Panel
from rich.align import Align
from rich.table import Table
from rich import box
from ayder_cli.console import console


TIPS = [
    "Use /help for available commands",
    "Use /tools to see available tools",
    "Use /compact to summarize, save, and reset",
    "Use /model to change LLM model",
    "Use /plan type your plan to split into small PRD files",
    "Use /tasks to list current tasks",
    "Use /implement N to implement the task (N = 1 on TASK-001)",
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

# ANSI color codes for direct use in ASCII banners
_C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[96m",
    "cyan_bright": "\033[38;5;51m",
    "blue": "\033[94m",
    "blue_bright": "\033[38;5;39m",
    "purple": "\033[38;5;141m",
    "magenta": "\033[95m",
    "magenta_bright": "\033[38;5;201m",
    "green": "\033[92m",
    "yellow": "\033[93m",
}


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


def print_rich_banner():
    """Print a rich panel banner with gradient-colored AYDER title."""
    # Create the stylized title
    title_line = Text()
    title_line.append("◆ ", style="cyan")
    title_line.append("A", style="bold bright_cyan")
    title_line.append("Y", style="bold cyan")
    title_line.append("D", style="bold bright_blue")
    title_line.append("E", style="bold blue")
    title_line.append("R", style="bold purple")
    title_line.append(" ◆", style="bright_magenta")
    
    # Subtitle
    subtitle = Text("AI-Powered Coding Assistant", style="dim italic")
    
    # Version badge
    version = Text(f" v{__version__} ", style="bold green on black")
    
    # Create features table
    features = Table(show_header=False, box=None, padding=(0, 2))
    features.add_column(style="cyan")
    features.add_column(style="green")
    features.add_column(style="yellow")
    features.add_column(style="magenta")
    features.add_row(
        "● Multi-Agent",
        "● Context Mgmt",
        "● Local LLMs",
        "● Tool System"
    )
    
    # Group the content
    group = Group(
        Align.center(title_line),
        Align.center(subtitle),
        Text(""),
        Align.center(features),
    )
    
    # Create the panel
    panel = Panel(
        group,
        title=version,
        title_align="right",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 4),
    )
    
    console.print()
    console.print(panel)
    console.print()
    
    # Quick start hint
    hint = Text()
    hint.append("Run ", style="dim")
    hint.append("ayder --help", style="bold yellow")
    hint.append(" for usage information", style="dim")
    console.print(Align.center(hint))
    console.print()


def print_compact_banner():
    """Print a compact banner suitable for startup messages."""
    text = Text()
    text.append("◆ ", style="cyan")
    text.append("AYDER", style="bold bright_cyan")
    text.append(f" v{__version__}", style="dim")
    text.append(" — AI-Powered Coding Assistant", style="dim")
    console.print(text)


def print_ascii_banner():
    """Print a pure ASCII art banner with ANSI colors."""
    c = _C
    
    banner = f"""
{c['cyan']}    ___   {c['cyan_bright']}_____   {c['blue']}_____   {c['purple']}_____   {c['magenta']}_____{c['reset']}
{c['cyan']}   /\\  \\  {c['cyan_bright']}/\\  __\\  {c['blue']}/\\  __-./{c['purple']}/\\  __-. {c['magenta']}/\\  __-.{c['reset']}
{c['cyan']}  /::\\  \\{c['cyan_bright']}/::\\_|  \\{c['blue']}\\ \\ \\/__/\\{c['purple']} \\ \\/__/ {c['magenta']}\\ \\ \\/__/{c['reset']}
{c['cyan']} /:/\\:\\__{c['cyan_bright']}\\:/\\____/{c['blue']}\\ \\____\\{c['purple']}\\ \\____\\{c['magenta']}\\ \\____\\{c['reset']}
{c['cyan']} \\:\\ \\/__{c['cyan_bright']}\\/____/  {c['blue']}\\/____/ {c['purple']}\\/____/ {c['magenta']}\\/____/{c['reset']}
{c['cyan']}  \\:\\__\\ {c['cyan_bright']}         {c['blue']}        {c['purple']}        {c['magenta']}       {c['reset']}
{c['cyan']}   \\/__/  {c['cyan_bright']}         {c['blue']}        {c['purple']}        {c['magenta']}       {c['reset']}

{c['cyan']}╔══════════════════════════════════════════════════╗{c['reset']}
{c['cyan']}║{c['reset']}  {c['bold']}{c['cyan']}A{c['cyan_bright']}Y{c['blue']}D{c['purple']}E{c['magenta']}R{c['reset']} {c['bold']}CLI{c['reset']}  {c['dim']}— AI-Powered Coding Assistant{c['reset']}     {c['cyan']}║{c['reset']}
{c['cyan']}╚══════════════════════════════════════════════════╝{c['reset']}
"""
    print(banner)


def print_minimal_banner():
    """Print minimal banner with just name and version."""
    console.print(f"[bold bright_cyan]ayder[/] [green]{__version__}[/] - AI-Powered Coding Assistant")


def print_fancy_banner(model,version):
    """Print a fancy gradient banner with block letters."""
    # Build the banner with gradient effect
    art_lines = [
        "                    █████╗ ██╗   ██╗██████╗ ███████╗██████╗ ",
        "                   ██╔══██╗╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗",
        "                   ███████║ ╚████╔╝ ██║  ██║█████╗  ██████╔╝",
        "                   ██╔══██║  ╚██╔╝  ██║  ██║██╔══╝  ██╔══██╗",
        "                   ██║  ██║   ██║   ██████╔╝███████╗██║  ██║",
        "                   ╚═╝  ╚═╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝",
    ]
    
    colors = ["bright_cyan", "cyan", "blue", "purple", "bright_magenta", "magenta"]
    
    console.print()
    for i, line in enumerate(art_lines):
        console.print(f"[{colors[i]}]{line}[/]")
    
    console.print()
    console.print(Align.center("[bold]AI-Powered Coding Assistant[/]"))
    console.print(Align.center(f"[dim]Version {__version__}[/]"))
    console.print(Align.center(f"[dim]Version {model}[/]"))
    console.print()


def print_futuristic_banner():
    """Print a futuristic high-ANSI neon banner with scan-line aesthetic."""
    c = _C

    # Extended ANSI 256-color codes for the neon/cyber palette
    _F = {
        "neon_cyan":    "\033[38;5;87m",
        "neon_blue":    "\033[38;5;33m",
        "ice_blue":     "\033[38;5;117m",
        "electric":     "\033[38;5;45m",
        "plasma":       "\033[38;5;177m",
        "hot_pink":     "\033[38;5;198m",
        "neon_green":   "\033[38;5;46m",
        "dark_cyan":    "\033[38;5;30m",
        "grid":         "\033[38;5;238m",
        "glow":         "\033[38;5;159m",
        "white":        "\033[38;5;255m",
        "dim_white":    "\033[38;5;245m",
        "bg_dark":      "\033[48;5;233m",
        "bg_strip":     "\033[48;5;234m",
    }
    r = c["reset"]
    b = c["bold"]
    d = c["dim"]

    # Top chrome border with corner accents
    print(f"""
{_F['grid']}{d}  ┌──────────────────────────────────────────────────────────────────┐{r}
{_F['grid']}{d}  │{_F['dark_cyan']}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}                                                                  {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['neon_cyan']}{b}     ▄▄▄·  ▄· ▄▌·▄▄▄▄  ▄▄▄ .▄▄▄  {r}                         {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['electric']}{b}    ▐█ ▀█ ▐█▪██▌██▪ ██ ▀▄.▀·▀▄ █· {r}                         {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['ice_blue']}{b}    ▄█▀▀█ ▐█▌▐█▪▐█· ▐█▌▐▀▀▪▄▐▀▀▄  {r}                         {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['neon_blue']}{b}    ▐█ ▪▐▌ ▐█▀·.██. ██ ▐█▄▄▌▐█•█▌ {r}                         {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['plasma']}{b}     ▀  ▀   ▀ • ▀▀▀▀▀•  ▀▀▀ .▀  ▀  {r}                         {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}                                                                  {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['grid']}──────────────────────────────────────────────────────────────{r}  {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}                                                                  {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['hot_pink']}{b}  ◈{r}  {_F['glow']}A U T O N O M O U S{r}   {_F['dim_white']}Engine for{r}   {_F['neon_green']}{b}Development{r}      {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}  {_F['hot_pink']}{b}  ◈{r}  {_F['glow']}R E A S O N I N G{r}     {_F['dim_white']}&&{r}          {_F['neon_green']}{b}Execution{r}       {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}                                                                  {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}     {_F['electric']}{d}┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐{r}     {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}     {_F['electric']}{d}│{_F['neon_cyan']} ◉ TOOLS {_F['electric']}{d}│  │{_F['neon_green']} ◉ AGENT {_F['electric']}{d}│  │{_F['plasma']} ◉ SHELL {_F['electric']}{d}│  │{_F['hot_pink']} ◉ TASKS {_F['electric']}{d}│{r}     {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}     {_F['electric']}{d}└─────────┘  └─────────┘  └─────────┘  └─────────┘{r}     {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}                                                                  {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}     {_F['dim_white']}{d}v{__version__}  ·  local LLM  ·  sandboxed  ·  MIT license{r}     {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{r}                                                                  {_F['grid']}{d}│{r}
{_F['grid']}{d}  │{_F['dark_cyan']}▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{_F['grid']}{d}│{r}
{_F['grid']}{d}  └──────────────────────────────────────────────────────────────────┘{r}
""")


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _gradient_at(position: float, stops: list[str]) -> str:
    """Get color at position (0.0-1.0) along a list of gradient stops."""
    position = max(0.0, min(1.0, position))
    if position >= 1.0:
        return stops[-1]
    segment = position * (len(stops) - 1)
    i = int(segment)
    t = segment - i
    return _lerp_color(stops[i], stops[min(i + 1, len(stops) - 1)], t)


def create_tui_banner(model: str = "default", ver: str = None) -> Text:
    """
    Create a colorful futuristic banner for the TUI.

    Returns a Rich Text object with a horizontal neon gradient across
    block-letter ASCII art.  Designed to be mounted as the first Static
    widget inside a scrollable ChatView so it scrolls away naturally.
    """
    ver = ver or __version__

    art = [
        "  █████╗ ██╗   ██╗██████╗ ███████╗██████╗  ",
        " ██╔══██╗╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗ ",
        " ███████║ ╚████╔╝ ██║  ██║█████╗  ██████╔╝ ",
        " ██╔══██║  ╚██╔╝  ██║  ██║██╔══╝  ██╔══██╗ ",
        " ██║  ██║   ██║   ██████╔╝███████╗██║  ██║ ",
        " ╚═╝  ╚═╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝ ",
    ]

    # Neon gradient:  cyan ➜ electric blue ➜ indigo ➜ purple ➜ magenta ➜ hot pink
    gradient = [
        "#00e5ff",
        "#00b0ff",
        "#2979ff",
        "#5c6bc0",
        "#7c4dff",
        "#aa00ff",
        "#d500f9",
        "#f50057",
    ]

    # Vertical brightness multipliers (top=bright, bottom fades slightly)
    row_brightness = [1.0, 0.95, 0.90, 0.85, 0.80, 0.70]

    banner = Text()
    banner.append("\n")

    max_width = max(len(line) for line in art)

    for row_idx, line in enumerate(art):
        brightness = row_brightness[row_idx] if row_idx < len(row_brightness) else 0.7
        for col_idx, ch in enumerate(line):
            if ch in (" ", "\t"):
                banner.append(ch)
            else:
                pos = col_idx / max(max_width - 1, 1)
                base = _gradient_at(pos, gradient)
                # Apply brightness (scale RGB toward 0)
                r, g, b = _hex_to_rgb(base)
                r = int(r * brightness)
                g = int(g * brightness)
                b = int(b * brightness)
                banner.append(ch, style=f"bold #{r:02x}{g:02x}{b:02x}")
        banner.append("\n")

    # Thin separator
    banner.append("\n")
    sep = "  " + "─" * (max_width - 2)
    for i, ch in enumerate(sep):
        if ch == "─":
            pos = i / max(len(sep) - 1, 1)
            color = _gradient_at(pos, gradient)
            # Dim the separator
            r, g, b = _hex_to_rgb(color)
            banner.append(ch, style=f"#{r // 3:02x}{g // 3:02x}{b // 3:02x}")
        else:
            banner.append(ch)
    banner.append("\n\n")

    # Tagline
    banner.append("  ")
    banner.append("◆ ", style="bold #00e5ff")
    banner.append("AI Agent  ", style="italic #7c7c9a")
    banner.append("for ", style="italic #555570")
    banner.append("Development ", style="italic #5cb870")
    banner.append("& ", style="italic #555570")
    banner.append("Reasoning", style="italic #d4a043")
    banner.append("\n")

    # Info line
    banner.append("    ")
    banner.append(f"v{ver}", style="bold #5cb870")
    banner.append("  ·  ", style="#555570")
    banner.append(model, style="#5eaff5")
    banner.append("  ·  ", style="#555570")
    banner.append("sandboxed", style="#666680")
    banner.append("\n\n")

    return banner


if __name__ == "__main__":
    import sys
    
    # Self-test: print all banner styles
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--compact":
            print_compact_banner()
        elif arg == "--ascii":
            print_ascii_banner()
        elif arg == "--minimal":
            print_minimal_banner()
        elif arg == "--fancy":
            print_fancy_banner("qwen3-coder:latest", __version__)
        elif arg == "--futuristic":
            print_futuristic_banner()
        elif arg == "--rich":
            print_rich_banner()
        elif arg == "--tui":
            console.print(create_tui_banner("qwen3-coder:latest"))
        else:
            print_welcome_banner("qwen2.5-coder:14b", str(Path.cwd()))
    else:
        # Default: show the welcome banner
        print_welcome_banner("qwen2.5-coder:14b", str(Path.cwd()))
