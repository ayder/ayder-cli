import json
import logging
import uuid
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

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        client: Any | None = None,
        interaction_sink: Any | None = None,
    ):
        if client:
            self.client = client
        else:
            self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.interaction_sink = interaction_sink

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        if verbose and self.interaction_sink is not None:
            self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        kwargs = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if options:
            if stop := options.get("stop_sequences"):
                kwargs["stop"] = stop  # type: ignore[assignment]

        return self.client.chat.completions.create(**kwargs)

    def list_models(self) -> List[str]:
        """List available models via the OpenAI-compatible API."""
        try:
            response = self.client.models.list()
            return [m.id for m in response.data]
        except Exception as e:
            logger.error(f"Failed to list models from LLM provider: {e}")
            return []


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
        interaction_sink: Any | None = None,
    ):
        if client:
            self.client = client
        else:
            from anthropic import Anthropic

            self.client = Anthropic(api_key=api_key)
        self.interaction_sink = interaction_sink

    # -- public interface ---------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        if verbose and self.interaction_sink is not None:
            self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        system, converted = self._convert_messages(messages)
        # Use max_output_tokens (max response length), NOT num_ctx (context window size).
        # Requires anthropic>=0.25.0 for cache_control support.
        max_tokens = (options or {}).get("max_output_tokens", 4096)

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": converted,
            "max_tokens": max_tokens,
        }
        if system:
            # Structured system block with cache_control so Anthropic caches the
            # system prompt + tool schemas across turns (~90% token savings on hits).
            kwargs["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if stop := (options or {}).get("stop_sequences"):
            kwargs["stop_sequences"] = stop

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


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------


class GeminiProvider(LLMProvider):
    """Google Gemini provider via google-genai package."""

    def __init__(
        self,
        api_key: str | None = None,
        client: Any | None = None,
        interaction_sink: Any | None = None,
    ):
        if client:
            self.client = client
        else:
            from google import genai

            self.client = genai.Client(api_key=api_key)
        self.interaction_sink = interaction_sink

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        if verbose and self.interaction_sink is not None:
            self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        from google.genai import types

        system_instruction, contents = self._convert_messages(messages)
        
        # Convert options
        config_args = {}
        if options:
            # Use max_output_tokens (max response length), NOT num_ctx (context window size).
            if "max_output_tokens" in options:
                config_args["max_output_tokens"] = options["max_output_tokens"]
            if stop := options.get("stop_sequences"):
                config_args["stop_sequences"] = stop

        if system_instruction:
            config_args["system_instruction"] = system_instruction
            
        if tools:
            config_args["tools"] = self._convert_tools(tools)

        config = types.GenerateContentConfig(**config_args)

        try:
            # We use models.generate_content. contents expects list of Content objects or dicts.
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return self._wrap_response(response)
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            raise

    def list_models(self) -> List[str]:
        """List available models."""
        try:
            models = []
            for m in self.client.models.list():
                # In google-genai SDK, use supported_actions
                actions = getattr(m, "supported_actions", []) or []
                if "generateContent" in actions:
                    name = m.name.replace("models/", "")
                    models.append(name)
            return models
        except Exception as e:
            logger.error(f"Failed to list models from Gemini API: {e}")
            return ["gemini-3-deep-think", "gemini-3-pro", "gemini-3-flash"]

    # -- message translation ------------------------------------------------

    @staticmethod
    def _convert_messages(
        messages: List[Dict[str, Any]],
    ) -> tuple[str | None, List[Dict[str, Any]]]:
        """Convert OpenAI-style messages to Gemini format.

        Returns (system_instruction, contents).
        """
        system_parts: list[str] = []
        converted: list[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # System messages
            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            # Tool result messages
            if role == "tool":
                # OpenAI sends tool outputs as separate messages.
                # Gemini expects function_response parts.
                # We map role='tool' to role='function'.
                
                # Try to parse content as JSON if possible, otherwise use as is
                try:
                    response_content = json.loads(content) if content else {}
                    if not isinstance(response_content, dict):
                        response_content = {"result": response_content}
                except (json.JSONDecodeError, TypeError):
                    response_content = {"result": content}

                fn_name = msg.get("name", "unknown_tool")
                
                # If name is missing, we try to find it in the last assistant message's tool_calls
                # matching the tool_call_id.
                if fn_name == "unknown_tool" and converted:
                    pass
                
                part = {
                    "function_response": {
                        "name": fn_name,
                        "response": response_content,
                    }
                }
                # To provide result of function call send a message with role='user' 
                # and a part containing function_response.
                converted.append({"role": "user", "parts": [part]})
                continue

            # Assistant messages
            if role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content})
                
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    args_str = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    
                    parts.append({
                        "function_call": {
                            "name": fn.get("name", ""),
                            "args": args,
                        }
                    })
                
                if parts:
                    converted.append({"role": "model", "parts": parts})
                continue

            # User messages
            if role == "user":
                converted.append({"role": "user", "parts": [{"text": content}]})

        # Merge consecutive messages
        merged = GeminiProvider._merge_consecutive(converted)
        
        return "\n\n".join(system_parts) if system_parts else None, merged

    @staticmethod
    def _merge_consecutive(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not messages:
            return []
        
        result = [messages[0]]
        for msg in messages[1:]:
            last = result[-1]
            if msg["role"] == last["role"]:
                # Merge parts
                last["parts"].extend(msg["parts"])
            else:
                result.append(msg)
        return result

    @staticmethod
    def _convert_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Gemini tools format:
        # tools = [ { "function_declarations": [ ... ] } ]
        # Each declaration similar to OpenAI but wrapped.
        
        funcs = []
        for tool in tools:
            fn = tool.get("function", {})
            parameters = fn.get("parameters", {})
            # Sanitize parameters to remove unsupported fields like "default"
            sanitized_params = GeminiProvider._sanitize_schema(parameters)
            
            funcs.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": sanitized_params,
            })
            
        return [{"function_declarations": funcs}]

    @staticmethod
    def _sanitize_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize schema to remove unsupported fields for Gemini (e.g. default)."""
        if not isinstance(schema, dict):
            return schema
            
        new_schema: Dict[str, Any] = {}
        for k, v in schema.items():
            # Special handling for "properties" to preserve keys (arg names) that might match forbidden fields
            if k == "properties" and isinstance(v, dict):
                new_props = {}
                for prop_name, prop_schema in v.items():
                    new_props[prop_name] = GeminiProvider._sanitize_schema(prop_schema)
                new_schema[k] = new_props
                continue

            # Filter out known unsupported fields in Gemini's Schema protobuf
            if k in ("default", "additionalProperties", "title"):
                continue
                
            if isinstance(v, dict):
                new_schema[k] = GeminiProvider._sanitize_schema(v)
            elif isinstance(v, list):
                new_schema[k] = [
                    GeminiProvider._sanitize_schema(i) if isinstance(i, dict) else i 
                    for i in v
                ]
            else:
                new_schema[k] = v
                
        return new_schema

    @staticmethod
    def _wrap_response(response: Any) -> _Response:
        """Wrap Gemini response."""
        # response.candidates[0].content.parts
        # We need to handle safety blocks or empty responses
        if not response.candidates:
            return _Response(
                choices=[_Choice(message=_Message(content="Error: No candidates returned (safety filter?)"))],
                usage=_Usage(total_tokens=0),
            )
            
        candidate = response.candidates[0]
        text_parts = []
        tool_calls = []
        
        for part in candidate.content.parts:
            if part.text:
                text_parts.append(part.text)
            if part.function_call:
                # Generate a random ID as Gemini doesn't provide one
                call_id = f"call_{uuid.uuid4().hex[:8]}"
                tool_calls.append(
                    _ToolCall(
                        id=call_id,
                        type="function",
                        function=_FunctionCall(
                            name=part.function_call.name,
                            arguments=json.dumps(dict(part.function_call.args)),
                        ),
                    )
                )

        content = "\n".join(text_parts) if text_parts else None
        message = _Message(content=content, tool_calls=tool_calls)
        
        # Usage metadata
        usage = getattr(response, "usage_metadata", None)
        total_tokens = 0
        if usage:
            prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
            
            # Try candidates_token_count (old SDK), if missing or None, try response_token_count (new SDK)
            completion_tokens = getattr(usage, "candidates_token_count", None)
            if completion_tokens is None:
                completion_tokens = getattr(usage, "response_token_count", 0)
            
            completion_tokens = completion_tokens or 0
            total_tokens = prompt_tokens + completion_tokens
            
        return _Response(
            choices=[_Choice(message=message)],
            usage=_Usage(total_tokens=total_tokens),
        )


# ---------------------------------------------------------------------------
# Ollama provider (official ollama-python SDK)
# ---------------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    """Ollama provider using the official ollama-python SDK.

    Wraps responses into OpenAI-compatible dataclasses so downstream
    consumers (chat_loop, tui, client) work unchanged.

    Options mapping:
      num_ctx          → options.num_ctx
      max_output_tokens → options.num_predict  (max tokens to generate)
      stop_sequences   → options.stop
    """

    def __init__(
        self,
        host: str | None = None,
        client: Any | None = None,
        interaction_sink: Any | None = None,
    ):
        if client:
            self.client = client
        else:
            from ollama import Client

            self.client = Client(host=host)
        self.interaction_sink = interaction_sink

    # -- public interface ---------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        if verbose and self.interaction_sink is not None:
            self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        converted = self._convert_messages(messages)

        kwargs: Dict[str, Any] = {"model": model, "messages": converted}
        if tools:
            kwargs["tools"] = tools  # Ollama accepts the same OpenAI tool schema

        if options:
            ollama_opts: Dict[str, Any] = {}
            if "num_ctx" in options:
                ollama_opts["num_ctx"] = options["num_ctx"]
            if "max_output_tokens" in options:
                ollama_opts["num_predict"] = options["max_output_tokens"]
            if stop := options.get("stop_sequences"):
                ollama_opts["stop"] = stop
            if ollama_opts:
                kwargs["options"] = ollama_opts

        response = self.client.chat(**kwargs)
        return self._wrap_response(response)

    def list_models(self) -> List[str]:
        """List locally available Ollama models."""
        try:
            result = self.client.list()
            return [m.model for m in result.models]
        except Exception as e:
            logger.error(f"Failed to list models from Ollama: {e}")
            return []

    # -- message conversion -------------------------------------------------

    @staticmethod
    def _convert_messages(messages: List[Any]) -> List[Dict[str, Any]]:
        """Convert messages to Ollama SDK format.

        Key difference from OpenAI: tool_call arguments must be dicts,
        not JSON strings. Also handles _Message dataclass objects that
        the CLI chat_loop may append via session.append_raw().
        """
        converted: List[Dict[str, Any]] = []

        for msg in messages:
            # Support both dict messages (TUI) and _Message dataclass (CLI)
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "") or ""
                tool_calls_raw = msg.get("tool_calls")
            else:
                # _Message dataclass from CLI path — treat as assistant
                role = getattr(msg, "role", "assistant")
                content = getattr(msg, "content", "") or ""
                tool_calls_raw = getattr(msg, "tool_calls", None)

            if role == "assistant" and tool_calls_raw:
                # Convert tool_calls: arguments must be dict for Ollama SDK
                ollama_tool_calls = []
                for tc in tool_calls_raw:
                    if isinstance(tc, dict):
                        fn = tc.get("function", {})
                        args = fn.get("arguments", {})
                    else:
                        fn = getattr(tc, "function", None)
                        args = getattr(fn, "arguments", {}) if fn else {}
                    # Deserialise if arguments arrived as a JSON string
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    fn_name = fn.get("name", "") if isinstance(fn, dict) else getattr(fn, "name", "")
                    ollama_tool_calls.append(
                        {"function": {"name": fn_name, "arguments": args}}
                    )
                converted.append(
                    {"role": "assistant", "content": content, "tool_calls": ollama_tool_calls}
                )
                continue

            # System / user / tool / plain assistant messages pass through as dicts
            converted.append({"role": role, "content": content})

        return converted

    # -- response wrapping --------------------------------------------------

    @staticmethod
    def _wrap_response(response: Any) -> _Response:
        """Wrap an Ollama ChatResponse into an OpenAI-compatible _Response."""
        msg = response.message
        content: str | None = getattr(msg, "content", None) or None
        tool_calls: list[_ToolCall] = []

        for tc in getattr(msg, "tool_calls", None) or []:
            fn = tc.function
            args = fn.arguments if fn.arguments is not None else {}
            tool_calls.append(
                _ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    type="function",
                    function=_FunctionCall(
                        name=fn.name,
                        arguments=json.dumps(dict(args)),
                    ),
                )
            )

        prompt_tokens = getattr(response, "prompt_eval_count", 0) or 0
        eval_tokens = getattr(response, "eval_count", 0) or 0

        return _Response(
            choices=[_Choice(message=_Message(content=content, tool_calls=tool_calls))],
            usage=_Usage(total_tokens=prompt_tokens + eval_tokens),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_llm_provider(config: Any) -> LLMProvider:
    """Create the appropriate LLM provider based on config.driver.

    Args:
        config: Config object with driver/provider/base_url/api_key fields.

    Returns:
        An LLMProvider instance.
    """
    driver_raw = getattr(config, "driver", None)
    driver = driver_raw if isinstance(driver_raw, str) and driver_raw else None
    if driver is None:
        # Compatibility fallback for callers still providing provider-only config.
        provider_name = getattr(config, "provider", "openai")
        driver = {
            "openai": "openai",
            "anthropic": "anthropic",
            "gemini": "google",
        }.get(provider_name, "openai")

    if driver == "anthropic":
        try:
            return AnthropicProvider(api_key=config.api_key)
        except ImportError:
            raise ImportError(
                "Anthropic provider requires the 'anthropic' package. "
                "Install it with: pip install anthropic"
            )
    if driver == "google":
        try:
            return GeminiProvider(api_key=config.api_key)
        except ImportError:
            raise ImportError(
                "Gemini provider requires the 'google-genai' package. "
                "Install it with: pip install google-genai"
            )
    if driver == "ollama":
        try:
            # Strip the /v1 suffix added by OpenAI-compat configs — the Ollama SDK
            # builds its own paths (e.g. /api/chat) from the bare host URL.
            host = getattr(config, "base_url", None)
            if host and host.endswith("/v1"):
                host = host[:-3]
            return OllamaProvider(host=host)
        except ImportError:
            raise ImportError(
                "Ollama provider requires the 'ollama' package. "
                "Install it with: pip install ollama"
            )
    if driver == "openai":
        return OpenAIProvider(base_url=config.base_url, api_key=config.api_key)

    raise ValueError(
        f"Unsupported LLM driver '{driver}'. Expected one of: openai, ollama, anthropic, google."
    )
