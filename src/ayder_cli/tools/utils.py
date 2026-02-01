"""
Utility functions for tool operations.
"""

import json
from pathlib import Path


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
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                return content.replace(old_string, new_string)
            except Exception:
                return ""
        else:
            return ""

    except Exception:
        return ""
