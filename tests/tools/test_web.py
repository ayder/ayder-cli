"""Tests for web fetching tool."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from curl_cffi.requests import Cookies
from curl_cffi.requests.exceptions import RequestException

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins import web
from ayder_cli.tools.builtins.web import fetch_web
from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME
from ayder_cli.version import __version__

_HTML_PAGE = (
    "<html><head><title>Shop</title><style>p{color:red}</style></head>"
    "<body><script>var x=1</script><p>Hello</p><div>Second   line</div></body></html>"
)


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


@pytest.fixture
def impersonation_session_factory():
    response = Mock(
        status_code=200,
        reason="OK",
        url="https://example.com",
        headers={"content-type": "text/plain"},
        text="hello world",
        cookies=Cookies(),
    )
    session = _mock_session(response=response)
    with patch("ayder_cli.tools.builtins.web.Session", return_value=session) as factory:
        yield factory


def test_fetch_web_impersonates_chrome_by_default(impersonation_session_factory):
    result = fetch_web("https://example.com")

    request_kwargs = impersonation_session_factory.return_value.request.call_args.kwargs
    assert request_kwargs.get("impersonate") == "chrome"
    assert "Impersonate: chrome" in result.splitlines()


def test_fetch_web_can_disable_impersonation(impersonation_session_factory):
    result = fetch_web("https://example.com", impersonate="none")

    request_kwargs = impersonation_session_factory.return_value.request.call_args.kwargs
    assert "impersonate" in request_kwargs
    assert request_kwargs["impersonate"] is None
    assert request_kwargs["headers"] == {"User-Agent": f"ayder-cli/{__version__}"}
    assert "Impersonate: none" in result.splitlines()


def test_fetch_web_preserves_caller_user_agent(impersonation_session_factory):
    fetch_web("https://example.com", impersonate="none", headers={"user-agent": "probe/1"})

    request_kwargs = impersonation_session_factory.return_value.request.call_args.kwargs
    assert request_kwargs["headers"] == {"user-agent": "probe/1"}


def test_fetch_web_rejects_unknown_impersonation(impersonation_session_factory):
    result = fetch_web("https://example.com", impersonate="firefox")

    assert isinstance(result, ToolError)
    assert result.category == "validation"
    assert "chrome" in result and "none" in result
    impersonation_session_factory.assert_not_called()


def test_fetch_web_definition_declares_impersonation():
    properties = TOOL_DEFINITIONS_BY_NAME["fetch_web"].parameters["properties"]

    assert "impersonate" in properties
    assert properties["impersonate"]["enum"] == ["chrome", "none"]


@pytest.fixture
def web_response():
    response = Mock(
        status_code=200,
        reason="OK",
        url="https://example.com",
        headers={"content-type": "text/html"},
        cookies=Cookies(),
    )
    session = _mock_session(response=response)
    with patch("ayder_cli.tools.builtins.web.Session", return_value=session):
        yield response


def _body_lines(result: str) -> list[str]:
    return result.split("\n\n", 1)[1].splitlines()[:-1]


def test_fetch_web_parses_html_by_default(web_response):
    web_response.headers = {"content-type": "text/html; charset=utf-8"}
    web_response.text = _HTML_PAGE

    result = fetch_web("https://example.com")

    body_heading, *body_lines = _body_lines(result)
    assert body_lines[0] == "Shop"
    assert "Hello" in body_lines
    assert "Second line" in body_lines
    body = "\n".join(body_lines)
    assert "var x=1" not in body
    assert "color:red" not in body
    text_length = len("Shop\nHello\nSecond line")
    assert body_heading == (
        f"Body ({text_length} chars, text extracted from {len(_HTML_PAGE)} chars of HTML):"
    )


@pytest.mark.parametrize("tag", ["script", "style", "noscript", "template", "svg", "iframe"])
def test_fetch_web_omits_hidden_html(web_response, tag):
    web_response.text = f"<p>keep</p><{tag}>drop-me</{tag}>"

    result = fetch_web("https://example.com")

    body = "\n".join(_body_lines(result)[1:])
    assert "keep" in body
    assert "drop-me" not in body


def test_fetch_web_parses_xhtml(web_response):
    web_response.headers = {"content-type": "application/xhtml+xml"}
    web_response.text = "<p>Hello</p>"

    result = fetch_web("https://example.com")

    assert "<p>" not in "\n".join(_body_lines(result)[1:])


def test_fetch_web_decodes_html_references(web_response):
    web_response.text = "<p>a &amp; b&nbsp;&#169;  c</p>"

    result = fetch_web("https://example.com")

    assert "a & b © c" in _body_lines(result)[1:]


def test_fetch_web_recovers_malformed_html(web_response):
    web_response.text = "<p>one<p>two<div>three</span>"

    result = fetch_web("https://example.com")

    assert isinstance(result, ToolSuccess)
    body_lines = _body_lines(result)[1:]
    assert body_lines == ["one", "two", "three"]
    assert "<" not in "\n".join(body_lines)


@pytest.mark.parametrize(
    "invalid_html",
    [
        pytest.param("<![foo [x]]>", id="unknown-marked-section"),
        pytest.param("&#" + "9" * 5000 + ";", id="oversized-decimal-reference"),
    ],
)
def test_fetch_web_preserves_text_recovered_before_parser_error(web_response, invalid_html):
    web_response.text = f"<p>before</p>{invalid_html}<p>after</p>"

    result = fetch_web("https://example.com")

    assert isinstance(result, ToolSuccess)
    assert _body_lines(result)[1:] == ["before"]


def test_fetch_web_truncates_after_html_extraction(web_response):
    text = "a" * 300
    web_response.text = f"<script>{'x' * 5000}</script><p>{text}</p>"

    result = fetch_web("https://example.com", max_content_chars=100)

    _, *body_and_note = _body_lines(result)
    assert body_and_note[:-2] == [text[:100]]
    assert body_and_note[-1] == "[Content truncated to 100 characters.]"


def test_fetch_web_preserves_html_when_parse_is_false(web_response):
    web_response.headers = {"content-type": "text/html; charset=utf-8"}
    web_response.text = _HTML_PAGE

    result = fetch_web("https://example.com", parse=False)

    assert _body_lines(result) == [f"Body ({len(_HTML_PAGE)} chars):", _HTML_PAGE]


def test_fetch_web_preserves_json(web_response):
    web_response.headers = {"content-type": "application/json"}
    web_response.text = '{"html": "<p>hi</p>"}'

    result = fetch_web("https://example.com")

    assert _body_lines(result)[1:] == [web_response.text]


def test_fetch_web_preserves_body_without_content_type(web_response):
    web_response.headers = {}
    web_response.text = "<p>Hello</p>"

    result = fetch_web("https://example.com")

    assert _body_lines(result)[1:] == [web_response.text]


def test_fetch_web_definition_declares_parse():
    properties = TOOL_DEFINITIONS_BY_NAME["fetch_web"].parameters["properties"]

    assert "parse" in properties
    assert properties["parse"]["type"] == "boolean"


@pytest.fixture
def linked_web_response(web_response):
    web_response.url = "https://shop.example/list/page2"
    web_response.text = (
        '<a href="p/1">Item one</a> <a href="https://other.example/x">Ext</a>'
    )
    return web_response


def test_fetch_web_renders_links_relative_to_final_url(linked_web_response):
    result = fetch_web("https://shop.example/go/start", links=True)

    body = "\n".join(_body_lines(result)[1:])
    assert "[Item one](https://shop.example/list/p/1)" in body
    assert "[Ext](https://other.example/x)" in body


def test_fetch_web_keeps_link_text_when_links_are_disabled(linked_web_response):
    result = fetch_web("https://shop.example/go/start", links=False)

    body = "\n".join(_body_lines(result)[1:])
    assert "Item one" in body
    assert "p/1" not in body


def test_fetch_web_keeps_plain_text_for_anchor_without_href(web_response):
    web_response.text = '<a name="top">Top</a>'

    result = fetch_web("https://example.com", links=True)

    body = "\n".join(_body_lines(result)[1:])
    assert "Top" in body
    assert "[" not in body


def test_fetch_web_definition_declares_links():
    properties = TOOL_DEFINITIONS_BY_NAME["fetch_web"].parameters["properties"]

    assert "links" in properties
    assert properties["links"]["type"] == "boolean"


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
        impersonate="chrome",
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
        impersonate="chrome",
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
