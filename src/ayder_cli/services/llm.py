import logging
from abc import ABC, abstractmethod
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
