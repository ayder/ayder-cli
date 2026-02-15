import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        """Execute a chat completion.

        Args:
            messages: List of message dictionaries.
            model: Model name.
            tools: Optional list of tool schemas.
            options: Optional dictionary of extra options (e.g. num_ctx).
            verbose: Whether to print debug information about the request.

        Returns:
            The raw response object from the LLM (provider specific, but usually expected to have .choices[0].message).
        """
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """List available models from the provider.

        Returns:
            List of model names/IDs.
        """
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI/Ollama implementation of LLMProvider."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, client: Any | None = None):
        if client:
            self.client = client
        else:
            self.client = OpenAI(base_url=base_url, api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        if verbose:
            self._print_llm_request(messages, model, tools, options)

        kwargs = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if options:
            # extra_body accepts dict but type stubs may differ
            kwargs["extra_body"] = {"options": options}  # type: ignore[assignment]

        return self.client.chat.completions.create(**kwargs)

    def list_models(self) -> List[str]:
        """List available models via the OpenAI-compatible API."""
        try:
            response = self.client.models.list()
            return [m.id for m in response.data]
        except Exception as e:
            logger.error(f"Failed to list models from LLM provider: {e}")
            return []

    def _print_llm_request(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> None:
        """Print formatted LLM request details when verbose mode is active."""
        from ayder_cli.ui import print_llm_request_debug

        print_llm_request_debug(messages, model, tools, options)


# ---------------------------------------------------------------------------
# OpenAI-compatible response wrappers (used by AnthropicProvider)
# ---------------------------------------------------------------------------


@dataclass
class _FunctionCall:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    type: str
    function: _FunctionCall


@dataclass
class _Message:
    content: str | None
    tool_calls: list[_ToolCall] = field(default_factory=list)


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Usage:
    total_tokens: int


@dataclass
class _Response:
    choices: list[_Choice]
    usage: _Usage


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------

_ANTHROPIC_MODELS_FALLBACK = [
    "claude-opus-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]


class AnthropicProvider(LLMProvider):
    """Native Anthropic Claude provider.

    Translates between OpenAI-style messages/tools and the Anthropic API,
    then wraps responses back into OpenAI-compatible dataclass objects so
    that downstream consumers (chat_loop, tui, client) work unchanged.
    """

    def __init__(
        self,
        api_key: str | None = None,
        client: Any | None = None,
    ):
        if client:
            self.client = client
        else:
            from anthropic import Anthropic

            self.client = Anthropic(api_key=api_key)

    # -- public interface ---------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        if verbose:
            self._print_llm_request(messages, model, tools, options)

        system, converted = self._convert_messages(messages)
        max_tokens = (options or {}).get("num_ctx", 8192)

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": converted,
            "max_tokens": max_tokens,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self.client.messages.create(**kwargs)
        return self._wrap_response(response)

    def list_models(self) -> List[str]:
        """List available models via the Anthropic API, falling back to a hardcoded list."""
        try:
            models = []
            page = self.client.models.list(limit=100)
            for m in page.data:
                models.append(m.id)
            return models if models else list(_ANTHROPIC_MODELS_FALLBACK)
        except Exception as e:
            logger.error(f"Failed to list models from Anthropic API: {e}")
            return list(_ANTHROPIC_MODELS_FALLBACK)

    # -- message translation ------------------------------------------------

    @staticmethod
    def _convert_messages(
        messages: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Convert OpenAI-style messages to Anthropic format.

        Returns (system_text, anthropic_messages).
        """
        system_parts: list[str] = []
        converted: list[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # System messages → separate system param
            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            # Tool result messages
            if role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                block = {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content if content else "",
                }
                converted.append({"role": "user", "content": [block]})
                continue

            # Assistant messages with tool_calls
            if role == "assistant" and msg.get("tool_calls"):
                blocks: list[Dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    args_str = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args,
                    })
                converted.append({"role": "assistant", "content": blocks})
                continue

            # Regular user/assistant text messages
            anthropic_role = "user" if role == "user" else "assistant"
            converted.append({"role": anthropic_role, "content": content})

        # Merge consecutive same-role messages
        merged = AnthropicProvider._merge_consecutive(converted)

        return "\n\n".join(system_parts), merged

    @staticmethod
    def _merge_consecutive(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge consecutive messages with the same role."""
        if not messages:
            return []
        result: list[Dict[str, Any]] = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == result[-1]["role"]:
                prev_content = result[-1]["content"]
                cur_content = msg["content"]

                # Normalise both sides to lists
                if isinstance(prev_content, str):
                    prev_content = [{"type": "text", "text": prev_content}]
                if isinstance(cur_content, str):
                    cur_content = [{"type": "text", "text": cur_content}]

                result[-1]["content"] = prev_content + cur_content
            else:
                result.append(msg)
        return result

    # -- tool translation ---------------------------------------------------

    @staticmethod
    def _convert_tools(
        tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert OpenAI tool schemas to Anthropic format."""
        converted = []
        for tool in tools:
            fn = tool.get("function", {})
            converted.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {}),
            })
        return converted

    # -- response wrapping --------------------------------------------------

    @staticmethod
    def _wrap_response(response: Any) -> _Response:
        """Wrap an Anthropic response into an OpenAI-compatible _Response."""
        text_parts: list[str] = []
        tool_calls: list[_ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    _ToolCall(
                        id=block.id,
                        type="function",
                        function=_FunctionCall(
                            name=block.name,
                            arguments=json.dumps(block.input),
                        ),
                    )
                )

        content = "\n".join(text_parts) if text_parts else None
        message = _Message(content=content, tool_calls=tool_calls or [])
        usage_input = getattr(response.usage, "input_tokens", 0)
        usage_output = getattr(response.usage, "output_tokens", 0)

        return _Response(
            choices=[_Choice(message=message)],
            usage=_Usage(total_tokens=usage_input + usage_output),
        )

    def _print_llm_request(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> None:
        from ayder_cli.ui import print_llm_request_debug

        print_llm_request_debug(messages, model, tools, options)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_llm_provider(config: Any) -> LLMProvider:
    """Create the appropriate LLM provider based on config.provider.

    Args:
        config: Config object with provider, base_url, api_key fields.

    Returns:
        An LLMProvider instance.
    """
    provider = getattr(config, "provider", "openai")
    if provider == "anthropic":
        try:
            return AnthropicProvider(api_key=config.api_key)
        except ImportError:
            raise ImportError(
                "Anthropic provider requires the 'anthropic' package. "
                "Install it with: pip install anthropic"
            )
    if provider == "gemini":
        raise ModuleNotFoundError(
            "Gemini provider is not yet supported. "
            "Configure it in config.toml for future use."
        )
    return OpenAIProvider(base_url=config.base_url, api_key=config.api_key)
