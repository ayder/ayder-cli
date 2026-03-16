"""
Context manager for ayder-cli chat loop.
Responsible for token counting, message trimming, and tool result truncation.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

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

@dataclass
class ContextStats:
    """Statistics about current context usage."""
    total_tokens: int
    overhead_tokens: int
    history_tokens: int
    available_tokens: int
    utilization_percent: float
    message_count: int
    compressed_count: int
    pruned_count: int
    last_summarization: datetime

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
        chars_per_token = self.CHARS_PER_TOKEN["code"] if is_code else self.CHARS_PER_TOKEN["default"]
        
        return int(len(text) / chars_per_token) + 1

    def count_schema_tokens(self, schemas: list[dict]) -> int:
        return self.estimate(schemas)
    
    def count_tokens(self, text: str) -> int:
        return self._estimate_string(text)
    
    def count_message_tokens(self, messages: list[dict]) -> int:
        return self.count_messages(messages)

class ContextManager:
    def __init__(self, config: Any, model: str = "unknown"):
        # Support both new config objects and legacy configs
        from ayder_cli.core.config import ContextManagerConfigSection
        
        if hasattr(config, "context_manager"):
            self._config = config.context_manager
        elif isinstance(config, ContextManagerConfigSection):
            self._config = config
        else:
            # Fallback for legacy configs
            max_tokens = getattr(config, "num_ctx", 8192)
            if max_tokens <= 0:
                max_tokens = 8192
            self._config = ContextManagerConfigSection(
                max_context_tokens=max_tokens
            )
            
        provider = getattr(config, "provider", "openai")
        self._counter = TokenCounter(model=model, provider=provider)
        
        self._messages: List[Dict[str, Any]] = []
        self._message_meta: List[Dict[str, Any]] = []
        
        self._compressed_count = 0
        self._pruned_count = 0
        self._last_summarization = datetime.now()
        self._cache_valid = False
        self._stats_cache: ContextStats | None = None

    @property
    def max_context(self) -> int:
        return self._config.max_context_tokens

    @property
    def reserve(self) -> int:
        return int(self._config.max_context_tokens * self._config.reserve_ratio)
        
    def count_tokens(self, text: str) -> int:
        """Legacy support"""
        return self._counter.estimate(text)
        
    def count_message_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Legacy support"""
        return self._counter.count_messages(messages)
        
    def count_schema_tokens(self, schemas: List[Dict[str, Any]]) -> int:
        """Legacy support"""
        return self._counter.estimate(schemas)
        
    def prepare_messages(
        self,
        messages: List[Dict[str, Any]],
        system_tokens: int = 0,
        schema_tokens: int = 0,
        max_history: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Legacy support wrapper that syncs external messages to internal state,
        then performs the new tiered prioritization.
        """
        # Re-sync if the external list is completely different
        self._messages = []
        self._message_meta = []
        self._cache_valid = False
        
        for msg in messages:
            self.add_message(msg)
            
        if not self._messages:
            return []
            
        # Perform auto compression
        self._auto_compress()
            
        system_msg = self._messages[0] if self._messages and self._messages[0].get("role") == "system" else None
        
        # Calculate overhead based on real estimated values
        overhead = self._calculate_overhead(
            system_msg.get("content", "") if system_msg else "", 
            None  # Assume schema tokens passed correctly externally
        )
        # Add external schema tokens manually
        overhead += schema_tokens
        
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
            result.insert(0, {"role": "user", "content": "[... history truncated for context efficiency ...]"})

        return ([system_msg] if system_msg else []) + result

    def truncate_tool_result(self, content: str, max_tokens: int = 2048) -> str:
        """Legacy support"""
        if not content:
            return ""
            
        if len(content) < max_tokens * 2: 
            return content
            
        if content.strip().startswith(("{", "[")):
            try:
                data = json.loads(content)
                summary = self._summarize_structure(data)
                return (
                    f"[Tool result compressed - {len(content)} chars]\n"
                    f"Summary: {summary}"
                )
            except json.JSONDecodeError:
                pass
                
        if self._counter._encoder:
            tokens = self._counter._encoder.encode(content)
            if len(tokens) <= max_tokens:
                return content
                
            head_len = int(max_tokens * 0.4)
            tail_len = int(max_tokens * 0.1)
            
            head_text = self._counter._encoder.decode(tokens[:head_len])
            tail_text = self._counter._encoder.decode(tokens[-tail_len:])
            
            removed_count = len(tokens) - head_len - tail_len
            
            return (
                f"{head_text}\n\n"
                f"--- [TRUNCATED {removed_count} TOKENS FOR CONTEXT EFFICIENCY] ---\n\n"
                f"{tail_text}"
            )
            
        max_chars = max_tokens * 4
        if len(content) <= max_chars:
            return content
        
        return content[:max_chars] + f"\n... ({len(content) - max_chars} chars omitted for context efficiency)"

    def add_message(self, message: dict) -> None:
        self._messages.append(message)
        
        tier = self._assign_tier(message, len(self._messages))
        token_count = self._counter.estimate(message)
        
        self._message_meta.append({
            "tier": tier,
            "timestamp": datetime.now(),
            "original_length": len(str(message.get("content", ""))),
            "compressed": False,
            "token_count": token_count
        })
        self._cache_valid = False

    def should_trigger_summarization(self) -> bool:
        if not self._config.enabled:
            return False
            
        total = self._calculate_total_tokens()
        utilization = total / self._config.max_context_tokens
        return utilization >= self._config.summarization_threshold

    def should_trigger_compression(self) -> bool:
        if not self._config.enabled or not self._config.compress_tool_results:
            return False
            
        total = self._calculate_total_tokens()
        utilization = total / self._config.max_context_tokens
        return utilization >= self._config.compression_threshold

    def compress_old_results(self, age_threshold: int | None = None) -> int:
        threshold = age_threshold if age_threshold is not None else self._config.tool_result_compress_age
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
        self._message_meta = [{
            "tier": MessageTier.RECENT_USER,
            "timestamp": datetime.now(),
            "original_length": len(summary),
            "compressed": False,
            "token_count": self._counter.estimate(self._messages[0]),
        }]
        self._compressed_count = 0
        self._last_summarization = datetime.now()
        self._cache_valid = False
        logger.info("Context reset with summary")

    def get_stats(self) -> ContextStats:
        if self._cache_valid and self._stats_cache:
            return self._stats_cache
        
        total = self._calculate_total_tokens()
        system_content = self._messages[0].get("content", "") if self._messages and self._messages[0].get("role") == "system" else ""
        overhead = self._calculate_overhead(system_content, [])
        history = total - overhead if total > overhead else 0
        available = self._config.max_context_tokens - total
        
        self._stats_cache = ContextStats(
            total_tokens=total,
            overhead_tokens=overhead,
            history_tokens=history,
            available_tokens=max(0, available),
            utilization_percent=(total / self._config.max_context_tokens) * 100,
            message_count=len(self._messages),
            compressed_count=self._compressed_count,
            pruned_count=self._pruned_count,
            last_summarization=self._last_summarization,
        )
        self._cache_valid = True
        return self._stats_cache

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

    def _assign_tier(self, message: dict, message_index: int) -> MessageTier:
        role = message.get("role", "")
        content = str(message.get("content", ""))
        age = len(self._messages) - message_index + 1
        
        if role == "system":
            return MessageTier.SYSTEM
        if role == "user":
            return MessageTier.RECENT_USER if age <= 3 else MessageTier.OLD_ASSISTANT
        if role == "assistant":
            return MessageTier.RECENT_ASSISTANT if age <= 3 else MessageTier.OLD_ASSISTANT
        if role == "tool":
            if len(content) < 200 or "error" in content.lower():
                return MessageTier.TOOL_RESULT_CRITICAL
            return MessageTier.RECENT_TOOL_RESULT if age <= 5 else MessageTier.OLD_TOOL_RESULT
        
        return MessageTier.OLD_TOOL_RESULT

    def _calculate_overhead(self, system_prompt: str, tool_schemas: list[dict] | None) -> int:
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
                return f"[Tool result compressed - {length} chars, tool: {name}]\nSummary: {summary}"
            except json.JSONDecodeError:
                pass
        
        truncated = content[:self._config.max_tool_result_length]
        return f"[Tool result truncated - {length} chars, tool: {name}]\n{truncated}\n... ({length - self._config.max_tool_result_length} chars omitted)"

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

    def _group_into_units(self, messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
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
