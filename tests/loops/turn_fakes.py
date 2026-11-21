"""Shared fakes for the chat-loop turn tests (environment: local-faked).

A scripted provider, recording callbacks, a recording registry and a context
manager stand in for everything ``ChatLoop`` talks to, so a whole turn runs
without a network, a UI or a real tool. The turn-integrity plan reuses these
in every step, so they stay general: tests choose what each piece does.

The provider replays one scripted list per LLM call. A script item is a stream
chunk, an exception (raised when the stream reaches it) or a ``Stall`` (the
stream waits there until the test releases it). The callbacks log every call,
in order, and raise from any callback a test names.
"""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace
from typing import Any, Callable

from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig
from ayder_cli.providers.base import NormalizedStreamChunk, ToolCallDef

DEFAULT_PERMISSIONS = frozenset({"r", "w", "x", "http"})
TURN_TIMEOUT = 5.0


# -- Scripted provider ---------------------------------------------------------


def chunk(
    content: str = "",
    reasoning: str = "",
    usage: dict[str, int] | None = None,
    calls: tuple[ToolCallDef, ...] | list[ToolCallDef] = (),
) -> NormalizedStreamChunk:
    """One stream chunk. ``calls`` are the tool-call deltas it carries."""
    built = NormalizedStreamChunk(content=content, reasoning=reasoning, usage=usage)
    built.tool_calls = list(calls)
    return built


def delta(
    id: str = "",
    name: str = "",
    arguments: str = "",
    index: int | None = None,
    thought_signature: str | None = None,
) -> ToolCallDef:
    """A tool-call delta as a provider yields it.

    ``index`` is the provider's stream position (``_stream_index``, which the
    OpenAI driver sets); None leaves the attribute off, as the other drivers do.
    """
    call = ToolCallDef(id=id, name=name, arguments=arguments, thought_signature=thought_signature)
    if index is not None:
        setattr(call, "_stream_index", index)
    return call


class Stall:
    """A point in a scripted stream where the provider waits for ``release``.

    ``entered`` is set when the stream reaches the stall, so a test can act
    while the turn is parked there (cancel it, raise a signal, ...). A stream
    that is cancelled at the stall never resumes.
    """

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()


class ScriptedProvider:
    """Replays one scripted item list per LLM call; the last list repeats.

    ``iterations`` are lists of ``NormalizedStreamChunk``, exceptions and
    ``Stall`` objects. ``calls`` counts the LLM calls made and ``requests``
    keeps a copy of the messages each call was given.
    """

    def __init__(self, *iterations: list[Any]) -> None:
        if not iterations:
            raise ValueError("a script needs at least one iteration")
        self.iterations = [list(items) for items in iterations]
        self.calls = 0
        self.requests: list[list[dict]] = []

    async def stream_with_tools(self, messages, model=None, tools=None, options=None, verbose=False):
        index = min(self.calls, len(self.iterations) - 1)
        self.calls += 1
        self.requests.append(copy.deepcopy(list(messages)))
        # Yield to the event loop, so a loop that never ends still lets the
        # test's wait_for time out instead of hanging the suite.
        await asyncio.sleep(0)
        for item in self.iterations[index]:
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, Stall):
                item.entered.set()
                await item.release.wait()
                continue
            yield item


# -- Recording callbacks -------------------------------------------------------

_Raises = BaseException | Callable[..., None]


class RecordingCallbacks:
    """``ChatCallbacks`` that logs every call, in order, and can raise on demand.

    ``calls`` holds ``(callback name, arguments)`` for every call, including
    ``is_cancelled`` polls; ``of(*names)`` filters it. ``raises`` maps a
    callback name to an exception (raised after the call is logged) or to a
    function that receives the call's arguments and may raise. ``confirm`` is
    what ``request_confirmation`` answers: an action string (``approve``,
    ``deny`` or ``instruct``), None (the dialog was closed), or a function of
    the tool name and arguments that returns one of those.
    """

    def __init__(
        self,
        *,
        confirm: str | None | Callable[[str, dict], Any] = "approve",
        raises: dict[str, _Raises] | None = None,
        cancelled: bool = False,
    ) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.confirm = confirm
        self.raises: dict[str, _Raises] = dict(raises or {})
        self.cancelled = cancelled

    def _note(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        spec = self.raises.get(name)
        if spec is None:
            return
        if isinstance(spec, BaseException):
            raise spec
        spec(*args)

    def of(self, *names: str) -> list[tuple[str, tuple]]:
        """The logged calls to the named callbacks, in order."""
        return [call for call in self.calls if call[0] in names]

    @property
    def system(self) -> list[str]:
        return [args[0] for _, args in self.of("on_system_message")]

    def starts_by_key(self) -> dict[str, list[tuple[str, dict]]]:
        """``on_tool_start`` calls as ``{call_id: [(name, arguments), ...]}``."""
        grouped: dict[str, list[tuple[str, dict]]] = {}
        for _, (call_id, name, arguments) in self.of("on_tool_start"):
            grouped.setdefault(call_id, []).append((name, arguments))
        return grouped

    def completes_by_key(self) -> dict[str, list[str]]:
        """``on_tool_complete`` calls as ``{call_id: [result, ...]}``."""
        grouped: dict[str, list[str]] = {}
        for _, (call_id, result) in self.of("on_tool_complete"):
            grouped.setdefault(call_id, []).append(result)
        return grouped

    def on_thinking_start(self) -> None:
        self._note("on_thinking_start")

    def on_thinking_stop(self) -> None:
        self._note("on_thinking_stop")

    def on_assistant_content(self, text: str) -> None:
        self._note("on_assistant_content", text)

    def on_thinking_content(self, text: str) -> None:
        self._note("on_thinking_content", text)

    def on_token_usage(self, total_tokens: int) -> None:
        self._note("on_token_usage", total_tokens)

    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None:
        self._note("on_tool_start", call_id, name, arguments)

    def on_tool_complete(self, call_id: str, result: str) -> None:
        self._note("on_tool_complete", call_id, result)

    def on_tools_cleanup(self) -> None:
        self._note("on_tools_cleanup")

    def on_system_message(self, text: str) -> None:
        self._note("on_system_message", text)

    async def request_confirmation(self, name: str, arguments: dict) -> object | None:
        self._note("request_confirmation", name, arguments)
        answer = self.confirm(name, arguments) if callable(self.confirm) else self.confirm
        if answer is None or not isinstance(answer, str):
            return answer
        return SimpleNamespace(action=answer, instructions="do X instead")

    def is_cancelled(self) -> bool:
        self._note("is_cancelled")
        return self.cancelled


# -- Recording registry and context --------------------------------------------


class RecordingRegistry:
    """A tool registry that records what ran.

    ``calls`` holds ``(name, arguments)`` for every executed call. ``results``
    maps a tool name to its result (``default`` otherwise); ``raises`` maps a
    tool name to an exception raised when it runs.
    """

    def __init__(
        self,
        *,
        results: dict[str, Any] | None = None,
        raises: dict[str, BaseException] | None = None,
        default: Any = "ok",
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.results = dict(results or {})
        self.raises = dict(raises or {})
        self.default = default

    def execute(self, name: str, arguments: dict) -> Any:
        self.calls.append((name, dict(arguments)))
        if name in self.raises:
            raise self.raises[name]
        return self.results.get(name, self.default)

    def get_schemas(self, tags=None) -> list:
        return []


class FakeContext:
    """A context manager that trims nothing and records the usage it is given.

    ``raises`` maps ``prepare_messages`` or ``update_from_response`` to an
    exception raised when that method is called.
    """

    session_id = None
    run_id = None

    def __init__(self, *, raises: dict[str, BaseException] | None = None) -> None:
        self.raises = dict(raises or {})
        self.usage: list[Any] = []

    def prepare_messages(self, messages, max_history=0):
        if "prepare_messages" in self.raises:
            raise self.raises["prepare_messages"]
        return list(messages)

    def update_from_response(self, usage) -> None:
        self.usage.append(usage)
        if "update_from_response" in self.raises:
            raise self.raises["update_from_response"]


# -- Building and running a turn -----------------------------------------------


def make_loop(
    provider: Any,
    *,
    registry: RecordingRegistry | None = None,
    callbacks: RecordingCallbacks | None = None,
    context: FakeContext | None = None,
    messages: list[dict] | None = None,
    permissions: set[str] | frozenset[str] = DEFAULT_PERMISSIONS,
    **config: Any,
) -> ChatLoop:
    """A ``ChatLoop`` over the fakes. Read them back as ``loop.registry``,
    ``loop.cb`` and ``loop.context_manager``; ``config`` goes to ``ChatLoopConfig``."""
    return ChatLoop(
        llm=provider,
        registry=registry or RecordingRegistry(),
        messages=(
            messages
            if messages is not None
            else [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}]
        ),
        config=ChatLoopConfig(permissions=set(permissions), **config),
        callbacks=callbacks or RecordingCallbacks(),
        context_manager=context or FakeContext(),
    )


def run_turn(loop: ChatLoop, *, timeout: float = TURN_TIMEOUT, **kwargs: Any) -> None:
    """Run one turn to its end; a turn that never ends times out instead of hanging."""
    asyncio.run(asyncio.wait_for(loop.run(**kwargs), timeout=timeout))


def tool_messages(loop: ChatLoop) -> list[dict]:
    """The ``tool`` messages in the loop's history, in order."""
    return [m for m in loop.messages if m["role"] == "tool"]


def assistant_calls(loop: ChatLoop) -> list[dict]:
    """Every tool call recorded on an assistant message, in history order."""
    return [call for m in loop.messages if m["role"] == "assistant" for call in m.get("tool_calls", [])]
