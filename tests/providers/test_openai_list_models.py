"""OpenAIProvider.list_models: server errors surface, empty listings stay empty."""

import httpx
import openai
import pytest

from ayder_cli.core.config import Config
from ayder_cli.providers.impl.openai import OpenAIProvider

TERMS_403 = {
    "error": {
        "message": "kullanım şartlarının güncel sürümünü (v1) kabul etmeniz gerekiyor",
        "type": "permission_error",
        "param": None,
        "code": "terms_not_accepted",
        "evren": {"required_terms_version": 1},
    }
}


def _provider(response: httpx.Response) -> OpenAIProvider:
    config = Config(base_url="https://api.example.com/v1", api_key="k", model="m")
    provider = OpenAIProvider(config)
    provider.client = openai.AsyncOpenAI(
        base_url=config.base_url,
        api_key="k",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _req: response)),
    )
    return provider


@pytest.mark.asyncio
async def test_list_models_raises_on_http_error():
    provider = _provider(httpx.Response(403, json=TERMS_403))

    with pytest.raises(openai.PermissionDeniedError) as exc_info:
        await provider.list_models()

    assert exc_info.value.code == "terms_not_accepted"


@pytest.mark.asyncio
async def test_list_models_empty_data_returns_empty():
    provider = _provider(httpx.Response(200, json={"object": "list", "data": []}))

    assert await provider.list_models() == []
