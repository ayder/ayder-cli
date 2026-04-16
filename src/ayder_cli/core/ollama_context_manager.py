"""OllamaContextManager — cache-aware, stable-prefix context manager for Ollama.

Implements the ContextManagerProtocol with real token counts from Ollama's
prompt_eval_count, ensuring the KV-cache prefix is never invalidated by
message mutation.

Stable-prefix layout per call to prepare_messages():
    Position 0:   [System Prompt]        — frozen at session start, never changes
    Position 1:   [Compaction Summary]   — only present after compaction
    Position 2-N: [Surviving History]    — append-only, never modified
    Position N+:  [New Messages]         — appended since last LLM call
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from ayder_cli.core.cache_monitor import CacheMonitor
from ayder_cli.core.context_manager import ContextStats
from ayder_cli.providers.impl.ollama_inspector import OllamaInspector

logger = logging.getLogger(__name__)


@dataclass
class OllamaContextStats(ContextStats):
    """Extended statistics for the Ollama context manager."""

    actual_context_length: int = 0
    real_prompt_tokens: int = 0
    real_completion_tokens: int = 0
    cache_hit_ratio: Optional[float] = None  # Phase 3 — CacheMonitor populates


class OllamaContextManager:
    """Cache-aware context manager for Ollama.

    Uses real token counts reported by Ollama (prompt_eval_count / eval_count)
    rather than estimates so that compaction decisions are accurate.

    Rules protecting the KV-cache:
    1. System prompt is frozen once at session start.
    2. Messages passed back to Ollama are append-only — content is never mutated.
    3. Tool results are truncated at insertion time (immutable after that).
    4. Compaction is the only mutation — oldest units replaced with a heuristic
       text summary, never an LLM call.
    """

    def __init__(
        self,
        provisional_context_length: int = 65536,
        reserve_ratio: float = 0.3,
        compaction_threshold: float = 0.7,
        host: str = "http://localhost:11434",
        model: str = "",
    ) -> None:
        self._actual_context_length = provisional_context_length
        self._provisional_context_length = provisional_context_length
        self._reserve_ratio = reserve_ratio
        self._compaction_threshold = compaction_threshold

        self._host = host
        self._model = model
        self._context_detected: bool = False

        self._frozen_system: str | None = None
        self._frozen_schemas: list[dict] = []
        self._system_finalized: bool = False  # True after first prepare_messages

        self._real_prompt_tokens: int = 0
        self._real_completion_tokens: int = 0

        # Timing data stored for CacheMonitor
        self._last_prompt_eval_ns: int = 0
        self._last_eval_ns: int = 0

        self._compaction_count: int = 0
        self._messages_compacted: int = 0

        self._cache_monitor: CacheMonitor = CacheMonitor()

    # ------------------------------------------------------------------
    # Protocol: freeze_system_prompt
    # ------------------------------------------------------------------

    def freeze_system_prompt(
        self, system_content: str, tool_schemas: list[dict]
    ) -> None:
        """Lock the system prefix. Called once at session start."""
        self._frozen_system = system_content
        self._frozen_schemas = list(tool_schemas)
        logger.info(
            "Context: system prompt frozen (%d chars, %d tool schemas, ctx=%d)",
            len(system_content), len(tool_schemas), self._actual_context_length,
        )

    # ------------------------------------------------------------------
    # Lazy initialization: detect real context length
    # ------------------------------------------------------------------

    async def detect_context_length(self) -> None:
        """Query Ollama for the model's real context length.

        Called once at the start of ChatLoop.run(). Falls back to the
        configured num_ctx if the inspector call fails (e.g., Ollama
        unreachable, cloud model without modelinfo).
        """
        if self._context_detected or not self._model:
            return
        self._context_detected = True

        try:
            inspector = OllamaInspector(host=self._host)
            info = await inspector.get_model_info(self._model)

            if info.max_context_length > 0:
                old = self._actual_context_length
                self._actual_context_length = info.max_context_length
                logger.info(
                    "Context: detected real context length from Ollama: %d tokens "
                    "(model=%s, family=%s, quantization=%s) — was %d from config",
                    info.max_context_length, self._model, info.family,
                    info.quantization, old,
                )
            else:
                logger.info(
                    "Context: model '%s' did not report context_length, "
                    "using configured num_ctx=%d",
                    self._model, self._actual_context_length,
                )
        except Exception as e:
            logger.warning(
                "Context: failed to detect context length from Ollama (%s), "
                "falling back to configured num_ctx=%d",
                e, self._actual_context_length,
            )

    # ------------------------------------------------------------------
    # Protocol: prepare_messages
    # ------------------------------------------------------------------

    def prepare_messages(
        self,
        messages: list[dict],
        max_history: int = 0,
    ) -> list[dict]:
        """Return a stable-prefix message list suitable for sending to Ollama.

        The returned list always starts with the frozen system prompt.
        If compaction is triggered, oldest message units are replaced with a
        heuristic summary inserted at position 1.
        """
        # On the FIRST call, finalize the system prompt from the actual message.
        # This captures any content appended after freeze_system_prompt() — such as
        # agent capability prompts that are registered after create_runtime().
        # All subsequent calls use this finalized frozen content for KV-cache stability.
        if not self._system_finalized and messages and messages[0].get("role") == "system":
            actual_content = messages[0].get("content", "")
            if actual_content and actual_content != self._frozen_system:
                logger.info(
                    "Context: system prompt updated on first call (%d → %d chars)",
                    len(self._frozen_system or ""), len(actual_content),
                )
                self._frozen_system = actual_content
            self._system_finalized = True

        # Separate system message from the rest — always use frozen content.
        system_msg: dict | None = None
        if messages and messages[0].get("role") == "system":
            system_msg = {"role": "system", "content": self._frozen_system or messages[0].get("content", "")}
            history = list(messages[1:])
        else:
            system_msg = (
                {"role": "system", "content": self._frozen_system}
                if self._frozen_system is not None
                else None
            )
            history = list(messages)

        if not history:
            return [system_msg] if system_msg else []

        # Compact if threshold exceeded
        compaction_summary: dict | None = None
        if self.should_compact() and history:
            history, compaction_summary = self._compact(history)

        # Apply max_history cap — trim from the head on unit boundaries so
        # assistant+tool_calls stays atomic with its tool_result responses.
        # See opus47.md finding #3.
        if max_history > 0 and len(history) > max_history:
            units = self._group_into_units(history)
            kept: list[list[dict]] = []
            msg_count = 0
            for unit in reversed(units):
                if msg_count + len(unit) > max_history and kept:
                    break
                kept.insert(0, unit)
                msg_count += len(unit)
            history = [m for unit in kept for m in unit]

        # Build the output — stable prefix order
        result: list[dict] = []
        if system_msg:
            result.append(system_msg)
        if compaction_summary is not None:
            result.append(compaction_summary)
        result.extend(history)
        return result

    # ------------------------------------------------------------------
    # Protocol: update_from_response
    # ------------------------------------------------------------------

    def update_from_response(self, usage: dict[str, int]) -> None:
        """Ingest Ollama-reported metrics after each LLM response."""
        self._real_prompt_tokens = usage.get("prompt_tokens", self._real_prompt_tokens)
        self._real_completion_tokens = usage.get(
            "completion_tokens", self._real_completion_tokens
        )
        self._last_prompt_eval_ns = usage.get("prompt_eval_ns", self._last_prompt_eval_ns)
        self._last_eval_ns = usage.get("eval_ns", self._last_eval_ns)

        ceiling = self._actual_context_length
        utilization = (self._real_prompt_tokens / ceiling * 100) if ceiling > 0 else 0
        prompt_speed = (
            f"{self._last_prompt_eval_ns / max(self._real_prompt_tokens, 1):.0f} ns/tok"
            if self._last_prompt_eval_ns else "n/a"
        )
        cache_state = ""
        if usage.get("prompt_eval_ns"):
            status = self._cache_monitor.record(
                prompt_eval_count=usage.get("prompt_tokens", 0),
                prompt_eval_ns=usage.get("prompt_eval_ns", 0),
            )
            cache_state = f", cache={status.state}({status.hit_ratio:.0%})"

        logger.info(
            "Context: %d/%d tokens (%.0f%%), completion=%d, speed=%s%s",
            self._real_prompt_tokens, ceiling, utilization,
            self._real_completion_tokens, prompt_speed, cache_state,
        )

    # ------------------------------------------------------------------
    # Protocol: get_stats
    # ------------------------------------------------------------------

    def get_stats(self) -> OllamaContextStats:
        """Return current context utilization metrics."""
        ceiling = self._actual_context_length
        used = self._real_prompt_tokens
        available = max(0, ceiling - used)
        utilization = (used / ceiling * 100.0) if ceiling > 0 else 0.0

        last_status = self._cache_monitor.last_status
        return OllamaContextStats(
            total_tokens=used,
            available_tokens=available,
            utilization_percent=utilization,
            message_count=0,  # Not tracked separately; caller has the list
            compaction_count=self._compaction_count,
            messages_compacted=self._messages_compacted,
            actual_context_length=ceiling,
            real_prompt_tokens=self._real_prompt_tokens,
            real_completion_tokens=self._real_completion_tokens,
            cache_hit_ratio=last_status.hit_ratio if last_status else None,
        )

    # ------------------------------------------------------------------
    # Protocol: should_compact
    # ------------------------------------------------------------------

    def should_compact(self) -> bool:
        """Return True when real prompt token usage nears the context ceiling.

        Calculation:
            used   = prompt_eval_count from last Ollama response
            budget = ceiling * (1 - reserve_ratio)
            compact when used >= budget * compaction_threshold
        """
        used = self._real_prompt_tokens
        ceiling = self._actual_context_length
        reserve = ceiling * self._reserve_ratio
        budget = ceiling - reserve

        threshold = self._compaction_threshold
        # Adaptive: when cache is hot, push threshold to 0.90 to defer compaction
        # and preserve the KV-cache prefix longer.
        if self._cache_monitor.last_status and self._cache_monitor.last_status.state == "hot":
            threshold = max(threshold, 0.90)

        should = used >= budget * threshold
        if should:
            logger.info(
                "Context: compaction triggered — %d tokens used, "
                "budget=%d, threshold=%.0f%%",
                used, int(budget), threshold * 100,
            )
        return should

    # ------------------------------------------------------------------
    # Class method: from_config
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: Any) -> "OllamaContextManager":
        """Construct from a full application config object."""
        try:
            compaction_threshold = cfg.context_manager.compaction_threshold
        except AttributeError:
            compaction_threshold = 0.7

        host = getattr(cfg, "base_url", "http://localhost:11434")
        # Strip /v1 suffix if present (legacy config)
        if host and host.rstrip("/").endswith("/v1"):
            host = host.rstrip("/")[:-3]

        return cls(
            provisional_context_length=getattr(cfg, "num_ctx", 65536),
            reserve_ratio=cfg.context_manager.reserve_ratio,
            compaction_threshold=compaction_threshold,
            host=host or "http://localhost:11434",
            model=getattr(cfg, "model", ""),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _group_into_units(
        self, messages: list[dict]
    ) -> list[list[dict]]:
        """Group messages into atomic units for compaction.

        A unit is either:
        - A single non-tool-calling message, or
        - An assistant message with tool_calls together with all following
          tool-result messages.
        """
        units: list[list[dict]] = []
        i = 0
        n = len(messages)

        while i < n:
            msg = messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                group = [msg]
                j = i + 1
                while j < n and messages[j].get("role") == "tool":
                    group.append(messages[j])
                    j += 1
                units.append(group)
                i = j
            else:
                units.append([msg])
                i += 1

        return units

    def _heuristic_summarize(self, messages: list[dict]) -> str:
        """Produce a compact text summary of messages without calling an LLM."""
        parts: list[str] = []
        for msg in messages:
            role = msg["role"]
            content = str(msg.get("content", ""))[:200]
            if role == "user":
                parts.append(f"User asked: {content}")
            elif role == "assistant":
                if msg.get("tool_calls"):
                    tools = [
                        tc.get("function", {}).get("name", "?")
                        for tc in msg.get("tool_calls", [])
                    ]
                    parts.append(f"Assistant called: {', '.join(tools)}")
                elif content:
                    parts.append(f"Assistant said: {content}")
            elif role == "tool":
                name = msg.get("name", "unknown")
                parts.append(f"Tool {name} returned result")
        return "[Previous conversation summary]\n" + "\n".join(parts)

    def _compact(
        self, history: list[dict]
    ) -> tuple[list[dict], dict]:
        """Replace the oldest half of message units with a heuristic summary.

        Returns the surviving history and the summary message dict.
        """
        units = self._group_into_units(history)

        # Compact the oldest half of units (at least 1)
        compact_count = max(1, len(units) // 2)
        units_to_compact = units[:compact_count]
        units_to_keep = units[compact_count:]

        # Flatten compacted units for summarisation
        msgs_to_compact = [msg for unit in units_to_compact for msg in unit]
        compacted_msg_count = len(msgs_to_compact)

        summary_text = self._heuristic_summarize(msgs_to_compact)
        summary_msg = {"role": "user", "content": summary_text}

        surviving = [msg for unit in units_to_keep for msg in unit]

        self._compaction_count += 1
        self._messages_compacted += compacted_msg_count

        logger.info(
            "OllamaContextManager: compacted %d messages into summary "
            "(compaction #%d)",
            compacted_msg_count,
            self._compaction_count,
        )

        return surviving, summary_msg
