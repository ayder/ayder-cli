"""Async LLM call utility used by TuiChatLoop.

Provides call_llm_async() which directly awaits the new async AIProvider.chat() method.
Maintained for backward compatibility in the broader system.
"""

from typing import Any
from ayder_cli.providers import AIProvider

async def call_llm_async(
    llm: AIProvider,
    messages: list,
    model: str,
    tools: list | None = None,
    num_ctx: int = 65536,
    max_output_tokens: int = 4096,
    stop_sequences: list | None = None,
) -> Any:
    """Async wrapper for LLM calls.

    Awaits the native async llm.chat() method directly.
    """
    options: dict = {"num_ctx": num_ctx, "max_output_tokens": max_output_tokens}
    if stop_sequences:
        options["stop_sequences"] = stop_sequences
        
    return await llm.chat(messages, model, tools, options)
