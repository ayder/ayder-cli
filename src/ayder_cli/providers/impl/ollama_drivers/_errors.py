"""Error classification for Ollama server-side tool-extraction bugs."""

from __future__ import annotations

from ollama import ResponseError


class OllamaServerToolBug(Exception):
    """Server-side tool extractor crashed mid-stream."""


# Each entry must reference an upstream Ollama issue so the list stays
# conservative and reviewable. Adding a signature without an issue number
# is forbidden — it risks false positives on transport errors.
_BUG_SIGNATURES: tuple[str, ...] = (
    "xml syntax error",                                    # ollama/ollama#14834
    "unexpected eof",                                      # ollama/ollama#14834
    "failed to parse json: unexpected end of json input",  # ollama/ollama#14570
)


def classify_ollama_error(exc: BaseException) -> BaseException:
    """Return OllamaServerToolBug for known tool-extractor failures.

    Only the curated _BUG_SIGNATURES match. A bare ``EOF (status code: -1)``
    without ``unexpected`` / ``xml`` / ``json`` context is a transport-level
    failure (TCP RST, server crash, OOM kill mid-stream), not the parser bug,
    and is intentionally NOT classified — it propagates as ResponseError so
    the retry layer can decide.
    """
    if not isinstance(exc, ResponseError):
        return exc
    message = str(exc).lower()
    if any(signature in message for signature in _BUG_SIGNATURES):
        return OllamaServerToolBug(str(exc))
    return exc
