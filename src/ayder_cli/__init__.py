"""ayder-cli: Interactive AI agent chat client for local LLMs."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("ayder-cli")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
