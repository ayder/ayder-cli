"""Ollama model introspection via native SDK.

Wraps ollama.AsyncClient for /api/show and /api/ps calls.
Used by OllamaContextManager to auto-detect context length and cache TTL.
Also exposes a probe_native_tool_calling() helper that empirically tests
whether a given model returns clean msg.tool_calls (native works) or leaks
XML/DSML markup into msg.content (needs IN_CONTENT driver).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ollama import AsyncClient, ResponseError


@dataclass
class ModelInfo:
    """Model metadata from /api/show."""
    name: str = ""
    max_context_length: int = 0
    capabilities: list[str] = field(default_factory=list)
    quantization: str = ""
    family: str = ""


@dataclass
class RuntimeState:
    """Running model state from /api/ps."""
    active_context_length: int = 0
    expires_at: Optional[datetime] = None
    vram_used: int = 0


@dataclass
class NativeToolProbe:
    """Result of probing whether a model handles native tool-calling cleanly.

    Attributes:
        verdict: "native_works" | "leaks_in_content" | "stream_failed" | "no_tool_call"
        reason: human-readable explanation of the verdict
        tool_call_count: number of entries in msg.tool_calls (canonical channel)
        content_markup_found: list of XML/DSML markers detected in msg.content
        content_preview: first 200 chars of msg.content (for inspection)
        raw_error: original exception message if the call failed
    """
    verdict: str
    reason: str
    tool_call_count: int = 0
    content_markup_found: list[str] = field(default_factory=list)
    content_preview: str = ""
    raw_error: str = ""


class OllamaInspector:
    """Queries Ollama for model metadata and runtime state."""

    def __init__(self, host: str = "http://localhost:11434"):
        self._client = AsyncClient(host=host)

    async def get_model_info(self, model: str) -> ModelInfo:
        """Call /api/show to get model context length, capabilities, etc."""
        response = await self._client.show(model)

        # Extract context_length from modelinfo dict.
        # Key is family-prefixed: "qwen2.context_length", "llama.context_length", etc.
        max_ctx = 0
        modelinfo = response.modelinfo or {}
        for key, value in modelinfo.items():
            if key.endswith(".context_length") and isinstance(value, int):
                max_ctx = value
                break

        capabilities = list(response.capabilities) if response.capabilities else []
        details = response.details
        family = getattr(details, "family", "") or ""
        quantization = getattr(details, "quantization_level", "") or ""

        return ModelInfo(
            name=model,
            max_context_length=max_ctx,
            capabilities=capabilities,
            quantization=quantization,
            family=family,
        )

    async def probe_native_tool_calling(
        self,
        model: str,
        prompt: str = "Read the file at /tmp/probe.txt",
        timeout_s: int = 60,
    ) -> NativeToolProbe:
        """Empirically probe whether `model` handles native tool calling.

        Sends a single non-streaming /api/chat request with a minimal tool
        schema, then inspects the response:
          - If msg.tool_calls is populated and msg.content has no XML/DSML
            markup, the model works natively (use generic_native).
          - If msg.content contains <tool_call>, <function_calls>,
            <｜DSML｜tool_calls>, or similar wrappers, the model needs an
            IN_CONTENT driver.
          - If the call raises, the result captures the error so callers can
            decide whether to engage the reactive fallback path.

        This is the canonical "how can we be sure" answer for any new model.
        """
        tools = [{
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from disk",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }]
        try:
            response = await self._client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                tools=tools,
                stream=False,
                options={"num_predict": 200},
            )
        except ResponseError as e:
            return NativeToolProbe(
                verdict="stream_failed",
                reason=f"Ollama returned an error: {e}",
                raw_error=str(e),
            )
        except Exception as e:  # noqa: BLE001 — surface anything else as a probe failure
            return NativeToolProbe(
                verdict="stream_failed",
                reason=f"Probe failed with {type(e).__name__}: {e}",
                raw_error=str(e),
            )

        msg = response.message
        content = msg.content or ""
        tool_calls = list(msg.tool_calls or [])

        # Markup we'd see if the model leaks tool calls into content
        # instead of the canonical msg.tool_calls channel.
        markup_patterns: tuple[tuple[str, str], ...] = (
            (r"<\w*:?tool_call>", "<tool_call>"),
            (r"<function_calls>", "<function_calls>"),
            (r"<tool_calls>", "<tool_calls>"),
            (r"<function=", "<function=...>"),
            (r"<invoke", "<invoke>"),
            ("｜ＤＳＭＬ｜", "｜DSML｜"),
            (r"\|DSML\|", "|DSML|"),
        )
        found = [
            label for pattern, label in markup_patterns
            if re.search(pattern, content)
        ]

        if tool_calls and not found:
            return NativeToolProbe(
                verdict="native_works",
                reason=(
                    f"msg.tool_calls populated ({len(tool_calls)}) and "
                    f"msg.content has no XML/DSML markup."
                ),
                tool_call_count=len(tool_calls),
                content_preview=content[:200],
            )
        if found:
            return NativeToolProbe(
                verdict="leaks_in_content",
                reason=(
                    f"msg.content contains tool-call markup: {found}. "
                    f"Use an IN_CONTENT driver."
                ),
                tool_call_count=len(tool_calls),
                content_markup_found=found,
                content_preview=content[:200],
            )
        return NativeToolProbe(
            verdict="no_tool_call",
            reason=(
                "Model produced neither msg.tool_calls nor recognizable "
                "tool-call markup. Model may be ignoring the tools list; "
                "verdict is inconclusive."
            ),
            content_preview=content[:200],
        )

    async def get_runtime_state(self) -> RuntimeState:
        """Call /api/ps to get running model state."""
        response = await self._client.ps()

        if not response.models:
            return RuntimeState()

        model = response.models[0]
        return RuntimeState(
            active_context_length=model.context_length or 0,
            expires_at=model.expires_at,
            vram_used=int(model.size_vram) if model.size_vram else 0,
        )
