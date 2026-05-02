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
        "EOF (status code: -1)",
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


def test_bare_eof_without_ollama_stream_status_passes_through():
    err = ResponseError("EOF while reading local fixture", 500)
    out = classify_ollama_error(err)
    assert out is err
