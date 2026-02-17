"""
Schema-driven ToolDefinition — single source of truth for all tool metadata.

Every tool's schema, permissions, aliases, path parameters, terminal/safe-mode
flags, and description template live in one frozen dataclass.  All existing
constants (tools_schema, TOOL_PERMISSIONS, PARAMETER_ALIASES, PATH_PARAMETERS,
TERMINAL_TOOLS) are generated from TOOL_DEFINITIONS at import time.
"""

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolDefinition:
    """Immutable definition of a single tool."""

    # ---- identity ----
    name: str
    description: str
    parameters: Dict[str, Any]  # OpenAI "parameters" object

    # ---- permission & flags ----
    permission: str = "r"  # "r", "w", "x", or "http"
    is_terminal: bool = False
    safe_mode_blocked: bool = False

    # ---- UI ----
    description_template: Optional[str] = None

    # ---- implementation reference ----
    func_ref: str = ""  # "module.path:function_name" for auto-registration

    # ---- parameter normalisation helpers ----
    parameter_aliases: Tuple[Tuple[str, str], ...] = ()  # ((alias, canonical), ...)
    path_parameters: Tuple[str, ...] = ()  # parameter names resolved via ProjectContext

    def to_openai_schema(self) -> Dict[str, Any]:
        """Return the OpenAI function-calling dict for this tool."""
        func: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
        if self.description_template is not None:
            func["description_template"] = self.description_template
        return {"type": "function", "function": func}

# ---------------------------------------------------------------------------
# Auto-Discovery System
# ---------------------------------------------------------------------------


def _discover_definitions() -> Tuple["ToolDefinition", ...]:
    """
    Auto-discover all tool definitions from *_definitions.py modules.
    
    Discovery Rules:
    - Scans all modules in ayder_cli.tools package
    - Loads any module ending with '_definitions'
    - Extracts TOOL_DEFINITIONS tuple from each module
    - Validates for duplicates and required tools
    
    Safety Safeguards:
    - Detects and rejects duplicate tool names
    - Validates required core tools are present
    - Gracefully handles import errors
    - Logs discovery process for debugging
    
    Returns:
        Tuple of all discovered ToolDefinition instances
        
    Raises:
        ValueError: If duplicate tool names found
        ImportError: If required core tools are missing
    """
    definitions = []
    discovered_modules = []
    
    # Get the tools package path
    import ayder_cli.tools as tools_package
    package_path = tools_package.__path__
    
    # Iterate through all modules in tools package
    for finder, name, is_pkg in pkgutil.iter_modules(package_path):
        # Only process *_definitions.py files (not packages)
        if name.endswith('_definitions') and not is_pkg:
            try:
                module = importlib.import_module(f'ayder_cli.tools.{name}')
                if hasattr(module, 'TOOL_DEFINITIONS'):
                    module_defs = module.TOOL_DEFINITIONS
                    definitions.extend(module_defs)
                    discovered_modules.append(name)
                    logger.debug(
                        f"Discovered {len(module_defs)} tools from {name}"
                    )
            except ImportError as e:
                logger.warning(f"Failed to import {name}: {e}")
            except Exception as e:
                logger.error(f"Error loading definitions from {name}: {e}")
    
    # Validate: Detect duplicate tool names
    seen: dict[str, str] = {}
    for td in definitions:
        if td.name in seen:
            raise ValueError(
                f"Duplicate tool name '{td.name}' found. "
                f"Previously defined in '{seen[td.name]}', "
                f"duplicate found in current module"
            )
        seen[td.name] = name
    
    # Validate: Ensure required core tools are present
    required_tools = {'list_files', 'read_file', 'write_file', 'run_shell_command'}
    found_tools = {td.name for td in definitions}
    missing = required_tools - found_tools
    if missing:
        raise ImportError(
            f"Required core tools missing: {missing}. "
            f"Ensure filesystem_definitions.py and shell_definitions.py exist."
        )
    
    logger.info(
        f"Auto-discovered {len(definitions)} tool definitions "
        f"from {len(discovered_modules)} modules: {', '.join(discovered_modules)}"
    )
    
    return tuple(definitions)


# ---------------------------------------------------------------------------
# All tool definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Auto-Discovered Tool Definitions
# ---------------------------------------------------------------------------
# Tool definitions are now auto-discovered from *_definitions.py modules.
# See filesystem_definitions.py, search_definitions.py, etc.
# To add a new tool: create a *_definitions.py file with TOOL_DEFINITIONS tuple.

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = _discover_definitions()
TOOL_DEFINITIONS_BY_NAME: Dict[str, ToolDefinition] = {
    td.name: td for td in TOOL_DEFINITIONS
}
