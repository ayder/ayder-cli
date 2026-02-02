"""
Utility functions for tool operations.
"""

import json
from pathlib import Path
from ayder_cli.path_context import ProjectContext


# --- Module-level ProjectContext ---

_default_project_ctx = None


def get_project_context():
    """Get or create the default project context."""
    global _default_project_ctx
    if _default_project_ctx is None:
        _default_project_ctx = ProjectContext(".")
    return _default_project_ctx


def prepare_new_content(fname, args):
    """
    Prepare the content that will be written to a file.
    For write_file: return the content directly.
    For replace_string: read the file and apply the replacement in memory.
    Args can be either a dict or a JSON string.
    """
    try:
        # Handle JSON string arguments
        if isinstance(args, str):
            args = json.loads(args)

        if fname == "write_file":
            return args.get("content", "")

        elif fname == "replace_string":
            file_path = args.get("file_path", "")
            old_string = args.get("old_string", "")
            new_string = args.get("new_string", "")

            if not file_path:
                return ""

            try:
                project = get_project_context()
                abs_path = project.validate_path(file_path)

                with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                return content.replace(old_string, new_string)
            except ValueError as e:
                # Security error - return empty to trigger error in UI
                return ""
            except Exception:
                return ""
        else:
            return ""

    except Exception:
        return ""
