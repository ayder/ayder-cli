"""
Base abstractions for the OCP-compliant Provider Architecture.

These interfaces are closed for modification. All new models must implement 
the AIProvider strategy to map their specific behaviors into the NormalizedStreamChunk.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, AsyncGenerator, Optional

@dataclass
class _FunctionCall:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _FunctionCall
    type: str = "function"


@dataclass
class ToolCallDef:
    """A strictly defined tool call extracted from the model's native format."""
    id: str
    name: str
    arguments: str  # Always a JSON string representing the arguments


@dataclass
class NormalizedStreamChunk:
    """Normalized stream format for ALL providers.
    
    Providers must map their specific streaming chunk variants (e.g. content_block_delta,
    FunctionCall, reasoning_content, thought) into this standard structure.
    """
    content: str = ""
    reasoning: str = ""
    tool_calls: List[ToolCallDef] = field(default_factory=list)
    raw_chunk: Any = None  # Original raw chunk object for debugging/logging
    usage: Optional[Dict[str, int]] = None


class AIProvider(ABC):
    """The base execution strategy for all LLM interactions."""

    def __init__(self, config: Any, interaction_sink: Any = None) -> None:
        """Initialize the provider with config and optional interaction sink."""
        pass

    async def list_models(self) -> List[str]:
        """
        List available models from the provider.
        
        Returns:
            List of model name strings. Empty list if not supported or on error.
        """
        return []
    
    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        """Non-streaming completion call."""
        pass

    @abstractmethod
    def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        """
        Stream a chat completion, resolving model-specific native tool calls and reasoning.

        Args:
            messages: The standard OpenAI-like conversation history.
            model: The target model name.
            tools: Optional internal tool schemas. The provider translates these if necessary.
            options: Execution options (num_ctx, max_output_tokens, etc).
            verbose: Whether to log low-level debugging info.

        Yields:
            NormalizedStreamChunk objects ready for direct consumption by the chat loop.
        """
        pass


class ProviderUnavailableError(RuntimeError):
    """Raised when a driver's optional dependency is not installed.

    The string form is a complete, ASCII, user-facing message (already
    prefixed with 'Error:') so entry points can print str(e) verbatim.
    """

    def __init__(self, driver: str, extra: str, available: dict[str, bool]) -> None:
        self.driver = driver
        self.extra = extra
        self.available = available
        super().__init__(self._format())

    def _format(self) -> str:
        installed = [name for name, ok in self.available.items() if ok]
        missing = [name for name, ok in self.available.items() if not ok]
        return (
            f"Error: the '{self.driver}' driver is not installed.\n"
            f"  Install it with:  pip install ayder-cli[{self.extra}]\n"
            f"\n"
            f"Drivers in this install:\n"
            f"  available:      {', '.join(installed)}\n"
            f"  not installed:  {', '.join(missing)}"
        )
