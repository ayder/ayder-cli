"""evren terms helpers: error detection, terms fetch, terms acceptance."""

import json

import httpx
import openai
import pytest

from ayder_cli.providers.evren import EvrenTerms, accept_terms, fetch_terms, is_evren_terms_error

EVREN = "https://evren-llmapi.ssyz.org.tr/v1"
TERMS_CONTENT = "# EVREN Kullanım Şartları\n\nMadde 1."


def _status_error(cls: type[openai.APIStatusError], status: int, code: str) -> openai.APIStatusError:
    request = httpx.Request("GET", f"{EVREN}/models")
    body = {"message": "refused", "type": "permission_error", "param": None, "code": code}
    return cls("refused", response=httpx.Response(status, request=request), body=body)


TERMS_403 = _status_error(openai.PermissionDeniedError, 403, "terms_not_accepted")


@pytest.mark.parametrize(
    ("base_url", "exc", "expected"),
    [
        (EVREN, TERMS_403, True),
        ("https://evren-llmapi.ssyz.org.tr/", TERMS_403, True),
        ("https://api.example.com/v1", TERMS_403, False),
        (EVREN, _status_error(openai.PermissionDeniedError, 403, "forbidden"), False),
        (EVREN, _status_error(openai.NotFoundError, 404, "terms_not_accepted"), False),
        (EVREN, RuntimeError("terms_not_accepted"), False),
        (None, TERMS_403, False),
    ],
)
def test_is_evren_terms_error(base_url, exc, expected):
    assert is_evren_terms_error(base_url, exc) is expected


def _client(responses: dict[str, httpx.Response], requests: list[httpx.Request]) -> openai.AsyncOpenAI:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses[request.url.path]

    return openai.AsyncOpenAI(
        base_url=EVREN,
        api_key="k",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_fetch_terms():
    requests: list[httpx.Request] = []
    body = {"version": 1, "doc_path": "docs/legal/x.md", "content": TERMS_CONTENT}
    client = _client({"/v1/terms/text": httpx.Response(200, json=body)}, requests)

    assert await fetch_terms(client) == EvrenTerms(version=1, content=TERMS_CONTENT)
    assert [(r.method, r.url.path) for r in requests] == [("GET", "/v1/terms/text")]
    assert requests[0].headers["Authorization"] == "Bearer k"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_body",
    [
        {"accepted_version": 1, "accepted_at": "2026-09-29T11:27:40.291459+00:00"},
        {},
    ],
)
async def test_accept_terms(response_body):
    requests: list[httpx.Request] = []
    client = _client({"/v1/terms/accept": httpx.Response(200, json=response_body)}, requests)

    assert await accept_terms(client, 1) == 1
    assert [(r.method, r.url.path) for r in requests] == [("POST", "/v1/terms/accept")]
    assert json.loads(requests[0].content) == {"version": 1}

