"""
Web fetching tools for ayder-cli.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from threading import Lock
from typing import Any

import httpx

from ayder_cli.core.result import ToolError, ToolSuccess

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_COOKIE_JAR = httpx.Cookies()
_COOKIE_LOCK = Lock()


def _normalize_headers(headers: Mapping[str, str] | None) -> dict[str, str] | None:
    if headers is None:
        return None
    if not isinstance(headers, Mapping):
        raise ValueError("headers must be an object with string keys and values")
    return {str(k): str(v) for k, v in headers.items()}


def _snapshot_cookies() -> httpx.Cookies:
    with _COOKIE_LOCK:
        return httpx.Cookies(_COOKIE_JAR)


def _merge_cookies(source: Any) -> None:
    if source is None:
        return
    if isinstance(source, httpx.Cookies):
        cookies: Any = source
    elif isinstance(source, Mapping):
        cookies = {str(k): str(v) for k, v in source.items()}
    elif hasattr(source, "items"):
        cookies = {str(k): str(v) for k, v in source.items()}
    else:
        return
    with _COOKIE_LOCK:
        _COOKIE_JAR.update(cookies)


def _reset_cookie_jar_for_tests() -> None:
    """Reset persisted cookie jar. Test-only helper."""
    with _COOKIE_LOCK:
        _COOKIE_JAR.clear()


async def _fetch_web_async(
    *,
    url: str,
    method: str,
    headers: dict[str, str] | None,
    body: str | None,
    timeout_seconds: int,
    follow_redirects: bool,
) -> httpx.Response:
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=follow_redirects,
        cookies=_snapshot_cookies(),
    ) as client:
        response = await client.request(
            method=method, url=url, headers=headers, content=body or None
        )
        _merge_cookies(getattr(client, "cookies", None))
        _merge_cookies(getattr(response, "cookies", None))
        return response


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
        response = asyncio.run(
            _fetch_web_async(
                url=url,
                method=normalized_method,
                headers=normalized_headers,
                body=body,
                timeout_seconds=timeout_seconds,
                follow_redirects=follow_redirects,
            )
        )

        lines = [
            "=== WEB FETCH RESULT ===",
            f"Method: {normalized_method}",
            f"URL: {url}",
            f"Final URL: {response.url}",
            f"Status: {response.status_code} {response.reason_phrase}",
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
    except httpx.RequestError as e:
        return ToolError(f"Error fetching URL: {e}", "execution")
    except Exception as e:
        return ToolError(f"Error during fetch_web: {e}", "execution")
