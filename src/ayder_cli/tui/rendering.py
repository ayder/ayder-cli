"""Safe render helpers for Textual widgets."""

from textual.content import Content
from textual.markup import MarkupError


def markup_or_plain(content: str) -> Content:
    """Render Textual markup, falling back to literal text if it is malformed."""
    try:
        return Content.from_markup(content)
    except MarkupError:
        return Content(content)
