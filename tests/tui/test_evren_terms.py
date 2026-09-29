"""/model listing: surfaced server errors and the evren terms-acceptance modal.

HTTP is faked with httpx.MockTransport; the 403 body is the one the evren gateway
returned before the account accepted its terms (2026-09-29).
"""

import json
from typing import Callable
from unittest.mock import patch

import httpx
import openai
import pytest
from textual.app import App
from textual.widgets import Markdown

from ayder_cli.core.config import Config
from ayder_cli.providers.impl.openai import OpenAIProvider
from ayder_cli.tui.commands import _list_and_show_models
from ayder_cli.tui.screens import CLISelectScreen, EvrenTermsScreen

EVREN = "https://evren-llmapi.ssyz.org.tr/v1"
OTHER = "https://api.example.com/v1"

TERMS_403 = {
    "error": {
        "message": (
            "kullanım şartlarının güncel sürümünü (v1) kabul etmeniz gerekiyor - metni GET "
            '/v1/terms/text ile okuyup POST /v1/terms/accept {"version": 1} ile onaylayın'
        ),
        "type": "permission_error",
        "param": None,
        "code": "terms_not_accepted",
        "evren": {"required_terms_version": 1},
    }
}
TERMS_TEXT = {
    "version": 1,
    "doc_path": "docs/legal/x.md",
    "content": "# EVREN Kullanım Şartları\n\nMadde 1.",
}
ACCEPTED = {"accepted_version": 1, "accepted_at": "2026-09-29T11:27:40.291459+00:00"}
MODELS = {
    "object": "list",
    "data": [
        {"id": "deepseek-v4-flash", "object": "model", "created": 0, "owned_by": "evren"},
        {"id": "dots-ocr", "object": "model", "created": 0, "owned_by": "evren"},
    ],
}
EMPTY = {"object": "list", "data": []}


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeGateway:
    """Serves /v1/models from a queue (the last entry repeats) and the terms endpoints."""

    def __init__(self, models: list[httpx.Response], terms_text: httpx.Response | None = None):
        self.models = models
        self.terms_text = terms_text or httpx.Response(200, json=TERMS_TEXT)
        self.requests: list[tuple[str, str, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        if request.url.path == "/v1/models":
            return self.models.pop(0) if len(self.models) > 1 else self.models[0]
        if request.url.path == "/v1/terms/text":
            return self.terms_text
        if request.url.path == "/v1/terms/accept":
            return httpx.Response(200, json=ACCEPTED)
        return httpx.Response(404)

    def calls(self, method: str, path: str) -> list[object]:
        return [body for m, p, body in self.requests if m == method and p == path]


class ChatRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def add_system_message(self, text: str) -> None:
        self.messages.append(text)


class HarnessApp(App):
    """The slice of AyderApp that /model listing touches."""

    def __init__(self, base_url: str, gateway: FakeGateway) -> None:
        super().__init__()
        self.config = Config(provider="openai", base_url=base_url, api_key="k", model="m")
        self.model = "m"
        self.client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key="k",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(gateway)),
        )
        self.llm = OpenAIProvider(self.config)
        self.llm.client = self.client
        self.pushed: list[type] = []

    def push_screen(self, screen, *args, **kwargs):  # type: ignore[override]
        self.pushed.append(type(screen))
        return super().push_screen(screen, *args, **kwargs)

    def request_turn(self, prepare: Callable[[], None], run_loop: bool = True) -> None:
        prepare()

    def update_system_prompt_model(self) -> None:
        pass


async def _until(pilot, condition: Callable[[], bool]) -> None:
    for _ in range(100):
        if condition():
            return
        await pilot.pause(0.01)


async def _run_listing(base_url: str, gateway: FakeGateway, then=None):
    """Run /model listing in the harness; `then(app, pilot)` drives the modal."""
    app = HarnessApp(base_url, gateway)
    chat = ChatRecorder()
    with patch("ayder_cli.providers.evren.make_client", return_value=app.client):
        async with app.run_test() as pilot:
            await _list_and_show_models(app, chat)  # type: ignore[arg-type]
            await pilot.pause()
            if then is not None:
                await then(app, pilot)
    return app, chat


@pytest.mark.anyio
async def test_model_listing_error_is_surfaced():
    gateway = FakeGateway([httpx.Response(403, json=TERMS_403)])

    app, chat = await _run_listing(OTHER, gateway)

    assert any(m.startswith("Error listing models:") and "403" in m for m in chat.messages), chat.messages
    assert not any(m.startswith("Current model:") for m in chat.messages)
    assert EvrenTermsScreen not in app.pushed
    assert not [r for r in gateway.requests if r[1].startswith("/v1/terms/")]


@pytest.mark.anyio
async def test_empty_listing_shows_current_model():
    gateway = FakeGateway([httpx.Response(200, json=EMPTY)])

    _app, chat = await _run_listing(OTHER, gateway)

    assert chat.messages == ["Current model: m"]


@pytest.mark.anyio
async def test_evren_terms_approve():
    gateway = FakeGateway(
        [httpx.Response(403, json=TERMS_403), httpx.Response(200, json=MODELS)]
    )
    seen: dict[str, object] = {}

    async def approve(app, pilot):
        assert isinstance(app.screen, EvrenTermsScreen)
        seen["content"] = app.screen.query_one("#terms-content", Markdown).source
        seen["focused"] = app.focused.id if app.focused else None
        await pilot.click("#terms-approve")
        await _until(pilot, lambda: isinstance(app.screen, CLISelectScreen))
        seen["select_items"] = getattr(app.screen, "items", None)

    _app, chat = await _run_listing(EVREN, gateway, approve)

    assert "Madde 1." in str(seen["content"])
    assert seen["focused"] == "terms-deny"
    assert gateway.calls("POST", "/v1/terms/accept") == [{"version": 1}]
    assert any("evren" in m and "v1" in m and "ccepted" in m for m in chat.messages), chat.messages
    assert seen["select_items"] == [("deepseek-v4-flash", "deepseek-v4-flash"), ("dots-ocr", "dots-ocr")]


@pytest.mark.anyio
@pytest.mark.parametrize("how", ["escape", "click"])
async def test_evren_terms_deny(how):
    gateway = FakeGateway([httpx.Response(403, json=TERMS_403)])

    async def deny(app, pilot):
        assert isinstance(app.screen, EvrenTermsScreen)
        if how == "escape":
            await pilot.press("escape")
        else:
            await pilot.click("#terms-deny")
        await _until(pilot, lambda: not isinstance(app.screen, EvrenTermsScreen))
        assert not isinstance(app.screen, EvrenTermsScreen)

    _app, chat = await _run_listing(EVREN, gateway, deny)

    assert gateway.calls("POST", "/v1/terms/accept") == []
    assert any("evren" in m and "not accepted" in m for m in chat.messages), chat.messages


@pytest.mark.anyio
async def test_evren_terms_second_refusal():
    gateway = FakeGateway([httpx.Response(403, json=TERMS_403)])

    async def approve(app, pilot):
        assert isinstance(app.screen, EvrenTermsScreen)
        await pilot.click("#terms-approve")
        await _until(pilot, lambda: len(gateway.calls("GET", "/v1/models")) >= 2)
        await pilot.pause(0.05)

    app, chat = await _run_listing(EVREN, gateway, approve)

    assert app.pushed.count(EvrenTermsScreen) == 1
    assert len(gateway.calls("POST", "/v1/terms/accept")) == 1
    assert any(m.startswith("Error listing models:") for m in chat.messages), chat.messages


@pytest.mark.anyio
async def test_evren_terms_text_failure():
    gateway = FakeGateway(
        [httpx.Response(403, json=TERMS_403)],
        terms_text=httpx.Response(500, json={"error": {"message": "boom", "code": "http_500"}}),
    )

    app, chat = await _run_listing(EVREN, gateway)

    assert any("evren" in m and "500" in m for m in chat.messages), chat.messages
    assert EvrenTermsScreen not in app.pushed
    assert gateway.calls("POST", "/v1/terms/accept") == []
