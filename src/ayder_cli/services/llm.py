from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
from openai import OpenAI

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, Any]], model: str, tools: Optional[List[Dict[str, Any]]] = None, options: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a chat completion.
        
        Args:
            messages: List of message dictionaries.
            model: Model name.
            tools: Optional list of tool schemas.
            options: Optional dictionary of extra options (e.g. num_ctx).
            
        Returns:
            The raw response object from the LLM (provider specific, but usually expected to have .choices[0].message).
        """
        pass

class OpenAIProvider(LLMProvider):
    """OpenAI/Ollama implementation of LLMProvider."""
    
    def __init__(self, base_url: str = None, api_key: str = None, client: Any = None):
        if client:
            self.client = client
        else:
            self.client = OpenAI(base_url=base_url, api_key=api_key)
        
    def chat(self, messages: List[Dict[str, Any]], model: str, tools: Optional[List[Dict[str, Any]]] = None, options: Optional[Dict[str, Any]] = None) -> Any:
        kwargs = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            
        if options:
             kwargs["extra_body"] = {"options": options}
             
        return self.client.chat.completions.create(**kwargs)
