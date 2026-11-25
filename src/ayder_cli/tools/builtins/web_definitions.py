"""
Tool definitions for web operations.

Tools: fetch_web
"""

from typing import Tuple

from ..definition import ToolDefinition, parallel_safe_when

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="fetch_web",
        description=(
            "Fetch a URL over HTTP(S) and return response details and text content. "
            "HTML is returned as extracted text; parse=false returns the raw body "
            "and links=true keeps link URLs. impersonate=chrome sends a Chrome "
            "browser identity, impersonate=none a plain client identity. Cookies "
            "persist across fetch_web calls within the same process."
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
                "impersonate": {
                    "type": "string",
                    "enum": ["chrome", "none"],
                    "description": "Chrome profile or no profile (default: chrome).",
                },
                "parse": {
                    "type": "boolean",
                    "description": "Extract readable text from HTML (default: true).",
                },
                "links": {
                    "type": "boolean",
                    "description": "Include link URLs in extracted text (default: false).",
                },
            },
            "required": ["url"],
        },
        permission="http",
        parallel_safe=parallel_safe_when("method", "GET", "HEAD", "OPTIONS", default="GET"),
        safe_mode_blocked=True,
    ),
)
