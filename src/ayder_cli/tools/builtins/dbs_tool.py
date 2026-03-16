"""
DBS RAG API client tool for ayder-cli.
"""

from __future__ import annotations

import json
import time
from threading import Lock
import urllib.error
import urllib.request
from typing import Any

from ayder_cli.core.result import ToolError, ToolSuccess

_VALID_MODES = {"md", "sql"}
_HEALTHCHECK_TIMEOUT_SECONDS = 10
_HEALTHCHECK_CACHE_SECONDS = 60
_HEALTHCHECK_PATH = "/health"
_healthcheck_cache: dict[str, float] = {}
_healthcheck_lock = Lock()


def _is_healthcheck_cached(base_url: str) -> bool:
    now = time.monotonic()
    with _healthcheck_lock:
        last_success = _healthcheck_cache.get(base_url)
        return last_success is not None and (now - last_success) < _HEALTHCHECK_CACHE_SECONDS


def _mark_healthcheck_success(base_url: str) -> None:
    with _healthcheck_lock:
        _healthcheck_cache[base_url] = time.monotonic()


def _reset_healthcheck_cache_for_tests() -> None:
    """Reset healthcheck cache. Test-only helper."""
    with _healthcheck_lock:
        _healthcheck_cache.clear()


def _ensure_healthcheck(base_url: str) -> None:
    if _is_healthcheck_cached(base_url):
        return

    health_url = f"{base_url.rstrip('/')}{_HEALTHCHECK_PATH}"
    req = urllib.request.Request(url=health_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_HEALTHCHECK_TIMEOUT_SECONDS):
            _mark_healthcheck_success(base_url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError("dbs_tool not available try again later") from e


def _call_api(base_url: str, mode: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/search/{mode}"
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to {url}: {e.reason}") from e

    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Non-JSON response from {url}: {body[:400]}") from e


def _to_markdown(mode: str, response: dict[str, Any]) -> str:
    lines = [
        "# DBS RAG Query Response",
        "",
        f"**Mode:** `{mode}`",
        f"**Query:** {response.get('query', '')}",
        "",
    ]
    results = response.get("results", [])
    if not isinstance(results, list) or not results:
        lines.append("_No results._")
        return "\n".join(lines)

    lines.append(f"## Results ({len(results)})")
    lines.append("")
    for i, item in enumerate(results, start=1):
        chunk = item.get("chunk", {}) if isinstance(item, dict) else {}
        lines.append(f"### {i}. {chunk.get('id', 'unknown')}")
        lines.append(f"- score: `{item.get('score', 'n/a')}`")
        lines.append(f"- distance: `{item.get('distance', 'n/a')}`")
        lines.append(f"- is_fts_match: `{item.get('is_fts_match', 'n/a')}`")
        lines.append(f"- source: `{chunk.get('source', 'n/a')}`")
        text = str(chunk.get("text", "")).strip()
        if text:
            lines.append("- text:")
            lines.append("```")
            lines.append(text)
            lines.append("```")
        extra_keys = [
            k for k in ("raw_query", "execution_time_ms", "calls", "content_hash") if k in chunk
        ]
        for key in extra_keys:
            lines.append(f"- {key}: `{chunk[key]}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def dbs_tool(
    query: str,
    mode: str,
    url: str = "http://127.0.0.1:8000",
    limit: int | None = None,
    source_filter: str | None = None,
    min_time: float | None = None,
    timeout_seconds: int = 60,
) -> str:
    """Query dbs-vector RAG API for md/sql retrieval and return formatted results."""
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in _VALID_MODES:
        return ToolError("Error: mode must be one of: md, sql", "validation")

    normalized_query = (query or "").strip()
    if not normalized_query:
        return ToolError("Error: query cannot be empty", "validation")

    if not (url.startswith("http://") or url.startswith("https://")):
        return ToolError("Error: url must start with http:// or https://", "validation")

    if timeout_seconds <= 0:
        return ToolError("Error: timeout_seconds must be a positive integer", "validation")

    if normalized_mode == "md" and min_time is not None:
        return ToolError("Error: min_time is only valid with mode='sql'", "validation")

    try:
        _ensure_healthcheck(url)
    except RuntimeError as e:
        return ToolError(f"Error: {e}", "execution")

    payload: dict[str, Any] = {"query": normalized_query}
    if limit is not None:
        payload["limit"] = limit
    if source_filter:
        payload["source_filter"] = source_filter
    if normalized_mode == "sql" and min_time is not None:
        payload["min_time"] = min_time

    try:
        response = _call_api(url, normalized_mode, payload, timeout_seconds)
    except RuntimeError as e:
        return ToolError(f"Error: {e}", "execution")

    return ToolSuccess(_to_markdown(normalized_mode, response))
