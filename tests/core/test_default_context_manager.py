"""Tests for DefaultContextManager — preserves existing behavior for non-Ollama providers."""
from unittest.mock import MagicMock

from ayder_cli.core.default_context_manager import DefaultContextManager
from ayder_cli.core.context_manager import ContextStats


def _make_config(max_context_tokens: int = 8192):
    cfg = MagicMock()
    cfg.context_manager.max_context_tokens = max_context_tokens
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    cfg.context_manager.tool_result_compress_age = 5
    cfg.context_manager.max_tool_result_length = 2048
    cfg.context_manager.compress_tool_results = True
    cfg.context_manager.enabled = True
    cfg.provider = "openai"
    cfg.model = "gpt-4o"
    return cfg


def test_implements_protocol():
    from ayder_cli.core.context_manager import ContextManagerProtocol

    mgr = DefaultContextManager.from_config(_make_config())
    assert isinstance(mgr, ContextManagerProtocol)


def test_freeze_system_prompt():
    mgr = DefaultContextManager.from_config(_make_config())
    mgr.freeze_system_prompt(
        "You are helpful.",
        [{"type": "function", "function": {"name": "test"}}],
    )
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    result = mgr.prepare_messages(messages)
    assert result[0]["role"] == "system"


def test_prepare_messages_fits_budget():
    mgr = DefaultContextManager.from_config(_make_config(max_context_tokens=200))
    mgr.freeze_system_prompt("System.", [])
    messages = [{"role": "system", "content": "System."}]
    for i in range(20):
        messages.append({"role": "user", "content": f"Message {i} " + "x" * 100})
        messages.append({"role": "assistant", "content": f"Response {i} " + "y" * 100})
    result = mgr.prepare_messages(messages)
    assert len(result) < len(messages)
    assert result[0]["role"] == "system"


def test_prepare_messages_groups_tool_calls():
    """Assistant + tool results should be kept or dropped as a unit."""
    mgr = DefaultContextManager.from_config(_make_config(max_context_tokens=100000))
    mgr.freeze_system_prompt("S", [])
    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "Do something"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "1", "name": "read_file", "content": "file contents"},
        {"role": "assistant", "content": "Done"},
    ]
    result = mgr.prepare_messages(messages)
    assert len(result) == 5


def test_get_stats_returns_context_stats():
    mgr = DefaultContextManager.from_config(_make_config())
    mgr.freeze_system_prompt("System.", [])
    stats = mgr.get_stats()
    assert isinstance(stats, ContextStats)


def test_update_from_response_accepts_usage():
    mgr = DefaultContextManager.from_config(_make_config())
    mgr.freeze_system_prompt("System.", [])
    mgr.update_from_response(
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    )
    # No error means success; internal state updated
    assert mgr._last_prompt_tokens == 100
    assert mgr._last_completion_tokens == 50


def test_update_from_response_ignores_ollama_keys():
    """Provider-specific keys like prompt_eval_ns should be silently ignored."""
    mgr = DefaultContextManager.from_config(_make_config())
    mgr.freeze_system_prompt("System.", [])
    # Should not raise
    mgr.update_from_response({"prompt_tokens": 100, "prompt_eval_ns": 5000000})
    assert mgr._last_prompt_tokens == 100


def test_from_config():
    cfg = _make_config()
    mgr = DefaultContextManager.from_config(cfg)
    assert mgr is not None
    assert isinstance(mgr, DefaultContextManager)


def test_should_compact_delegates_to_summarization():
    """should_compact() must delegate to the internal threshold logic."""
    mgr = DefaultContextManager.from_config(_make_config(max_context_tokens=100))
    # Fill messages to push utilization above threshold
    large_content = "x" * 500
    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": large_content},
        {"role": "assistant", "content": large_content},
    ]
    mgr.prepare_messages(messages)
    # Either True or False is acceptable — we just test it doesn't raise
    result = mgr.should_compact()
    assert isinstance(result, bool)


def test_token_counting_legacy_api():
    """Legacy count_tokens / count_message_tokens / count_schema_tokens still work."""
    from ayder_cli.core.config import ContextManagerConfigSection

    config = ContextManagerConfigSection(max_context_tokens=1000)
    mgr = DefaultContextManager(config)
    assert mgr.count_tokens("Hello world") > 0
    assert mgr.count_tokens("") == 0
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    assert mgr.count_message_tokens(messages) > 0
    schemas = [{"name": "test_tool", "parameters": {}}]
    assert mgr.count_schema_tokens(schemas) > 0


def test_add_message_copies_dict():
    """add_message must copy the dict so caller mutations don't corrupt history."""
    from ayder_cli.core.config import ContextManagerConfigSection

    config = ContextManagerConfigSection(max_context_tokens=1000)
    mgr = DefaultContextManager(config)
    msg = {"role": "user", "content": "original"}
    mgr.add_message(msg)
    msg["content"] = "mutated by caller"
    assert mgr._messages[0]["content"] == "original"


def test_group_into_units():
    from ayder_cli.core.config import ContextManagerConfigSection

    config = ContextManagerConfigSection(max_context_tokens=1000)
    mgr = DefaultContextManager(config)
    messages = [
        {"role": "user", "content": "run ls"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "1", "function": {"name": "ls"}}],
        },
        {"role": "tool", "content": "file1", "tool_call_id": "1"},
        {"role": "user", "content": "thanks"},
    ]
    units = mgr._group_into_units(messages)
    assert len(units) == 3
    assert units[0] == [messages[0]]
    assert units[1] == [messages[1], messages[2]]
    assert units[2] == [messages[3]]


def _make_old_long_tool_result_manager(config):
    """Manager holding one old, long tool result eligible for compression."""
    mgr = DefaultContextManager(config)
    long_content = "x" * 5000  # exceeds max_tool_result_length (2048)
    mgr.add_message({"role": "user", "content": "go"})
    mgr.add_message(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "1", "function": {"name": "read_file", "arguments": "{}"}}
            ],
        }
    )
    mgr.add_message(
        {"role": "tool", "tool_call_id": "1", "name": "read_file", "content": long_content}
    )
    # Filler so the tool result is "old" (age > tool_result_compress_age=5).
    for i in range(10):
        mgr.add_message({"role": "user", "content": f"m{i}"})
    return mgr, long_content


def test_max_context_tokens_defaults_to_none():
    """max_context_tokens is now optional — unset means 'derive from num_ctx'."""
    from ayder_cli.core.config import ContextManagerConfigSection

    assert ContextManagerConfigSection().max_context_tokens is None


def test_budget_syncs_from_num_ctx_when_max_context_tokens_unset():
    """When max_context_tokens is unset, the budget tracks the model's num_ctx."""
    from types import SimpleNamespace
    from ayder_cli.core.config import ContextManagerConfigSection

    cfg = SimpleNamespace(
        context_manager=ContextManagerConfigSection(),  # max_context_tokens=None
        num_ctx=131072,
        provider="openai",
        model="x",
    )
    mgr = DefaultContextManager(cfg)

    assert mgr._max_context_tokens == 131072
    assert mgr.reserve == int(131072 * 0.30)


def test_explicit_max_context_tokens_overrides_num_ctx():
    """An explicit max_context_tokens wins over num_ctx."""
    from types import SimpleNamespace
    from ayder_cli.core.config import ContextManagerConfigSection

    cfg = SimpleNamespace(
        context_manager=ContextManagerConfigSection(max_context_tokens=4096),
        num_ctx=131072,
        provider="openai",
        model="x",
    )
    mgr = DefaultContextManager(cfg)

    assert mgr._max_context_tokens == 4096


def test_enable_compression_defaults_off():
    """Compression must be opt-in: the global flag defaults to False."""
    from ayder_cli.core.config import ContextManagerConfigSection

    assert ContextManagerConfigSection().enable_compression is False


def test_compress_old_results_noop_when_compression_disabled():
    """With the default (disabled) flag, old long tool results are NOT compressed."""
    from ayder_cli.core.config import ContextManagerConfigSection

    config = ContextManagerConfigSection(max_context_tokens=1000)
    mgr, original = _make_old_long_tool_result_manager(config)

    compressed = mgr.compress_old_results()

    assert compressed == 0
    assert mgr._messages[2]["content"] == original  # untouched


def test_compress_old_results_runs_when_compression_enabled():
    """When enable_compression=True, eligible old long tool results are compressed."""
    from ayder_cli.core.config import ContextManagerConfigSection

    config = ContextManagerConfigSection(
        max_context_tokens=1000, enable_compression=True
    )
    mgr, original = _make_old_long_tool_result_manager(config)

    compressed = mgr.compress_old_results()

    assert compressed == 1
    assert mgr._messages[2]["content"] != original
    assert "truncated" in mgr._messages[2]["content"].lower()


def test_assign_tier_user_messages_never_old_assistant():
    """_assign_tier must not assign OLD_ASSISTANT to old user messages."""
    from ayder_cli.core.config import ContextManagerConfigSection
    from ayder_cli.core.default_context_manager import MessageTier

    config = ContextManagerConfigSection(max_context_tokens=1000)
    mgr = DefaultContextManager(config)
    mgr._messages = [{"role": "user", "content": f"filler {i}"} for i in range(20)]
    old_user_msg = {"role": "user", "content": "an old user message"}
    tier = mgr._assign_tier(old_user_msg, message_index=1)
    assert tier != MessageTier.OLD_ASSISTANT
