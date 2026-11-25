"""
Web fetching tools for ayder-cli.
"""

from __future__ import annotations

from collections.abc import Mapping
from html.parser import HTMLParser
from http import HTTPStatus
from threading import Lock
from typing import cast

from curl_cffi.requests import Cookies, Session
from curl_cffi.requests.exceptions import RequestException
from curl_cffi.requests.session import HttpMethod

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.log import get_logger
from ayder_cli.version import __version__

logger = get_logger("tool")

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_COOKIE_JAR = Cookies()
_COOKIE_LOCK = Lock()
_HTML_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}
_HIDDEN_HTML_TAGS = {"script", "style", "noscript", "template", "svg", "iframe"}
_BLOCK_HTML_TAGS = {
    "address", "article", "aside", "blockquote", "body", "caption", "dd", "details",
    "dialog", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "li", "main", "menu",
    "nav", "ol", "p", "pre", "search", "section", "summary", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "ul",
}


class _HTMLTextParser(HTMLParser):
    """Collect the title and visible text from an HTML response."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_tags: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._line_parts: list[str] = []
        self._lines: list[str] = []

    def _finish_line(self, *, keep_empty: bool = False) -> None:
        line = " ".join("".join(self._line_parts).split())
        self._line_parts.clear()
        if line or (keep_empty and self._lines and self._lines[-1]):
            self._lines.append(line)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN_HTML_TAGS:
            self._hidden_tags.append(tag)
        elif self._hidden_tags:
            return
        elif tag == "title":
            self._in_title = True
        elif not self._in_title:
            if tag == "br":
                self._finish_line(keep_empty=True)
            elif tag in _BLOCK_HTML_TAGS:
                self._finish_line()

    def handle_endtag(self, tag: str) -> None:
        if self._hidden_tags:
            if tag in _HIDDEN_HTML_TAGS and tag in self._hidden_tags:
                while self._hidden_tags.pop() != tag:
                    pass
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_HTML_TAGS and not self._in_title:
            self._finish_line()

    def handle_data(self, data: str) -> None:
        if not self._hidden_tags:
            parts = self._title_parts if self._in_title else self._line_parts
            parts.append(data)

    def get_text(self) -> str:
        self._finish_line()
        title = " ".join("".join(self._title_parts).split())
        body = "\n".join(self._lines).rstrip("\n")
        return "\n".join(part for part in (title, body) if part)


def _html_to_text(html: str, base_url: str, links: bool) -> str:
    # The URL and link setting are reserved for link rendering.
    parser = _HTMLTextParser()
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, ValueError):
        # Malformed declarations and character references can stop HTMLParser.
        pass
    return parser.get_text()


def _normalize_headers(headers: Mapping[str, str] | None) -> dict[str, str] | None:
    if headers is None:
        return None
    if not isinstance(headers, Mapping):
        raise ValueError("headers must be an object with string keys and values")
    return {str(k): str(v) for k, v in headers.items()}


def _snapshot_cookies() -> Cookies:
    with _COOKIE_LOCK:
        return Cookies(_COOKIE_JAR)


def _merge_cookies(cookies: Cookies) -> None:
    with _COOKIE_LOCK:
        _COOKIE_JAR.update(cookies)


def _reset_cookie_jar_for_tests() -> None:
    """Reset persisted cookie jar. Test-only helper."""
    with _COOKIE_LOCK:
        _COOKIE_JAR.clear()


def fetch_web(
    url: str,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: str | None = None,
    timeout_seconds: int = 30,
    max_content_chars: int = 20000,
    follow_redirects: bool = True,
    impersonate: str = "chrome",
    parse: bool = True,
) -> str:
    """Fetch a URL with an HTTP request and return a text summary for the LLM."""
    try:
        normalized_method = (method or "GET").strip().upper()
        if normalized_method not in _ALLOWED_METHODS:
            return ToolError(
                "Error: method must be one of GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS",
                "validation",
            )

        if not (url.startswith("http://") or url.startswith("https://")):
            return ToolError(
                "Error: url must start with http:// or https://", "validation"
            )

        if timeout_seconds <= 0:
            return ToolError(
                "Error: timeout_seconds must be a positive integer", "validation"
            )
        if max_content_chars < 1:
            return ToolError(
                "Error: max_content_chars must be at least 1", "validation"
            )
        if impersonate not in ("chrome", "none"):
            return ToolError(
                "Error: impersonate must be one of chrome, none", "validation"
            )

        normalized_headers = _normalize_headers(headers)
        if impersonate == "none":
            normalized_headers = normalized_headers or {}
            if not any(name.lower() == "user-agent" for name in normalized_headers):
                normalized_headers["User-Agent"] = f"ayder-cli/{__version__}"

        with Session(cookies=_snapshot_cookies()) as session:
            response = session.request(
                cast(HttpMethod, normalized_method),
                url,
                headers=normalized_headers,
                data=body or None,
                timeout=timeout_seconds,
                allow_redirects=follow_redirects,
                impersonate=None if impersonate == "none" else impersonate,
            )
            _merge_cookies(session.cookies)

        status_code = response.status_code
        reason = response.reason
        if not reason:
            try:
                reason = HTTPStatus(status_code).phrase
            except ValueError:
                pass
        status = f"{status_code} {reason}" if reason else str(status_code)

        content_type = response.headers.get("content-type", "unknown")
        lines = [
            "=== WEB FETCH RESULT ===",
            f"Method: {normalized_method}",
            f"URL: {url}",
            f"Final URL: {response.url}",
            f"Status: {status}",
            f"Content-Type: {content_type}",
            f"Impersonate: {impersonate}",
            "",
        ]

        if normalized_method == "HEAD":
            lines.append("Body: (omitted for HEAD request)")
        else:
            content = response.text or ""
            extraction_note = ""
            media_type = content_type.partition(";")[0].strip().lower()
            if parse and media_type in _HTML_MEDIA_TYPES:
                raw_length = len(content)
                content = _html_to_text(content, response.url, links=False)
                extraction_note = f", text extracted from {raw_length} chars of HTML"

            truncated = content[:max_content_chars]
            lines.extend(
                [
                    f"Body ({len(content)} chars{extraction_note}):",
                    truncated,
                ]
            )
            if len(content) > max_content_chars:
                lines.append(
                    f"\n[Content truncated to {max_content_chars} characters.]"
                )

        lines.append("=== END WEB FETCH RESULT ===")
        return ToolSuccess("\n".join(lines))
    except ValueError as e:
        return ToolError(f"Error: {e}", "validation")
    except RequestException as e:
        return ToolError(f"Error fetching URL: {e}", "execution")
    except Exception as e:  # noqa: BLE001 - tool boundary: residual after ValueError and RequestException; any fetch or parse failure becomes a ToolError
        return ToolError(f"Error during fetch_web: {e}", "execution")
