"""
Tool definitions for web operations.

Tools: fetch_web
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="fetch_web",
        description=(
            "Fetch a URL over HTTP(S) and return response details and text content. "
            "Session cookies are persisted across fetch_web calls within the same process."
        ),
        description_template="Web URL '{url}' will be fetched with method '{method}'",
        tags=("http",),
        func_ref="ayder_cli.tools.builtins.web:fetch_web",
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL to fetch (must start with http:// or https://)",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                    "description": "HTTP method to use (default: GET)",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional request headers as key-value pairs",
                    "additionalProperties": {"type": "string"},
                },
                "body": {
                    "type": "string",
                    "description": "Optional raw request body (commonly used with POST/PUT/PATCH)",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)",
                },
                "max_content_chars": {
                    "type": "integer",
                    "description": "Maximum number of response body characters to return (default: 20000)",
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "Whether to follow HTTP redirects (default: true)",
                },
            },
            "required": ["url"],
        },
        permission="http",
        safe_mode_blocked=True,
    ),
)
