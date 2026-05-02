"""Error classification for Ollama server-side tool-extraction bugs."""

from __future__ import annotations

from ollama import ResponseError


class OllamaServerToolBug(Exception):
    """Server-side tool extractor crashed mid-stream."""


_BUG_SIGNATURES: tuple[str, ...] = (
    "xml syntax error",
    "unexpected eof",
    "failed to parse json: unexpected end of json input",
)


def classify_ollama_error(exc: BaseException) -> Exception:
    """Return OllamaServerToolBug for known tool-extractor failures."""
    if not isinstance(exc, ResponseError):
        return exc
    message = str(exc).lower()
    if any(signature in message for signature in _BUG_SIGNATURES):
        return OllamaServerToolBug(str(exc))
    if "eof" in message and "status code: -1" in message:
        return OllamaServerToolBug(str(exc))
    return exc
