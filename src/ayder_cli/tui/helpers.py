"""Helper functions for the TUI."""

from rich.text import Text
from ayder_cli.version import __version__


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


def is_tool_blocked_in_safe_mode(tool_name: str, safe_mode: bool) -> bool:
    """
    Check if a tool should be blocked when safe mode is enabled.

    Args:
        tool_name: Name of the tool to check
        safe_mode: Whether safe mode is enabled

    Returns:
        True if the tool should be blocked in safe mode, False otherwise
    """
    if not safe_mode:
        return False

    from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

    tool_def = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    return tool_def.safe_mode_blocked if tool_def else False
