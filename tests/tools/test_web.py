"""Tests for web fetching tool."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from curl_cffi.requests import Cookies
from curl_cffi.requests.exceptions import RequestException

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins import web
from ayder_cli.tools.builtins.web import fetch_web


@pytest.fixture(autouse=True)
def _reset_cookies():
    web._reset_cookie_jar_for_tests()
    yield
    web._reset_cookie_jar_for_tests()


def _mock_session(
    response: Mock | None = None, side_effect: Exception | None = None
) -> MagicMock:
    session = MagicMock()
    session.__enter__.return_value = session
    session.cookies = Cookies()
    session.request.return_value = response
    session.request.side_effect = side_effect
    return session


def test_fetch_web_defaults_to_get():
    response = Mock(
        status_code=200,
        reason="OK",
        url="https://example.com",
        headers={"content-type": "text/plain"},
        text="hello world",
        cookies=Cookies(),
    )
    session = _mock_session(response=response)

    with patch("ayder_cli.tools.builtins.web.Session", return_value=session):
        result = fetch_web("https://example.com")

    assert isinstance(result, ToolSuccess)
    assert "Method: GET" in result
    assert "Status: 200 OK" in result
    assert "hello world" in result
    session.request.assert_called_once_with(
        "GET",
        "https://example.com",
        headers=None,
        data=None,
        timeout=30,
        allow_redirects=True,
    )


def test_fetch_web_falls_back_to_standard_reason():
    response = Mock(
        status_code=200,
        reason="",
        url="https://example.com",
        headers={"content-type": "text/plain"},
        text="hello world",
        cookies=Cookies(),
    )
    session = _mock_session(response=response)

    with patch("ayder_cli.tools.builtins.web.Session", return_value=session):
        result = fetch_web("https://example.com")

    assert "Status: 200 OK" in result


def test_fetch_web_omits_empty_reason_for_unknown_status():
    response = Mock(
        status_code=799,
        reason="",
        url="https://example.com",
        headers={"content-type": "text/plain"},
        text="hello world",
        cookies=Cookies(),
    )
    session = _mock_session(response=response)

    with patch("ayder_cli.tools.builtins.web.Session", return_value=session):
        result = fetch_web("https://example.com")

    status_line = next(line for line in result.splitlines() if line.startswith("Status:"))
    assert status_line == "Status: 799"


def test_fetch_web_supports_post_with_body_and_headers():
    response = Mock(
        status_code=201,
        reason="Created",
        url="https://example.com/api",
        headers={"content-type": "application/json"},
        text='{"ok":true}',
        cookies=Cookies(),
    )
    session = _mock_session(response=response)

    with patch("ayder_cli.tools.builtins.web.Session", return_value=session):
        result = fetch_web(
            "https://example.com/api",
            method="post",
            headers={"Authorization": "Bearer token"},
            body='{"name":"ayder"}',
        )

    assert isinstance(result, ToolSuccess)
    assert "Method: POST" in result
    session.request.assert_called_once_with(
        "POST",
        "https://example.com/api",
        headers={"Authorization": "Bearer token"},
        data='{"name":"ayder"}',
        timeout=30,
        allow_redirects=True,
    )


def test_fetch_web_head_omits_body():
    response = Mock(
        status_code=200,
        reason="OK",
        url="https://example.com",
        headers={"content-type": "text/html"},
        text="this should not appear",
        cookies=Cookies(),
    )
    session = _mock_session(response=response)

    with patch("ayder_cli.tools.builtins.web.Session", return_value=session):
        result = fetch_web("https://example.com", method="HEAD")

    assert "Body: (omitted for HEAD request)" in result
    assert "this should not appear" not in result


def test_fetch_web_rejects_invalid_method():
    result = fetch_web("https://example.com", method="TRACE")
    assert isinstance(result, ToolError)
    assert result.category == "validation"
    assert "method must be one of" in result


def test_fetch_web_handles_request_errors():
    session = _mock_session(side_effect=RequestException("network failure"))

    with patch("ayder_cli.tools.builtins.web.Session", return_value=session):
        result = fetch_web("https://example.com")

    assert isinstance(result, ToolError)
    assert result.category == "execution"
    assert "Error fetching URL" in result


def test_fetch_web_persists_session_cookies_across_calls():
    first_response = Mock(
        status_code=200,
        reason="OK",
        url="https://example.com/login",
        headers={"content-type": "text/plain"},
        text="logged in",
        cookies=Cookies({"sessionid": "abc123"}),
    )
    second_response = Mock(
        status_code=200,
        reason="OK",
        url="https://example.com/me",
        headers={"content-type": "text/plain"},
        text="profile",
        cookies=Cookies(),
    )

    first_session = _mock_session(response=first_response)
    second_session = _mock_session(response=second_response)
    first_session.cookies = Cookies({"sessionid": "abc123"})

    with patch(
        "ayder_cli.tools.builtins.web.Session",
        side_effect=[first_session, second_session],
    ) as session_factory:
        fetch_web("https://example.com/login")
        fetch_web("https://example.com/me")

    second_call_kwargs = session_factory.call_args_list[1].kwargs
    persisted_cookies = second_call_kwargs.get("cookies")
    assert isinstance(persisted_cookies, Cookies)
    assert persisted_cookies.get("sessionid") == "abc123"
