"""
Tool schema definitions for ayder-cli.

Generated from ToolDefinition instances — see definition.py for the source of truth.
"""

from ayder_cli.tools.definition import TOOL_DEFINITIONS

# OpenAI function-calling schemas
tools_schema = [td.to_openai_schema() for td in TOOL_DEFINITIONS]

# Permission categories for each tool: r=read, w=write, x=execute, http=web
TOOL_PERMISSIONS = {td.name: td.permission for td in TOOL_DEFINITIONS}
