"""Tests for dbs_tool."""

import io
from unittest.mock import Mock, patch
import urllib.error

import pytest

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins import dbs_tool as dbs_tool_module
from ayder_cli.tools.builtins.dbs_tool import dbs_tool


def _mock_urlopen_response(payload: str):
    response = Mock()
    response.read.return_value = payload.encode("utf-8")
    context_manager = Mock()
    context_manager.__enter__ = Mock(return_value=response)
    context_manager.__exit__ = Mock(return_value=False)
    return context_manager


@pytest.fixture(autouse=True)
def _reset_healthcheck_cache():
    dbs_tool_module._reset_healthcheck_cache_for_tests()
    yield
    dbs_tool_module._reset_healthcheck_cache_for_tests()


def test_dbs_tool_md_success_formats_markdown():
    health_payload = '{"status":"healthy"}'
    response_payload = (
        '{"query":"find issue","results":[{"chunk":{"id":"c1","text":"hello","source":"docs/a.md"},'
        '"score":0.9,"distance":0.1,"is_fts_match":false}]}'
    )
    with patch(
        "ayder_cli.tools.builtins.dbs_tool.urllib.request.urlopen",
        side_effect=[
            _mock_urlopen_response(health_payload),
            _mock_urlopen_response(response_payload),
        ],
    ):
        result = dbs_tool(query="find issue", mode="md")

    assert isinstance(result, ToolSuccess)
    assert "# DBS RAG Query Response" in result
    assert "**Mode:** `md`" in result
    assert "### 1. c1" in result


def test_dbs_tool_sql_includes_min_time():
    health_payload = '{"status":"healthy"}'
    response_payload = '{"query":"slow query","results":[]}'
    with patch(
        "ayder_cli.tools.builtins.dbs_tool.urllib.request.urlopen",
        side_effect=[
            _mock_urlopen_response(health_payload),
            _mock_urlopen_response(response_payload),
        ],
    ) as mock_urlopen:
        result = dbs_tool(query="slow query", mode="sql", min_time=500.0)

    assert isinstance(result, ToolSuccess)
    request_obj = mock_urlopen.call_args.args[0]
    request_body = request_obj.data.decode("utf-8")
    assert '"min_time": 500.0' in request_body


def test_dbs_tool_rejects_invalid_mode():
    result = dbs_tool(query="x", mode="issues")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_dbs_tool_rejects_empty_query():
    result = dbs_tool(query="   ", mode="md")
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_dbs_tool_rejects_min_time_for_md():
    result = dbs_tool(query="q", mode="md", min_time=1.0)
    assert isinstance(result, ToolError)
    assert result.category == "validation"


def test_dbs_tool_handles_http_error():
    error = urllib.error.HTTPError(
        url="http://127.0.0.1:8000/search/md",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=io.BytesIO(b"boom"),
    )
    with patch(
        "ayder_cli.tools.builtins.dbs_tool.urllib.request.urlopen",
        side_effect=[
            _mock_urlopen_response('{"status":"healthy"}'),
            error,
        ],
    ):
        result = dbs_tool(query="q", mode="md")

    assert isinstance(result, ToolError)
    assert result.category == "execution"
    assert "HTTP 500" in result


def test_dbs_tool_handles_non_json_response():
    with patch(
        "ayder_cli.tools.builtins.dbs_tool.urllib.request.urlopen",
        side_effect=[
            _mock_urlopen_response('{"status":"healthy"}'),
            _mock_urlopen_response("not-json"),
        ],
    ):
        result = dbs_tool(query="q", mode="md")

    assert isinstance(result, ToolError)
    assert result.category == "execution"
    assert "Non-JSON response" in result


def test_dbs_tool_returns_unavailable_when_healthcheck_fails():
    with patch(
        "ayder_cli.tools.builtins.dbs_tool.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ) as mock_urlopen:
        result = dbs_tool(query="q", mode="md")

    assert isinstance(result, ToolError)
    assert result.category == "execution"
    assert "dbs_tool not available try again later" in result
    health_request = mock_urlopen.call_args.args[0]
    assert health_request.full_url.endswith("/health")
    assert mock_urlopen.call_args.kwargs["timeout"] == 10


def test_dbs_tool_caches_successful_healthcheck_for_one_minute():
    with patch(
        "ayder_cli.tools.builtins.dbs_tool.urllib.request.urlopen",
        side_effect=[
            _mock_urlopen_response('{"status":"healthy"}'),
            _mock_urlopen_response('{"query":"q1","results":[]}'),
            _mock_urlopen_response('{"query":"q2","results":[]}'),
        ],
    ) as mock_urlopen:
        result1 = dbs_tool(query="q1", mode="md")
        result2 = dbs_tool(query="q2", mode="md")

    assert isinstance(result1, ToolSuccess)
    assert isinstance(result2, ToolSuccess)
    assert mock_urlopen.call_count == 3
