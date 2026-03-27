"""Central keybinding registry for the TUI.

Single source of truth for all keybindings. The help modal
reads from this at render time — add new bindings here and
they automatically appear in Ctrl+H help.
"""

KEYBINDING_REGISTRY: list[tuple[str, str, str]] = [
    # (key_display, description, category)
    # Navigation
    ("Ctrl+PgUp/PgDn", "Scroll chat line", "Navigation"),
    ("PgUp/PgDn", "Scroll chat page", "Navigation"),
    ("Home/End", "Top/Bottom of chat", "Navigation"),
    # Chat
    ("Enter", "Send message", "Chat"),
    ("Shift+Enter", "New line", "Chat"),
    ("\u2191/\u2193", "Command history", "Chat"),
    ("Tab", "Complete /command", "Chat"),
    # Panels
    ("Ctrl+O", "Toggle Tools panel", "Panels"),
    ("Ctrl+T", "Toggle Thinking", "Panels"),
    ("Ctrl+G", "Toggle Agents panel", "Panels"),
    # General
    ("Ctrl+L", "Clear chat", "General"),
    ("Ctrl+X", "Cancel generation", "General"),
    ("Ctrl+H", "Show help", "General"),
    ("Ctrl+Q", "Quit", "General"),
]

_CATEGORY_ORDER = ["Navigation", "Chat", "Panels", "General"]


def get_keybindings_by_category() -> dict[str, list[tuple[str, str]]]:
    """Return keybindings grouped by category in display order.

    Returns:
        Ordered dict of {category: [(key_display, description), ...]}.
    """
    grouped: dict[str, list[tuple[str, str]]] = {c: [] for c in _CATEGORY_ORDER}
    for key, desc, cat in KEYBINDING_REGISTRY:
        grouped[cat].append((key, desc))
    return grouped
