"""What the chat loop tells the user when the LLM call fails.

Kind: baseline regression. openai 3.x builds ``"Error code: <status>"`` and appends only
a mapping body's ``error.message``. Gemini's OpenAI-compatible endpoint sends a JSON
*list*, so the text is the bare status and the reason sits unused on ``exc.body``.

The exceptions are the ones the installed SDKs really raise, built over an httpx2
``MockTransport``; no request leaves the process (environment: local-faked).
"""

from __future__ import annotations

import asyncio

import httpx2
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from tests.loops.test_chat_loop_guards import _loop, _Provider, _Registry, _tool


def _http_client(status: int, **response_kwargs) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(status, **response_kwargs))
    )


def _openai_error(status: int, **response_kwargs) -> Exception:
    """The exception a streamed ``chat.completions.create`` raises for ``status``."""

    async def go() -> Exception:
        client = AsyncOpenAI(
            base_url="http://mock/v1",
            api_key="x",
            max_retries=0,
            http_client=_http_client(status, **response_kwargs),
        )
        try:
            stream = await client.chat.completions.create(
                model="m", messages=[{"role": "user", "content": "hi"}], stream=True
            )
            async for _ in stream:
                pass
        except Exception as exc:  # noqa: BLE001 - the test wants the SDK's exception
            return exc
        raise AssertionError("the mock transport should have produced an error")

    return asyncio.run(go())


def _anthropic_error(status: int, **response_kwargs) -> Exception:
    async def go() -> Exception:
        client = AsyncAnthropic(
            base_url="http://mock",
            api_key="x",
            max_retries=0,
            http_client=_http_client(status, **response_kwargs),
        )
        try:
            async with client.messages.stream(
                model="m", max_tokens=8, messages=[{"role": "user", "content": "hi"}]
            ) as stream:
                async for _ in stream:
                    pass
        except Exception as exc:  # noqa: BLE001 - the test wants the SDK's exception
            return exc
        raise AssertionError("the mock transport should have produced an error")

    return asyncio.run(go())


class _Raising:
    """A provider whose stream fails before the first chunk."""

    def __init__(self, exc: Exception):
        self.exc = exc

    async def stream_with_tools(self, *a, **k):
        raise self.exc
        yield  # pragma: no cover - makes this an async generator


def _reported(exc: Exception) -> list[str]:
    loop = _loop(_Raising(exc))
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))
    return loop.cb.system


_GEMINI_404 = [
    {"error": {"code": 404, "status": "NOT_FOUND", "message": "model retired; use gemini-2.5-flash"}}
]


def test_a_list_body_is_shown_after_the_status():
    """Baseline regression: the loop reports a bare ``Error: Error code: 404`` today."""
    (message,) = _reported(_openai_error(404, json=_GEMINI_404))

    assert message.startswith("Error: Error code: 404 - ")
    assert "model retired; use gemini-2.5-flash" in message


def test_an_unrecognised_mapping_body_is_shown_after_the_status():
    """Baseline regression: a body without ``error.message`` is dropped today."""
    (message,) = _reported(_openai_error(404, json={"detail": "Not Found"}))

    assert message == 'Error: Error code: 404 - {"detail": "Not Found"}'


def test_an_openai_shaped_body_is_unchanged():
    """Preservation: the SDK already appends ``error.message``; it is not shown twice."""
    exc = _openai_error(400, json={"error": {"message": "bad model", "type": "x"}})

    assert _reported(exc) == ["Error: Error code: 400 - bad model"]


def test_an_anthropic_error_is_unchanged():
    """Preservation: anthropic already puts the body in its message."""
    exc = _anthropic_error(
        404,
        json={"type": "error", "error": {"type": "not_found_error", "message": "no model"}},
    )

    assert _reported(exc) == [f"Error: {exc}"]
    assert "no model" in str(exc)


def test_a_plain_exception_is_unchanged():
    """Preservation: an exception without a status or body prints as before."""
    assert _reported(RuntimeError("Qwen API failed: boom")) == ["Error: Qwen API failed: boom"]


def test_a_long_body_is_cut_at_2000_characters_with_a_tail():
    """Baseline regression: the body is not shown at all today; unbounded would flood."""
    (message,) = _reported(_openai_error(502, text="<html>" + "x" * 5000 + "</html>"))

    prefix = "Error: Error code: 502 - "
    assert message.startswith(prefix + "<html>")
    shown, _, tail = message[len(prefix) :].partition("... (")
    assert len(shown) == 2000
    assert tail == f"{len('<html>' + 'x' * 5000 + '</html>') - 2000} more chars)"


# --- loop.error: which stops end the turn in an error (the CLI exits 1) -----------

def _run(loop) -> None:
    asyncio.run(asyncio.wait_for(loop.run(), timeout=5))


def test_a_stream_failure_sets_error():
    """New interface: ChatLoop has no ``error`` today."""
    loop = _loop(_Raising(RuntimeError("boom")))
    _run(loop)

    assert loop.error == "Error: boom"
    assert loop.cb.system == ["Error: boom"]


def test_the_max_iterations_stop_sets_error():
    """New interface: ChatLoop has no ``error`` today."""
    loop = _loop(_Provider(_tool()), max_iterations=3)
    _run(loop)

    assert loop.error is not None and loop.error.startswith("Error:")
    assert "max_iterations = 3" in loop.error
    assert loop.cb.system == [loop.error]


def test_an_empty_response_sets_error():
    """New interface: ChatLoop has no ``error`` today."""
    loop = _loop(_Provider({}))
    _run(loop)

    assert loop.error is not None and "empty response" in loop.error
    assert loop.cb.system == [loop.error]


def test_the_reasoning_only_limit_sets_error():
    """New interface: ChatLoop has no ``error`` today."""
    loop = _loop(_Provider({"reasoning": "hmm"}))
    _run(loop)

    assert loop.error is not None and loop.error.startswith("Error:")
    assert "only reasoning" in loop.error
    assert loop.cb.system == [loop.error]


def test_a_text_reply_leaves_error_unset():
    """Preservation: a normal turn is not an error."""
    loop = _loop(_Provider({"content": "hi"}))
    _run(loop)

    assert loop.error is None


def test_an_escalation_stop_leaves_error_unset():
    """Preservation: escalation hands control back to the user; it is not a failure."""

    class _EscalatingRegistry(_Registry):
        def execute(self, name, arguments):
            super().execute(name, arguments)
            return '{"action": "escalate"}'

    loop = _loop(_Provider(_tool()), registry=_EscalatingRegistry())
    _run(loop)

    assert any("Escalation requested" in s for s in loop.cb.system)
    assert loop.error is None


def test_error_is_cleared_when_the_loop_runs_again():
    """The TUI reuses one loop: a later good turn must not inherit an earlier failure."""
    loop = _loop(_Raising(RuntimeError("boom")))
    _run(loop)
    assert loop.error == "Error: boom"

    loop.llm = _Provider({"content": "recovered"})
    loop.messages.append({"role": "user", "content": "again"})
    _run(loop)

    assert loop.error is None
