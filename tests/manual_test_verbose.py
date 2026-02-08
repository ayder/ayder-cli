#!/usr/bin/env python3
"""
Manual test script for verbose LLM request display feature.
This script demonstrates the new verbose mode functionality.
"""

from unittest.mock import Mock
from ayder_cli.services.llm import OpenAIProvider
from ayder_cli.ui import print_llm_request_debug

def test_display():
    """Test the display function directly."""
    print("\n" + "="*80)
    print("TEST 1: Display LLM Request Debug Info")
    print("="*80 + "\n")
    
    messages = [
        {"role": "system", "content": "You are a helpful coding assistant with access to file system tools."},
        {"role": "user", "content": "Create a Python function that reads a JSON file"},
        {"role": "assistant", "content": "I'll help you create that function. Let me read the existing files first."},
        {"role": "tool", "content": "File list: main.py, config.json, utils.py"},
        {"role": "user", "content": "Now add error handling to the function"}
    ]
    
    tools = [
        {"function": {"name": "read_file"}},
        {"function": {"name": "write_file"}},
        {"function": {"name": "list_files"}},
        {"function": {"name": "replace_string"}},
        {"function": {"name": "run_shell_command"}},
        {"function": {"name": "search_codebase"}},
    ]
    
    options = {"num_ctx": 65536}
    
    print_llm_request_debug(messages, "qwen3-coder:latest", tools, options)
    

def test_long_message():
    """Test with a very long message to verify truncation."""
    print("\n" + "="*80)
    print("TEST 2: Long Message Truncation")
    print("="*80 + "\n")
    
    long_content = "This is a very long message. " * 20  # 580 chars
    messages = [
        {"role": "user", "content": long_content}
    ]
    
    print_llm_request_debug(messages, "test-model", None, None)


def test_provider_integration():
    """Test the provider calls the display function."""
    print("\n" + "="*80)
    print("TEST 3: Provider Integration (with mock)")
    print("="*80 + "\n")
    
    mock_client = Mock()
    mock_response = Mock()
    mock_client.chat.completions.create.return_value = mock_response
    
    provider = OpenAIProvider(client=mock_client)
    messages = [{"role": "user", "content": "Hello, can you help me?"}]
    tools = [{"function": {"name": "read_file"}}]
    
    print("Calling provider with verbose=True...")
    provider.chat(messages, "qwen3-coder:latest", tools=tools, options={"num_ctx": 8192}, verbose=True)
    
    print("\n✅ Provider call completed (display should appear above)")


def test_message_objects():
    """Test with message objects instead of dicts."""
    print("\n" + "="*80)
    print("TEST 4: Message Objects (OpenAI SDK format)")
    print("="*80 + "\n")
    
    # Simulate OpenAI SDK message objects
    class MockMessage:
        def __init__(self, role, content):
            self.role = role
            self.content = content
    
    messages = [
        MockMessage("system", "You are a helpful assistant"),
        MockMessage("user", "Write a hello world function"),
    ]
    
    tools = [{"function": {"name": "write_file"}}]
    
    print_llm_request_debug(messages, "qwen3-coder:latest", tools, {"num_ctx": 4096})



if __name__ == "__main__":
    print("\n🔍 VERBOSE MODE LLM REQUEST DISPLAY - MANUAL TEST\n")
    
    test_display()
    test_long_message()
    test_provider_integration()
    test_message_objects()
    
    print("\n" + "="*80)
    print("ALL TESTS COMPLETED")
    print("="*80 + "\n")
    print("To use in interactive mode:")
    print("  1. Run: ayder")
    print("  2. Type: /verbose")
    print("  3. Send a message to the LLM")
    print("  4. You should see the LLM request details before the response\n")
