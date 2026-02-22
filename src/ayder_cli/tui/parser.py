"""TUI parser — re-exports from unified ContentProcessor.

All logic lives in ``ayder_cli.parser.ContentProcessor``.
Import directly from ``ayder_cli.parser`` in new code.
"""

from ayder_cli.parser import (
    content_processor,
    ContentProcessor,
)

# Backward-compatible function aliases (existing callers work without change)
extract_think_blocks = content_processor.extract_think_blocks
strip_for_display = content_processor.strip_for_display
parse_json_tool_calls = content_processor.parse_json_tool_calls
has_custom_tool_calls = content_processor.has_tool_calls

__all__ = [
    "content_processor",
    "ContentProcessor",
    "extract_think_blocks",
    "strip_for_display",
    "parse_json_tool_calls",
    "has_custom_tool_calls",
]
