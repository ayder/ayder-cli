"""Loop severity, asserted on the production call path."""
import pytest
from unittest.mock import MagicMock

# scripts/ is on sys.path via tests/conftest.py (§C15).
from logging_gates import BATCHES, collect, resolve  # noqa: E402

from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _Provider:
    """One text-only chunk, then done."""

    def __init__(self, content="Hello"):
        self.content = content

    async def stream_with_tools(self, *a, **k):
        from ayder_cli.providers import NormalizedStreamChunk
        chunk = NormalizedStreamChunk()
        chunk.content = self.content
        chunk.done = True
        yield chunk


class _Callbacks:
    """Never cancels. The loop ends through its real text-only return path."""

    def __init__(self):
        self.system_messages = []

    def on_thinking_start(self): pass
    def on_thinking_stop(self): pass
    def on_assistant_content(self, text): pass
    def on_thinking_content(self, text): pass
    def on_token_usage(self, total_tokens): pass
    def on_tool_start(self, call_id, name, arguments): pass
    def on_tool_complete(self, call_id, result): pass
    def on_tools_cleanup(self): pass
    def on_system_message(self, text): self.system_messages.append(text)
    async def request_confirmation(self, name, arguments): return None
    def is_cancelled(self): return False


def _loop(content="Hello", *, verbose=False, history=1):
    cfg = ChatLoopConfig()
    cfg.verbose = verbose
    return ChatLoop(
        llm=_Provider(content),
        registry=MagicMock(get_schemas=MagicMock(return_value=[])),
        messages=[{"role": "system", "content": "s"}]
                 + [{"role": "user", "content": f"m{i}"} for i in range(history)],
        config=cfg,
        callbacks=_Callbacks(),
    )


async def test_history_summary_is_one_debug_record_per_turn(loguru_caplog):
    await _loop(history=1).run()
    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("Calling LLM with history:")]
    assert len(hits) == 1
    assert hits[0]["level"].name == "DEBUG"
    assert hits[0]["extra"]["channel"] == "llm"


async def test_history_summary_does_not_scale_with_history(loguru_caplog):
    await _loop(history=40).run()
    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("Calling LLM with history:")]
    assert len(hits) == 1, "one summary per turn regardless of history length"


async def test_per_message_dump_is_trace_and_scales(loguru_caplog):
    await _loop(verbose=True, history=5).run()
    dumps = [r for r in loguru_caplog.records if r["message"].lstrip().startswith("Message ")]
    assert len(dumps) == 6                      # system + 5 user
    assert {r["level"].name for r in dumps} == {"TRACE"}


async def test_empty_response_is_error(loguru_caplog):
    loop = _loop(content="")
    await loop.run()
    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("LLM returned empty response")]
    assert hits, "empty-response record never emitted"
    assert hits[0]["level"].name == "ERROR"
    assert loop.cb.system_messages, "the user was never told the turn failed"


async def test_no_error_records_on_the_happy_path(loguru_caplog):
    await _loop().run()
    assert loguru_caplog.at_level("ERROR").messages == []


def test_context_record_is_debug_on_the_production_path(loguru_caplog):
    """`Context[...]` fires once per turn -> DEBUG, not INFO."""
    from ayder_cli.core.ollama_context_manager import OllamaContextManager
    mgr = OllamaContextManager(provisional_context_length=262144, model="m")
    mgr.update_from_response({"prompt_tokens": 100, "completion_tokens": 5})
    hits = [r for r in loguru_caplog.records if r["message"].startswith("Context[")]
    assert hits, "context record never emitted"
    assert hits[0]["level"].name == "DEBUG"
    assert "%%" not in hits[0]["message"]
    assert hits[0]["message"].count("%") == 1      # the utilisation sign only


# --- AST assertion: supplements the production tests, never replaces them ---

EXPECTED = {
    "loops/chat_loop.py :: ChatLoop.run :: Calling LLM with history:": "debug",
    "loops/chat_loop.py :: ChatLoop.run :: Message {} [{}] content_type=": "trace",
    "loops/chat_loop.py :: ChatLoop._execute_tool_calls :: Appending Tool Result": "trace",
    "loops/chat_loop.py :: ChatLoop._execute_tool_calls :: Appending Tool Error": "trace",
    "loops/chat_loop.py :: ChatLoop.run :: LLM returned empty response": "error",
    "loops/chat_loop.py :: ChatLoop._execute_tool_calls :: Tool '{}' called with missing args": "warning",
    "core/ollama_context_manager.py :: OllamaContextManager.update_from_response :: Context[{}]:": "debug",
    "core/default_context_manager.py :: DefaultContextManager.__init__ :: Context budget: could not read": "warning",
}


@pytest.mark.parametrize("identity,level", sorted(EXPECTED.items()))
def test_frozen_levels(identity, level):
    assert resolve(identity, collect(BATCHES["loops-core"]))["level"] == level
