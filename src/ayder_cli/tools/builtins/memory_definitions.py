"""
Tool definitions for memory operations.

Tools: save_memory, load_memory
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="save_memory",
        description="Save a piece of context or insight to persistent cross-session memory.",
        description_template="Memory will be saved (category: {category})",
        tags=("metadata",),
        func_ref="ayder_cli.tools.builtins.memory:save_memory",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to remember",
                },
                "category": {
                    "type": "string",
                    "description": "Category for organization (e.g., 'architecture', 'decisions', 'bugs')",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags for filtering",
                },
            },
            "required": ["content"],
        },
        permission="w",
        safe_mode_blocked=False,
    ),
    ToolDefinition(
        name="load_memory",
        description="Load saved memories from persistent cross-session storage.",
        description_template="Memories will be loaded",
        tags=("metadata",),
        func_ref="ayder_cli.tools.builtins.memory:load_memory",
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                },
                "query": {
                    "type": "string",
                    "description": "Search query to filter memories by content",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of memories to return (default: 10)",
                },
            },
        },
        permission="r",
    ),
    ToolDefinition(
        name="save_context_memory",
        description="Save a conversation context summary to persistent storage for later retrieval.",
        description_template="Context memory '{name}' will be saved",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.memory:save_context_memory",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name/key for the context memory (e.g., 'session-summary', 'project-state')",
                },
                "content": {
                    "type": "string",
                    "description": "The context content to save",
                },
            },
            "required": ["name", "content"],
        },
        permission="w",
        safe_mode_blocked=False,
    ),
    ToolDefinition(
        name="load_context_memory",
        description="Load a previously saved context memory by name.",
        description_template="Context memory '{name}' will be loaded",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.memory:load_context_memory",
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name/key of the context memory to load",
                },
            },
            "required": ["name"],
        },
        permission="r",
    ),
)