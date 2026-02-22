"""
Unified LLM output parser — ContentProcessor handles all formats.

Responsibilities:
1. Tool call extraction (XML, DeepSeek, DSML, JSON array formats)
2. Think block extraction
3. Display content stripping (removes all markup)
4. Quick format detection
"""

import json
import re
from typing import Any


def _build_single_param_map() -> dict[str, str]:
    """Build a map of single-param tools by analyzing tool schemas.

    Returns a dict mapping tool name to its single required parameter name.
    Only includes tools with exactly one required parameter.
    """
    from ayder_cli.tools.schemas import tools_schema

    single_param_map = {}
    for tool in tools_schema:
        func = tool.get("function", {})
        name = func.get("name")
        params = func.get("parameters", {})
        required = params.get("required", [])
        if name and len(required) == 1:
            single_param_map[name] = required[0]
    return single_param_map


# Auto-generated map of single-param tools from schemas (built at import time)
_SINGLE_PARAM_TOOLS = _build_single_param_map()


class ContentProcessor:
    """Single parser for all LLM output processing.

    Why regex instead of an XML parser?  Model output is *not* valid XML —
    tags are often unclosed, interleaved with prose, or malformed.  A small
    set of compiled patterns is the most reliable (and fastest) approach.

    All patterns are compiled once at class-body evaluation time.
    Use the module-level ``content_processor`` singleton for zero-cost reuse.

    Public API:
        extract_think_blocks(content)  → list[str]
        strip_for_display(content)     → str
        has_tool_calls(content)        → bool
        parse_tool_calls(content)      → list[dict]
        parse_json_tool_calls(content) → list[dict]
    """

    # -- Think blocks --------------------------------------------------------
    _RE_THINK_CLOSED = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    _RE_THINK_UNCLOSED = re.compile(r"<think>(.*)", re.DOTALL)
    _RE_THINK_STRIP = re.compile(r"<think>.*?</think>", re.DOTALL)
    _RE_THINK_STRIP_UNCLOSED = re.compile(r"<think>.*", re.DOTALL)

    # -- Tool call blocks (for stripping display) ----------------------------
    # Support namespaced tool calls like <minimax:tool_call>...</minimax:tool_call>
    _RE_TOOL_CALL_BLOCK = re.compile(
        r"<(\w+:)?tool_call>.*?</(\w+:)?tool_call>", re.DOTALL
    )
    _RE_FUNCTION_BLOCK = re.compile(r"<function=.*?</function>", re.DOTALL)
    # DeepSeek format: <function_calls><invoke>...</invoke></function_calls>
    # Also covers DSML-prefixed variants (｜DSML｜function_calls, etc.)
    _RE_FUNCTION_CALLS_BLOCK = re.compile(
        r"<\uff5c?\uff24?\uff33?\uff2d?\uff2c?\uff5c?function_calls>.*?"
        r"</\uff5c?\uff24?\uff33?\uff2d?\uff2c?\uff5c?function_calls>",
        re.DOTALL,
    )
    _RE_INVOKE_BLOCK = re.compile(
        r"<\uff5c?\uff24?\uff33?\uff2d?\uff2c?\uff5c?invoke.*?"
        r"</\uff5c?\uff24?\uff33?\uff2d?\uff2c?\uff5c?invoke>",
        re.DOTALL,
    )

    # -- Orphaned tags (for stripping display) -------------------------------
    _RE_ORPHAN_TOOL_CALL = re.compile(r"</?(\w+:)?tool_call>")
    _RE_ORPHAN_FUNCTION = re.compile(r"</?function[^>]*>")
    _RE_ORPHAN_FUNCTION_CALLS = re.compile(
        r"</?\uff5c?\uff24?\uff33?\uff2d?\uff2c?\uff5c?function_calls\s*>"
    )
    _RE_ORPHAN_INVOKE = re.compile(
        r"</?\uff5c?\uff24?\uff33?\uff2d?\uff2c?\uff5c?invoke[^>]*>"
    )
    _RE_ORPHAN_PARAMETER = re.compile(
        r"</?\uff5c?\uff24?\uff33?\uff2d?\uff2c?\uff5c?parameter[^>]*>"
    )

    # -- JSON tool arrays (for stripping and parsing) ------------------------
    _RE_JSON_TOOL_ARRAY = re.compile(r'\[\s*\{[^}]*"function"\s*:.*?\}\s*\]', re.DOTALL)
    _RE_JSON_NAME = re.compile(r'"name"\s*:\s*"([^"]+)"')
    _RE_JSON_ARGS = re.compile(
        r'"arguments"\s*:\s*["\{](.*?)["\}](?:\s*[,}])', re.DOTALL
    )
    _RE_KV_PAIR = re.compile(r'"(\w+)"\s*:\s*"([^"]*)"')

    # -- Whitespace cleanup --------------------------------------------------
    _RE_BLANK_LINES = re.compile(r"\n{3,}")

    # -- XML extraction (for parse_tool_calls) -------------------------------
    _RE_FUNC = re.compile(r"<function=(.*?)>(.*?)</function>", re.DOTALL)
    _RE_PARAM = re.compile(r"<parameter=(.*?)>(.*?)</parameter>", re.DOTALL)
    _RE_PARAM_UNCLOSED = re.compile(r"<parameter=(.*?)>(.*)", re.DOTALL)

    # -- Markup normalization (for _normalize_markup) -----------------------
    # Unwrap <tool_call> wrappers (including namespaced variants)
    _RE_TOOL_CALL_WRAPPER = re.compile(
        r"<(\w+:)?tool_call>\s*(.*?)\s*</(\w+:)?tool_call>",
        re.DOTALL,
    )
    # DeepSeek <invoke> extraction
    _RE_INVOKE = re.compile(
        r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', re.DOTALL
    )
    # DeepSeek <parameter name="..."> extraction
    _RE_DS_PARAM = re.compile(
        r'<parameter\s+name="([^"]+)"[^>]*>(.*?)</parameter>', re.DOTALL
    )
    # Strip outer <function_calls> tags
    _RE_FUNCTION_CALLS_STRIP = re.compile(r"</?function_calls\s*>", re.DOTALL)
    # DSML fullwidth prefix: ｜DSML｜
    _RE_DSML_FULLWIDTH = re.compile(r"<(/?)\uff5c\uff24\uff33\uff2d\uff2c\uff5c")
    # DSML ASCII fallback: |DSML|
    _RE_DSML_ASCII = re.compile(r"<(/?)\|DSML\|")

    # =========================================================================
    # Public API
    # =========================================================================

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

    def has_tool_calls(self, content: str) -> bool:
        """Quick presence check — does content contain any tool call format?

        Detects:
        - Standard: <function=...>
        - Wrapped: <tool_call> (including namespaced like <minimax:tool_call>)
        - DeepSeek: <function_calls> or <invoke
        - DeepSeek DSML: ｜DSML｜function_calls or ｜DSML｜invoke
        """
        if not content:
            return False
        return (
            "<function=" in content
            or re.search(r"<(\w+:)?tool_call>", content) is not None
            or "<function_calls>" in content
            or "<invoke" in content
            or "\uff5c\uff24\uff33\uff2d\uff2c\uff5c" in content
            or "|DSML|" in content
        )

    def parse_tool_calls(self, content: str) -> list[dict[str, Any]]:
        """Extract tool calls from any supported LLM output format.

        Routing order:
        1. Normalize markup (DSML markers, <tool_call> wrappers, DeepSeek conversion)
        2. Try XML extraction (<function=name>...</function> patterns)
        3. If no XML results, try JSON array extraction
        4. Return combined results (parse errors included as error dicts)

        Returns list of:
          {"name": "tool_name", "arguments": {...}}
        or on error:
          {"name": "unknown", "arguments": {}, "error": "..."}
        """
        if not content:
            return []
        normalized = self._normalize_markup(content)
        results = self._parse_xml_tool_calls(normalized)
        if not results:
            results = self.parse_json_tool_calls(content)
        return results

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

    # =========================================================================
    # Private: markup normalization
    # =========================================================================

    def _normalize_markup(self, content: str) -> str:
        """Normalize model-specific tool call markup variations.

        1. Strip DSML markers from DeepSeek tags.
        2. Strip outer <tool_call> wrappers (including namespaced variants).
        3. Add missing </function> when block ends with </tool_call>.
        4. Convert DeepSeek <function_calls>/<invoke> to standard format.
        """
        content = self._normalize_dsml(content)
        content = self._RE_TOOL_CALL_WRAPPER.sub(
            lambda m: (
                m.group(2)
                if "</function>" in m.group(2)
                else m.group(2) + "</function>"
            ),
            content,
        )
        content = self._convert_deepseek(content)
        return content

    def _normalize_dsml(self, content: str) -> str:
        """Strip ｜DSML｜ prefix from tags (fullwidth and ASCII variants)."""
        if "\uff5c\uff24\uff33\uff2d\uff2c\uff5c" not in content and "DSML" not in content:
            return content
        content = self._RE_DSML_FULLWIDTH.sub(r"<\1", content)
        content = self._RE_DSML_ASCII.sub(r"<\1", content)
        return content

    def _convert_deepseek(self, content: str) -> str:
        """Convert DeepSeek <function_calls>/<invoke> to standard format.

        DeepSeek format:
            <function_calls>
            <invoke name="func_name">
            <parameter name="param">value</parameter>
            </invoke>
            </function_calls>

        Converts to:
            <function=func_name><parameter=param>value</parameter></function>
        """
        def convert_invoke(match: re.Match) -> str:
            func_name = match.group(1)
            params_block = match.group(2)
            params = []
            for pm in self._RE_DS_PARAM.finditer(params_block):
                param_name = pm.group(1)
                param_value = pm.group(2).strip()
                params.append(f"<parameter={param_name}>{param_value}</parameter>")
            return f"<function={func_name}>{''.join(params)}</function>"

        result = self._RE_INVOKE.sub(convert_invoke, content)
        result = self._RE_FUNCTION_CALLS_STRIP.sub("", result)
        return result

    # =========================================================================
    # Private: XML tool call extraction
    # =========================================================================

    def _parse_xml_tool_calls(self, content: str) -> list[dict[str, Any]]:
        """Extract tool calls from <function=name>...</function> patterns.

        Handles:
        - Standard: <function=name><parameter=key>value</parameter></function>
        - Unclosed parameters: <parameter=key>value (no closing tag)
        - Lazy: <function=name>value</function> (single-param tools only)
        """
        calls = []
        for func_match in self._RE_FUNC.finditer(content):
            func_name = func_match.group(1).strip()
            body = func_match.group(2).strip()

            if not func_name:
                calls.append({
                    "name": "unknown",
                    "arguments": {},
                    "error": "Malformed tool call: function name is empty",
                })
                continue

            param_matches = list(self._RE_PARAM.finditer(body))

            if param_matches:
                # Standard format: closed <parameter=key>value</parameter>
                args = {}
                for pm in param_matches:
                    key = pm.group(1).strip()
                    value = pm.group(2).strip()
                    if key:
                        args[key] = value
                calls.append({"name": func_name, "arguments": args})

            elif "<parameter=" in body:
                # Unclosed parameters: <parameter=key>value (no closing tag)
                unclosed = list(self._RE_PARAM_UNCLOSED.finditer(body))
                if unclosed:
                    args = {}
                    for um in unclosed:
                        key = um.group(1).strip()
                        value = um.group(2).strip()
                        if key:
                            args[key] = value
                    calls.append({"name": func_name, "arguments": args})
                else:
                    calls.append({"name": func_name, "arguments": {}})

            elif body and "<parameter" not in body:
                # Lazy format — infer single parameter name from schema
                inferred = self._infer_parameter_name(func_name)
                if inferred:
                    calls.append({"name": func_name, "arguments": {inferred: body}})
                else:
                    calls.append({
                        "name": func_name,
                        "arguments": {},
                        "error": (
                            f"Missing <parameter> tags. Use: "
                            f"<function={func_name}><parameter=name>value</parameter></function>"
                        ),
                    })
            else:
                # Empty body — valid for no-argument tools
                calls.append({"name": func_name, "arguments": {}})

        return calls

    def _infer_parameter_name(self, func_name: str) -> str:
        """Return the single required parameter for single-param tools."""
        return _SINGLE_PARAM_TOOLS.get(func_name, "")

    # =========================================================================
    # Private: display stripping helpers
    # =========================================================================

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
        text = self._RE_ORPHAN_FUNCTION_CALLS.sub("", text)
        text = self._RE_ORPHAN_INVOKE.sub("", text)
        text = self._RE_ORPHAN_PARAMETER.sub("", text)
        return text

    def _strip_json_tool_arrays(self, text: str) -> str:
        return self._RE_JSON_TOOL_ARRAY.sub("", text)

    def _collapse_blank_lines(self, text: str) -> str:
        return self._RE_BLANK_LINES.sub("\n\n", text).strip()

    # =========================================================================
    # Private: JSON fallback extraction
    # =========================================================================

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


# =============================================================================
# Module-level singleton — compiled once, reused everywhere.
# =============================================================================

content_processor = ContentProcessor()


# =============================================================================
# Backward-compatible module-level functions
# (preserved for existing callers; prefer using content_processor directly)
# =============================================================================


def parse_custom_tool_calls(content: str) -> list[dict[str, Any]]:
    """Parse XML-format tool calls from LLM output.

    Deprecated: use ``content_processor.parse_tool_calls()`` instead.
    """
    return content_processor.parse_tool_calls(content)


def _infer_parameter_name(func_name: str) -> str:
    """Infer parameter for single-param tools only."""
    return _SINGLE_PARAM_TOOLS.get(func_name, "")


def _normalize_dsml_markup(content: str) -> str:
    """Normalize DeepSeek DSML-prefixed tags to standard DeepSeek format."""
    return content_processor._normalize_dsml(content)


def _normalize_tool_call_markup(content: str) -> str:
    """Normalize model-specific tool call markup variations."""
    return content_processor._normalize_markup(content)
