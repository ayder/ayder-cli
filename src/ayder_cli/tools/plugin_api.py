"""Plugin API version constants and compatibility checks."""

PLUGIN_API_VERSION: int = 1
PLUGIN_API_MIN_VERSION: int = 1


def check_api_compatibility(plugin_api_version: int) -> str | None:
    """Check if a plugin's API version is compatible.

    Returns None if compatible, or an error message string if not.
    """
    if plugin_api_version > PLUGIN_API_VERSION:
        return (
            f"Plugin requires API v{plugin_api_version}, "
            f"but ayder supports v{PLUGIN_API_VERSION}. Update ayder."
        )
    if plugin_api_version < PLUGIN_API_MIN_VERSION:
        return (
            f"Plugin targets API v{plugin_api_version}, "
            f"minimum supported is v{PLUGIN_API_MIN_VERSION}. Update the plugin."
        )
    return None
