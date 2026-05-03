"""Tests for OllamaServerToolBug classification."""

import pytest
from ollama import ResponseError

from ayder_cli.providers.impl.ollama_drivers._errors import (
    OllamaServerToolBug,
    classify_ollama_error,
)


@pytest.mark.parametrize(
    "message",
    [
        "XML syntax error on line 43: unexpected EOF",
        "xml syntax error: unexpected eof",
        "failed to parse JSON: unexpected end of JSON input",
        "Failed to parse JSON: unexpected end of JSON input at line 5",
    ],
)
def test_known_bug_signatures_classify_as_tool_bug(message):
    err = ResponseError(message)
    out = classify_ollama_error(err)
    assert isinstance(out, OllamaServerToolBug)
    assert message.lower() in str(out).lower()


@pytest.mark.parametrize(
    "message",
    [
        "model not found",
        "context length exceeded",
        "connection refused",
        "rate limit exceeded",
        "internal server error",
        # Bare EOF is a transport failure (TCP RST, server crash, OOM
        # mid-stream), NOT the tool-extractor parser bug. It must
        # propagate as ResponseError so the retry layer decides.
        "EOF (status code: -1)",
        "EOF while reading local fixture",
        "eof",
    ],
)
def test_unrelated_response_errors_pass_through_unchanged(message):
    err = ResponseError(message)
    out = classify_ollama_error(err)
    assert out is err
    assert not isinstance(out, OllamaServerToolBug)


def test_non_response_errors_pass_through_unchanged():
    err = TimeoutError("connection timed out")
    out = classify_ollama_error(err)
    assert out is err
