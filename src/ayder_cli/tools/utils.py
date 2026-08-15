"""
Utility functions for tool operations.
"""

import json

from ayder_cli.core.context import ProjectContext
from ayder_cli.log import get_logger

logger = get_logger("tool")


def prepare_new_content(fname, args, project_ctx=None):
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
                project = (
                    project_ctx if project_ctx is not None else ProjectContext(".")
                )
                abs_path = project.validate_path(file_path)

                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return content.replace(old_string, new_string)
            except ValueError as e:
                # Security error - return empty to trigger error in UI
                logger.warning("Security error in replace_string: {}", type(e).__name__)
                return ""
            except (IOError, OSError):
                logger.exception("File error in replace_string")
                return ""

        elif fname == "insert_line":
            file_path = args.get("file_path", "")
            line_number = args.get("line_number", 1)
            content = args.get("content", "")

            if not file_path:
                return ""

            try:
                project = (
                    project_ctx if project_ctx is not None else ProjectContext(".")
                )
                abs_path = project.validate_path(file_path)

                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                idx = min(max(int(line_number) - 1, 0), len(lines))
                if content and not content.endswith("\n"):
                    content += "\n"
                lines.insert(idx, content)
                return "".join(lines)
            except (ValueError, IOError, OSError) as e:
                logger.warning("Error in insert_line preview: {}", type(e).__name__)
                return ""

        elif fname == "delete_line":
            file_path = args.get("file_path", "")
            line_number = args.get("line_number", 1)

            if not file_path:
                return ""

            try:
                project = (
                    project_ctx if project_ctx is not None else ProjectContext(".")
                )
                abs_path = project.validate_path(file_path)

                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                idx = int(line_number) - 1
                if 0 <= idx < len(lines):
                    lines.pop(idx)
                return "".join(lines)
            except (ValueError, IOError, OSError) as e:
                logger.warning("Error in delete_line preview: {}", type(e).__name__)
                return ""

        else:
            return ""

    except json.JSONDecodeError:
        logger.exception("JSON decode error")
        return ""
    except Exception:  # noqa: BLE001 - residual after JSONDecodeError: preview rendering must degrade to an empty string
        logger.opt(exception=True).error("Unexpected error in prepare_new_content")
        return ""
