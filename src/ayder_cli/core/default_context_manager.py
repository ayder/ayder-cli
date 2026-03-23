"""DefaultContextManager — concrete implementation for non-Ollama providers.

Extracted from the old context_manager.py monolith. Satisfies the
ContextManager Protocol defined in context_manager.py.

Import note: ContextStats is imported lazily inside get_stats() to avoid
a circular import with context_manager.py (which re-exports this class).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ayder_cli.core.context_manager import ContextStats

logger = logging.getLogger(__name__)


class MessageTier(Enum):
    """Importance tiers for messages."""

    SYSTEM = "system"
    RECENT_USER = "recent_user"
    RECENT_ASSISTANT = "recent_assistant"
    TOOL_RESULT_CRITICAL = "tool_result_critical"
    RECENT_TOOL_RESULT = "recent_tool_result"
    OLD_ASSISTANT = "old_assistant"
    OLD_TOOL_RESULT = "old_tool_result"
    COMPRESSED = "compressed"


class TokenCounter:
    """Estimates token counts with provider-specific optimizations."""

    CHARS_PER_TOKEN = {
        "en": 4.0,
        "code": 3.5,
        "default": 4.0,
    }

    def __init__(self, model: str = "unknown", provider: str = "openai") -> None:
        self.model = model
        self.provider = provider
        self._encoder: Optional[Any] = None
        self._init_encoder()

    def _init_encoder(self) -> None:
        if self.provider not in ("openai", "anthropic"):
            return

        try:
            import tiktoken

            encoding_map = {
                "gpt-4": "cl100k_base",
                "gpt-4o": "o200k_base",
                "gpt-3.5": "cl100k_base",
                "claude": "cl100k_base",
            }

            encoding_name = None
            for prefix, enc in encoding_map.items():
                if prefix in self.model.lower():
                    encoding_name = enc
                    break

            if not encoding_name:
                encoding_name = "cl100k_base"

            self._encoder = tiktoken.get_encoding(encoding_name)
        except ImportError:
            pass

    def estimate(self, obj: Any) -> int:
        if obj is None:
            return 0

        if isinstance(obj, str):
            return self._estimate_string(obj)

        if isinstance(obj, dict):
            if "content" in obj:
                tokens = self._estimate_string(str(obj.get("content", "")))
                tokens += 4  # Role field overhead
                if "tool_calls" in obj:
                    tokens += self._estimate_string(json.dumps(obj["tool_calls"]))
                if "name" in obj:
                    tokens += 2
                return tokens
            return self._estimate_string(json.dumps(obj))

        if isinstance(obj, list):
            return sum(self.estimate(item) for item in obj) + len(obj)

        return self._estimate_string(str(obj))

    def count_messages(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += self.estimate(msg)
            total += 3
        return total

    def _estimate_string(self, text: str) -> int:
        if not text:
            return 0

        if self._encoder is not None:
            try:
                return len(self._encoder.encode(text))
            except Exception:
                pass

        is_code = any(c in text for c in "{}[]();=<>+-*/%&|^~!")
        chars_per_token = (
            self.CHARS_PER_TOKEN["code"] if is_code else self.CHARS_PER_TOKEN["default"]
        )

        return int(len(text) / chars_per_token) + 1

    def count_schema_tokens(self, schemas: list[dict]) -> int:
        return self.estimate(schemas)

    def count_tokens(self, text: str) -> int:
        return self._estimate_string(text)

    def count_message_tokens(self, messages: list[dict]) -> int:
        return self.count_messages(messages)


class DefaultContextManager:
    """Concrete context manager for standard OpenAI-compatible providers.

    Satisfies the ContextManager Protocol. Extracted from the original
    monolithic ContextManager class.
    """

    def __init__(self, config: Any, model: str = "unknown") -> None:
        from ayder_cli.core.config import ContextManagerConfigSection

        if hasattr(config, "context_manager"):
            self._config = config.context_manager
        elif isinstance(config, ContextManagerConfigSection):
            self._config = config
        else:
            max_tokens = getattr(config, "num_ctx", 8192)
            if max_tokens <= 0:
                max_tokens = 8192
            self._config = ContextManagerConfigSection(max_context_tokens=max_tokens)

        provider = getattr(config, "provider", "openai")
        self._counter = TokenCounter(model=model, provider=provider)

        self._messages: List[Dict[str, Any]] = []
        self._message_meta: List[Dict[str, Any]] = []

        self._compressed_count = 0
        self._pruned_count = 0
        self._last_summarization = datetime.now()
        self._cache_valid = False
        self._stats_cache: "ContextStats | None" = None

        # Frozen system prompt data (set via freeze_system_prompt)
        self._frozen_system: str = ""
        self._frozen_schemas: list[dict] = []
        self._system_tokens: int = 0
        self._schema_tokens: int = 0

        # Provider-reported token usage from update_from_response
        self._last_prompt_tokens: int = 0
        self._last_completion_tokens: int = 0
        self._compaction_count: int = 0
        self._messages_compacted: int = 0

    # -- Protocol methods ----------------------------------------------------

    @classmethod
    def from_config(cls, cfg: Any) -> "DefaultContextManager":
        """Create a DefaultContextManager from a full app config object."""
        model = getattr(cfg, "model", "unknown")
        return cls(config=cfg, model=model)

    def freeze_system_prompt(
        self, system_content: str, tool_schemas: list[dict]
    ) -> None:
        """Lock the system prefix. Called once at session start."""
        self._frozen_system = system_content
        self._frozen_schemas = tool_schemas
        self._system_tokens = self._counter.estimate(system_content)
        self._schema_tokens = self._counter.count_schema_tokens(tool_schemas)
        self._cache_valid = False

    def update_from_response(self, usage: dict[str, int]) -> None:
        """Ingest provider-reported metrics after each LLM response.

        Unknown keys (e.g. Ollama's ``prompt_eval_ns``) are silently ignored.
        """
        self._last_prompt_tokens = usage.get("prompt_tokens", self._last_prompt_tokens)
        self._last_completion_tokens = usage.get(
            "completion_tokens", self._last_completion_tokens
        )
        self._cache_valid = False

    def should_compact(self) -> bool:
        """Whether compaction/trimming should be triggered."""
        return self.should_trigger_summarization()

    def get_stats(self) -> "ContextStats":
        """Return current context utilization metrics (base Protocol type)."""
        # Lazy import to avoid circular dependency with context_manager.py
        from ayder_cli.core.context_manager import ContextStats

        if self._cache_valid and self._stats_cache is not None:
            return self._stats_cache

        total = self._calculate_total_tokens()
        available = max(0, self._config.max_context_tokens - total)
        utilization = (total / self._config.max_context_tokens) * 100

        self._stats_cache = ContextStats(
            total_tokens=total,
            available_tokens=available,
            utilization_percent=utilization,
            message_count=len(self._messages),
            compaction_count=self._compaction_count,
            messages_compacted=self._messages_compacted,
        )
        self._cache_valid = True
        return self._stats_cache

    # -- Core logic ----------------------------------------------------------

    @property
    def max_context(self) -> int:
        return self._config.max_context_tokens

    @property
    def reserve(self) -> int:
        return int(self._config.max_context_tokens * self._config.reserve_ratio)

    def count_tokens(self, text: str) -> int:
        """Legacy support."""
        return self._counter.estimate(text)

    def count_message_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Legacy support."""
        return self._counter.count_messages(messages)

    def count_schema_tokens(self, schemas: List[Dict[str, Any]]) -> int:
        """Legacy support."""
        return self._counter.estimate(schemas)

    def prepare_messages(
        self,
        messages: List[Dict[str, Any]],
        system_tokens: int = 0,
        schema_tokens: int = 0,
        max_history: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return a trimmed message list that fits the context budget.

        If freeze_system_prompt() has been called, uses frozen token counts
        instead of the legacy ``system_tokens``/``schema_tokens`` params.
        """
        # Re-sync external list to internal state
        self._messages = []
        self._message_meta = []
        self._cache_valid = False

        for msg in messages:
            self.add_message(msg)

        if not self._messages:
            return []

        # Perform auto compression
        self._auto_compress()

        system_msg = (
            self._messages[0]
            if self._messages and self._messages[0].get("role") == "system"
            else None
        )

        # Use frozen data if available, otherwise fall back to params
        if self._system_tokens or self._schema_tokens:
            effective_system_tokens = self._system_tokens
            effective_schema_tokens = self._schema_tokens
        else:
            system_content = system_msg.get("content", "") if system_msg else ""
            effective_system_tokens = self._calculate_overhead(system_content, None)
            effective_schema_tokens = schema_tokens

        overhead = effective_system_tokens + effective_schema_tokens
        available = self._available_budget(overhead)

        if available <= 0:
            return [system_msg] if system_msg else []

        start_idx = 1 if system_msg else 0
        history_msgs = self._messages[start_idx:]

        units = self._group_into_units(history_msgs)

        result: List[Dict[str, Any]] = []
        used = 0
        messages_count = 0
        for unit in reversed(units):
            if max_history > 0 and messages_count + len(unit) > max_history:
                break

            cost = self._counter.count_messages(unit)
            if used + cost > available:
                break

            result = unit + result
            used += cost
            messages_count += len(unit)

        if result and result[0].get("role") != "user":
            result.insert(
                0,
                {"role": "user", "content": "[... history truncated for context efficiency ...]"},
            )

        return ([system_msg] if system_msg else []) + result

    def truncate_tool_result(self, content: str, max_tokens: int = 2048) -> str:
        """Truncate a tool result. Delegates to module-level utility."""
        from ayder_cli.core.context_manager import truncate_tool_result

        return truncate_tool_result(content, max_chars=max_tokens * 4)

    def add_message(self, message: dict) -> None:
        self._messages.append(dict(message))

        tier = self._assign_tier(message, len(self._messages))
        token_count = self._counter.estimate(message)

        self._message_meta.append(
            {
                "tier": tier,
                "timestamp": datetime.now(),
                "original_length": len(str(message.get("content", ""))),
                "compressed": False,
                "token_count": token_count,
            }
        )
        self._cache_valid = False

    def should_trigger_summarization(self) -> bool:
        if not self._config.enabled:
            return False

        total = self._calculate_total_tokens()
        utilization = total / self._config.max_context_tokens
        return utilization >= self._config.compaction_threshold

    def should_trigger_compression(self) -> bool:
        if not self._config.enabled or not self._config.compress_tool_results:
            return False

        total = self._calculate_total_tokens()
        utilization = total / self._config.max_context_tokens
        return utilization >= self._config.compaction_threshold

    def compress_old_results(self, age_threshold: int | None = None) -> int:
        threshold = (
            age_threshold
            if age_threshold is not None
            else self._config.tool_result_compress_age
        )
        compressed = 0

        for i, (msg, meta) in enumerate(zip(self._messages, self._message_meta)):
            if meta["compressed"]:
                continue

            if msg.get("role") != "tool":
                continue

            age = len(self._messages) - i
            if age <= threshold:
                continue

            content = msg.get("content", "")
            if len(content) > self._config.max_tool_result_length:
                compressed_content = self._compress_content(content, msg.get("name"))
                msg["content"] = compressed_content
                meta["compressed"] = True
                meta["original_length"] = len(content)
                meta["token_count"] = self._counter.estimate(msg)
                compressed += 1

        if compressed > 0:
            self._compressed_count += compressed
            self._cache_valid = False
            logger.info(f"Compressed {compressed} old tool results")

        return compressed

    def reset_with_summary(self, summary: str) -> None:
        self._messages = [{"role": "user", "content": summary}]
        self._message_meta = [
            {
                "tier": MessageTier.RECENT_USER,
                "timestamp": datetime.now(),
                "original_length": len(summary),
                "compressed": False,
                "token_count": self._counter.estimate(self._messages[0]),
            }
        ]
        self._compressed_count = 0
        self._last_summarization = datetime.now()
        self._cache_valid = False
        logger.info("Context reset with summary")

    def get_messages(self) -> list[dict]:
        return self._messages.copy()

    def estimate_tokens(self, obj: Any) -> int:
        return self._counter.estimate(obj)

    def clear(self) -> None:
        self._messages.clear()
        self._message_meta.clear()
        self._compressed_count = 0
        self._pruned_count = 0
        self._cache_valid = False

    # -- Internal helpers ----------------------------------------------------

    def _assign_tier(self, message: dict, message_index: int) -> MessageTier:
        role = message.get("role", "")
        content = str(message.get("content", ""))
        age = len(self._messages) - message_index + 1

        if role == "system":
            return MessageTier.SYSTEM
        if role == "user":
            return MessageTier.RECENT_USER
        if role == "assistant":
            return (
                MessageTier.RECENT_ASSISTANT if age <= 3 else MessageTier.OLD_ASSISTANT
            )
        if role == "tool":
            if len(content) < 200 or "error" in content.lower():
                return MessageTier.TOOL_RESULT_CRITICAL
            return (
                MessageTier.RECENT_TOOL_RESULT if age <= 5 else MessageTier.OLD_TOOL_RESULT
            )

        return MessageTier.OLD_TOOL_RESULT

    def _calculate_overhead(
        self, system_prompt: str, tool_schemas: list[dict] | None
    ) -> int:
        overhead = self._counter.estimate(system_prompt)
        if tool_schemas:
            for schema in tool_schemas:
                overhead += self._counter.estimate(schema)
        return overhead

    def _available_budget(self, overhead: int) -> int:
        reserve = int(self._config.max_context_tokens * self._config.reserve_ratio)
        return self._config.max_context_tokens - overhead - reserve

    def _auto_compress(self) -> None:
        if not self._config.compress_tool_results:
            return
        if self.should_trigger_compression():
            self.compress_old_results()

    def _compress_content(self, content: str, tool_name: str | None) -> str:
        name = tool_name or "unknown"
        length = len(content)

        if content.strip().startswith(("{", "[")):
            try:
                data = json.loads(content)
                summary = self._summarize_structure(data)
                return (
                    f"[Tool result compressed - {length} chars, tool: {name}]\n"
                    f"Summary: {summary}"
                )
            except json.JSONDecodeError:
                pass

        truncated = content[: self._config.max_tool_result_length]
        return (
            f"[Tool result truncated - {length} chars, tool: {name}]\n"
            f"{truncated}\n"
            f"... ({length - self._config.max_tool_result_length} chars omitted)"
        )

    def _summarize_structure(self, data: Any, max_depth: int = 2) -> str:
        if max_depth <= 0:
            return "..."
        if isinstance(data, dict):
            if not data:
                return "{}"
            items = []
            for k, v in list(data.items())[:5]:
                items.append(f"{k}: {self._summarize_structure(v, max_depth - 1)}")
            if len(data) > 5:
                items.append(f"... ({len(data) - 5} more keys)")
            return "{" + ", ".join(items) + "}"
        if isinstance(data, list):
            if not data:
                return "[]"
            item_summary = self._summarize_structure(data[0], max_depth - 1) if data else ""
            return f"[{len(data)} items, e.g.: {item_summary}]"
        if isinstance(data, str):
            if len(data) > 50:
                return f'"{data[:50]}..."'
            return f'"{data}"'
        return str(data)

    def _calculate_total_tokens(self) -> int:
        return sum(
            meta.get("token_count", self._counter.estimate(msg))
            for msg, meta in zip(self._messages, self._message_meta)
        )

    def _group_into_units(
        self, messages: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        units = []
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
