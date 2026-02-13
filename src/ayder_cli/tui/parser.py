"""
TUI Parser — model output normalization for the Textual TUI.

This module provides regex-based parsing for various LLM tool call formats,
similar to the CLI parser but tailored for TUI-specific needs like content
stripping for display and think block extraction.
"""

from __future__ import annotations

import json
import re
from typing import List, Dict, Any


class ContentProcessor:
    """Precompiled regex engine for stripping LLM output artifacts.

    Why regex instead of an XML parser?  Model output is *not* valid XML —
    tags are often unclosed, interleaved with prose, or malformed.  A small
    set of compiled patterns is the most reliable (and fastest) approach.

    All patterns are compiled once at class-body evaluation time.
    Use the module-level ``content_processor`` singleton for zero-cost reuse.
    """

    # -- think blocks --------------------------------------------------------
    _RE_THINK_CLOSED = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    _RE_THINK_UNCLOSED = re.compile(r"<think>(.*)", re.DOTALL)
    _RE_THINK_STRIP = re.compile(r"<think>.*?</think>", re.DOTALL)
    _RE_THINK_STRIP_UNCLOSED = re.compile(r"<think>.*", re.DOTALL)

    # -- tool call blocks ----------------------------------------------------
    # Support namespaced tool calls like <minimax:tool_call>...</minimax:tool_call>
    _RE_TOOL_CALL_BLOCK = re.compile(r"<(\w+:)?tool_call>.*?</(\w+:)?tool_call>", re.DOTALL)
    _RE_FUNCTION_BLOCK = re.compile(r"<function=.*?</function>", re.DOTALL)
    # DeepSeek format: <function_calls><invoke>...</invoke></function_calls>
    _RE_FUNCTION_CALLS_BLOCK = re.compile(r"<function_calls>.*?</function_calls>", re.DOTALL)
    _RE_INVOKE_BLOCK = re.compile(r"<invoke.*?</invoke>", re.DOTALL)

    # -- orphaned tags -------------------------------------------------------
    # Support namespaced tool call tags
    _RE_ORPHAN_TOOL_CALL = re.compile(r"</?(\w+:)?tool_call>")
    _RE_ORPHAN_FUNCTION = re.compile(r"</?function[^>]*>")
    # DeepSeek orphaned tags
    _RE_ORPHAN_FUNCTION_CALLS = re.compile(r"</?function_calls\s*>")
    _RE_ORPHAN_INVOKE = re.compile(r"</?invoke[^>]*>")
    _RE_ORPHAN_PARAMETER = re.compile(r"</?parameter[^>]*>")

    # -- JSON tool arrays ----------------------------------------------------
    _RE_JSON_TOOL_ARRAY = re.compile(
        r'\[\s*\{[^}]*"function"\s*:.*?\}\s*\]', re.DOTALL
    )

    # -- whitespace cleanup --------------------------------------------------
    _RE_BLANK_LINES = re.compile(r"\n{3,}")

    # -- regex fallback for malformed JSON -----------------------------------
    _RE_JSON_NAME = re.compile(r'"name"\s*:\s*"([^"]+)"')
    _RE_JSON_ARGS = re.compile(
        r'"arguments"\s*:\s*["\{](.*?)["\}](?:\s*[,}])', re.DOTALL
    )
    _RE_KV_PAIR = re.compile(r'"(\w+)"\s*:\s*"([^"]*)"')

    # -- public API ----------------------------------------------------------

    def extract_think_blocks(self, content: str) -> list[str]:
        """Return a list of non-empty ``<think>`` block texts."""
        blocks = self._RE_THINK_CLOSED.findall(content)
        remaining = self._RE_THINK_CLOSED.sub("", content)
        unclosed = self._RE_THINK_UNCLOSED.findall(remaining)
        blocks.extend(unclosed)
        return [b.strip() for b in blocks if b.strip()]

    def strip_for_display(self, content: str) -> str:
        """Strip all tool/think markup, returning clean display text."""
        text = self._strip_think_blocks(content)
        text = self._strip_tool_call_blocks(text)
        text = self._strip_function_blocks(text)
        text = self._strip_deepseek_blocks(text)
        text = self._strip_orphaned_tags(text)
        text = self._strip_json_tool_arrays(text)
        text = self._collapse_blank_lines(text)
        return text

    def parse_json_tool_calls(self, content: str) -> list[dict]:
        """Parse tool calls from a JSON array in content (model fallback).

        Falls back to regex extraction when ``json.loads`` fails.
        Returns a list of dicts with ``name`` and ``arguments`` keys, or [].
        """
        content = content.strip()
        if not content.startswith("["):
            return []
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return self._regex_extract_json_tool_calls(content)
        if not isinstance(data, list):
            return []
        calls: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            func = item.get("function")
            if not isinstance(func, dict):
                continue
            name = func.get("name")
            if not name:
                continue
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, ValueError):
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
            calls.append({"name": name, "arguments": args})
        return calls

    # -- private helpers (named for readability) -----------------------------

    def _strip_think_blocks(self, text: str) -> str:
        text = self._RE_THINK_STRIP.sub("", text)
        text = self._RE_THINK_STRIP_UNCLOSED.sub("", text)
        return text

    def _strip_tool_call_blocks(self, text: str) -> str:
        return self._RE_TOOL_CALL_BLOCK.sub("", text)

    def _strip_function_blocks(self, text: str) -> str:
        return self._RE_FUNCTION_BLOCK.sub("", text)

    def _strip_deepseek_blocks(self, text: str) -> str:
        """Strip DeepSeek <function_calls> and <invoke> blocks."""
        text = self._RE_FUNCTION_CALLS_BLOCK.sub("", text)
        text = self._RE_INVOKE_BLOCK.sub("", text)
        return text

    def _strip_orphaned_tags(self, text: str) -> str:
        text = self._RE_ORPHAN_TOOL_CALL.sub("", text)
        text = self._RE_ORPHAN_FUNCTION.sub("", text)
        # Strip DeepSeek orphaned tags
        text = self._RE_ORPHAN_FUNCTION_CALLS.sub("", text)
        text = self._RE_ORPHAN_INVOKE.sub("", text)
        text = self._RE_ORPHAN_PARAMETER.sub("", text)
        return text

    def _strip_json_tool_arrays(self, text: str) -> str:
        return self._RE_JSON_TOOL_ARRAY.sub("", text)

    def _collapse_blank_lines(self, text: str) -> str:
        return self._RE_BLANK_LINES.sub("\n\n", text).strip()

    def _regex_extract_json_tool_calls(self, content: str) -> list[dict]:
        """Regex fallback for malformed JSON tool calls."""
        calls: list[dict] = []
        for m in self._RE_JSON_NAME.finditer(content):
            name = m.group(1)
            args: dict = {}
            start = max(0, m.start() - 200)
            end = min(len(content), m.end() + 200)
            chunk = content[start:end]
            arg_match = self._RE_JSON_ARGS.search(chunk)
            if arg_match:
                raw = arg_match.group(1).strip()
                try:
                    args = json.loads("{" + raw + "}")
                except (json.JSONDecodeError, ValueError):
                    for kv in self._RE_KV_PAIR.finditer(raw):
                        args[kv.group(1)] = kv.group(2)
            calls.append({"name": name, "arguments": args})
        return calls


# Module-level singleton — compiled once, reused everywhere.
content_processor = ContentProcessor()


# -- Convenience functions for backward compat -------------------------------

def extract_think_blocks(content: str) -> list[str]:
    """Extract <think> blocks from content."""
    return content_processor.extract_think_blocks(content)


def strip_for_display(content: str) -> str:
    """Strip tool/think markup for display."""
    return content_processor.strip_for_display(content)


def parse_json_tool_calls(content: str) -> list[dict]:
    """Parse JSON tool calls from content."""
    return content_processor.parse_json_tool_calls(content)


def has_custom_tool_calls(content: str) -> bool:
    """Check if content contains custom tool call markers.
    
    Detects:
    - Standard: <function=...>
    - Wrapped: <tool_call> (including namespaced like <minimax:tool_call>)
    - DeepSeek: <function_calls> or <invoke
    """
    if not content:
        return False
    return (
        "<function=" in content
        or re.search(r"<(\w+:)?tool_call>", content) is not None
        or "<function_calls>" in content
        or "<invoke" in content
    )
