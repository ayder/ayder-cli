"""
Web fetching tools for ayder-cli.
"""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from threading import Lock
from typing import cast

from curl_cffi.requests import Cookies, Session
from curl_cffi.requests.exceptions import RequestException
from curl_cffi.requests.session import HttpMethod

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.log import get_logger

logger = get_logger("tool")

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_COOKIE_JAR = Cookies()
_COOKIE_LOCK = Lock()


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

        normalized_headers = _normalize_headers(headers)
        with Session(cookies=_snapshot_cookies()) as session:
            response = session.request(
                cast(HttpMethod, normalized_method),
                url,
                headers=normalized_headers,
                data=body or None,
                timeout=timeout_seconds,
                allow_redirects=follow_redirects,
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

        lines = [
            "=== WEB FETCH RESULT ===",
            f"Method: {normalized_method}",
            f"URL: {url}",
            f"Final URL: {response.url}",
            f"Status: {status}",
            f"Content-Type: {response.headers.get('content-type', 'unknown')}",
            "",
        ]

        if normalized_method == "HEAD":
            lines.append("Body: (omitted for HEAD request)")
        else:
            content = response.text or ""
            truncated = content[:max_content_chars]
            lines.extend(
                [
                    f"Body ({len(content)} chars):",
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
