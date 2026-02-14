"""
Client module - Manages chat sessions and agents.

This module provides:
- ChatSession: Manages conversation state and history
- Agent: High-level interface that delegates to ChatLoop for execution
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from ayder_cli.services.llm import LLMProvider
from ayder_cli.services.tools.executor import ToolExecutor
from ayder_cli.checkpoint_manager import CheckpointManager
from ayder_cli.memory import MemoryManager
from ayder_cli.chat_loop import ChatLoop, LoopConfig

# Thread pool for running sync code
_executor = ThreadPoolExecutor(max_workers=2)


async def call_llm_async(
    llm: LLMProvider,
    messages: list,
    model: str,
    tools: list | None = None,
    num_ctx: int = 65536,
) -> Any:
    """
    Async wrapper for LLM calls.

    Runs the synchronous LLM call in a thread pool to avoid blocking the UI.

    Args:
        llm: LLM provider instance
        messages: Conversation history
        model: Model name
        tools: Available tools (optional)
        num_ctx: Context window size

    Returns:
        LLM response object
    """
    loop = asyncio.get_event_loop()

    def call_sync():
        options = {"num_ctx": num_ctx}
        return llm.chat(messages, model, tools, options)

    return await loop.run_in_executor(_executor, call_sync)


class ChatSession:
    """Manage conversation state and history."""

    def __init__(
        self,
        config,
        system_prompt: str,
        permissions: set | None = None,
        iterations: int = 50,
        checkpoint_manager: CheckpointManager | None = None,
        memory_manager: MemoryManager | None = None,
    ):
        """Initialize chat session.

        Args:
            config: Config object
            system_prompt: Base SYSTEM_PROMPT (enhanced with project structure)
            permissions: Set of granted permission categories.
            iterations: Max agentic iterations per message.
            checkpoint_manager: CheckpointManager for checkpoint/restore cycles.
            memory_manager: MemoryManager for LLM-based checkpoint operations.
        """
        self.config = config
        self.system_prompt = system_prompt
        self.messages: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {
            "verbose": config.verbose if hasattr(config, "verbose") else False,
            "permissions": permissions or set(),
            "iterations": iterations,
        }
        self.checkpoint_manager = checkpoint_manager
        self.memory_manager = memory_manager

    def add_message(self, role: str, content: str, **kwargs):
        """Add a message to conversation history.

        Args:
            role: Message role (user, assistant, system, tool)
            content: Message content
            **kwargs: Additional message fields (tool_call_id, name, etc.)
        """
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.messages.append(message)

    def append_raw(self, message):
        """Append a raw/pre-formed message object to history.

        Used for OpenAI message objects that need to preserve their
        structure (e.g., tool_calls attribute).
        """
        self.messages.append(message)

    def get_messages(self) -> list:
        """Get current message history for API calls."""
        return self.messages

    def clear_messages(self, keep_system: bool = True):
        """Clear conversation history, optionally keeping system message.

        Args:
            keep_system: If True, keeps the system message
        """
        if keep_system and len(self.messages) > 0:
            system_msg = self.messages[0]
            self.messages = [system_msg]
        else:
            self.messages = []


class Agent:
    """Handle OpenAI/Ollama API interaction and tool execution."""

    def __init__(
        self, llm_provider: LLMProvider, tools: ToolExecutor, session: ChatSession
    ):
        """Initialize agent.

        Args:
            llm_provider: LLMProvider instance (injected)
            tools: ToolExecutor instance (injected)
            session: Reference to ChatSession
        """
        self.llm = llm_provider
        self.tools = tools
        self.session = session

    def chat(self, user_input: str) -> str | None:
        """Process user input through the agentic loop.

        Returns the final assistant text response, or None if only
        tools ran (terminal tool, empty content, etc.).  Errors
        propagate as exceptions — the caller handles UI.

        Args:
            user_input: User's input message

        Returns:
            The assistant's text response, or None.
        """
        # Get config from session
        cfg = self.session.config
        model = self.session.state.get("model", cfg.model)

        # Build loop configuration
        loop_config = LoopConfig(
            max_iterations=self.session.state.get("iterations", 50),
            model=model,
            num_ctx=cfg.num_ctx,
            verbose=self.session.state.get("verbose", False),
            permissions=self.session.state.get("permissions", set()),
        )

        # Create and run chat loop
        chat_loop = ChatLoop(
            llm_provider=self.llm,
            tool_executor=self.tools,
            session=self.session,
            config=loop_config,
            checkpoint_manager=self.session.checkpoint_manager,
            memory_manager=self.session.memory_manager,
        )

        return chat_loop.run(user_input)
