from ayder_cli.core.context_manager import ContextManager

from ayder_cli.core.config import ContextManagerConfigSection

def test_token_counting():
    config = ContextManagerConfigSection(max_context_tokens=1000)
    cm = ContextManager(config)
    assert cm.count_tokens("Hello world") > 0
    assert cm.count_tokens("") == 0
    
    # Test message counting
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    tokens = cm.count_message_tokens(messages)
    assert tokens > 0
    
    # Test schema counting
    schemas = [{"name": "test_tool", "parameters": {}}]
    assert cm.count_schema_tokens(schemas) > 0

def test_group_into_units():
    config = ContextManagerConfigSection(max_context_tokens=1000)
    cm = ContextManager(config)
    messages = [
        {"role": "user", "content": "run ls"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "ls"}}]},
        {"role": "tool", "content": "file1", "tool_call_id": "1"},
        {"role": "user", "content": "thanks"}
    ]
    
    units = cm._group_into_units(messages)
    assert len(units) == 3
    assert units[0] == [messages[0]]
    assert units[1] == [messages[1], messages[2]]  # Atomic unit
    assert units[2] == [messages[3]]

def test_prepare_messages_budgeting():
    # Very small budget to force trimming
    # reserve = 50 * 0.2 = 10
    config = ContextManagerConfigSection(max_context_tokens=50, reserve_ratio=0.2)
    cm = ContextManager(config)
    
    messages = [
        {"role": "system", "content": "I am a bot"},
        {"role": "user", "content": "Long message that will be trimmed " * 10},
        {"role": "user", "content": "Short message"}
    ]
    
    # System prompt is about 5 tokens, plus overhead
    trimmed = cm.prepare_messages(messages, system_tokens=10, schema_tokens=0)
    
    assert len(trimmed) < len(messages)
    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"] == "Short message"

def test_anthropic_constraint():
    # budget = 100 - (100*0.1) = 90
    config = ContextManagerConfigSection(max_context_tokens=100, reserve_ratio=0.1)
    cm = ContextManager(config)
    
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "very long message that gets trimmed" * 10},
        {"role": "assistant", "content": "I am here"},
        {"role": "user", "content": "newest"}
    ]
    
    # Force trim to skip the first user message
    # budget = 90 - 5 - 0 = 85
    trimmed = cm.prepare_messages(messages, system_tokens=5, schema_tokens=0)
    
    non_system = trimmed[1:]
    assert non_system[0]["role"] == "user"

def test_truncate_tool_result():
    config = ContextManagerConfigSection(max_context_tokens=1000)
    cm = ContextManager(config)
    long_content = "word " * 1000
    truncated = cm.truncate_tool_result(long_content, max_tokens=50)
    
    assert "TRUNCATED" in truncated
    # Use internal counter for token count in test
    assert cm._counter._estimate_string(truncated) <= 100
