"""Tests for web fetching tool."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins import web
from ayder_cli.tools.builtins.web import fetch_web


@pytest.fixture(autouse=True)
def _reset_cookies():
    web._reset_cookie_jar_for_tests()
    yield
    web._reset_cookie_jar_for_tests()


def _mock_async_client(response: Mock | None = None, side_effect: Exception | None = None):
    client = AsyncMock()
    client.cookies = httpx.Cookies()
    if side_effect is not None:
        client.request.side_effect = side_effect
    else:
        client.request.return_value = response

    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = client
    context_manager.__aexit__.return_value = None
    return context_manager, client


def test_fetch_web_defaults_to_get():
    response = Mock(
        status_code=200,
        reason_phrase="OK",
        url="https://example.com",
        headers={"content-type": "text/plain"},
        text="hello world",
        cookies=httpx.Cookies(),
    )
    cm, client = _mock_async_client(response=response)

    with patch("ayder_cli.tools.builtins.web.httpx.AsyncClient", return_value=cm):
        result = fetch_web("https://example.com")

    assert isinstance(result, ToolSuccess)
    assert "Method: GET" in result
    assert "Status: 200 OK" in result
    assert "hello world" in result
    client.request.assert_awaited_once_with(
        method="GET",
        url="https://example.com",
        headers=None,
        content=None,
    )


def test_fetch_web_supports_post_with_body_and_headers():
    response = Mock(
        status_code=201,
        reason_phrase="Created",
        url="https://example.com/api",
        headers={"content-type": "application/json"},
        text='{"ok":true}',
        cookies=httpx.Cookies(),
    )
    cm, client = _mock_async_client(response=response)

    with patch("ayder_cli.tools.builtins.web.httpx.AsyncClient", return_value=cm):
        result = fetch_web(
            "https://example.com/api",
            method="post",
            headers={"Authorization": "Bearer token"},
            body='{"name":"ayder"}',
        )

    assert isinstance(result, ToolSuccess)
    assert "Method: POST" in result
    client.request.assert_awaited_once_with(
        method="POST",
        url="https://example.com/api",
        headers={"Authorization": "Bearer token"},
        content='{"name":"ayder"}',
    )


def test_fetch_web_head_omits_body():
    response = Mock(
        status_code=200,
        reason_phrase="OK",
        url="https://example.com",
        headers={"content-type": "text/html"},
        text="this should not appear",
        cookies=httpx.Cookies(),
    )
    cm, _ = _mock_async_client(response=response)

    with patch("ayder_cli.tools.builtins.web.httpx.AsyncClient", return_value=cm):
        result = fetch_web("https://example.com", method="HEAD")

    assert "Body: (omitted for HEAD request)" in result
    assert "this should not appear" not in result


def test_fetch_web_rejects_invalid_method():
    result = fetch_web("https://example.com", method="TRACE")
    assert isinstance(result, ToolError)
    assert result.category == "validation"
    assert "method must be one of" in result


def test_fetch_web_handles_request_errors():
    request = httpx.Request("GET", "https://example.com")
    error = httpx.RequestError("network failure", request=request)
    cm, _ = _mock_async_client(side_effect=error)

    with patch("ayder_cli.tools.builtins.web.httpx.AsyncClient", return_value=cm):
        result = fetch_web("https://example.com")

    assert isinstance(result, ToolError)
    assert result.category == "execution"
    assert "Error fetching URL" in result


def test_fetch_web_persists_session_cookies_across_calls():
    first_response = Mock(
        status_code=200,
        reason_phrase="OK",
        url="https://example.com/login",
        headers={"content-type": "text/plain"},
        text="logged in",
        cookies=httpx.Cookies({"sessionid": "abc123"}),
    )
    second_response = Mock(
        status_code=200,
        reason_phrase="OK",
        url="https://example.com/me",
        headers={"content-type": "text/plain"},
        text="profile",
        cookies=httpx.Cookies(),
    )

    cm1, client1 = _mock_async_client(response=first_response)
    cm2, _ = _mock_async_client(response=second_response)
    client1.cookies = httpx.Cookies({"sessionid": "abc123"})

    with patch("ayder_cli.tools.builtins.web.httpx.AsyncClient", side_effect=[cm1, cm2]) as mock_client:
        fetch_web("https://example.com/login")
        fetch_web("https://example.com/me")

    second_call_kwargs = mock_client.call_args_list[1].kwargs
    persisted_cookies = second_call_kwargs.get("cookies")
    assert isinstance(persisted_cookies, httpx.Cookies)
    assert persisted_cookies.get("sessionid") == "abc123"
