"""Async LLM call utility used by TuiChatLoop.

Provides call_llm_async() which wraps the synchronous LLM provider call
in a ThreadPoolExecutor so it doesn't block the async event loop.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ayder_cli.services.llm import LLMProvider

# Thread pool for running sync code
_executor = ThreadPoolExecutor(max_workers=2)


async def call_llm_async(
    llm: LLMProvider,
    messages: list,
    model: str,
    tools: list | None = None,
    num_ctx: int = 65536,
    max_output_tokens: int = 4096,
    stop_sequences: list | None = None,
) -> Any:
    """Async wrapper for LLM calls.

    Runs the synchronous LLM call in a thread pool to avoid blocking the UI.

    Args:
        llm: LLM provider instance
        messages: Conversation history
        model: Model name
        tools: Available tools (optional)
        num_ctx: Context window size
        max_output_tokens: Maximum tokens to generate in the response
        stop_sequences: Optional list of stop sequences

    Returns:
        LLM response object
    """
    loop = asyncio.get_event_loop()

    def call_sync():
        options: dict = {"num_ctx": num_ctx, "max_output_tokens": max_output_tokens}
        if stop_sequences:
            options["stop_sequences"] = stop_sequences
        return llm.chat(messages, model, tools, options)

    return await loop.run_in_executor(_executor, call_sync)
