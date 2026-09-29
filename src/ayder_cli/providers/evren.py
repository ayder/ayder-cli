"""evren LLM gateway: terms-of-use acceptance.

The gateway (https://evren-llmapi.ssyz.org.tr) is OpenAI-compatible but refuses every
call with HTTP 403 ``terms_not_accepted`` until the account accepts the current terms.
"""

from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from openai import AsyncOpenAI, PermissionDeniedError

from ayder_cli.core.config import Config

EVREN_HOST: Final[str] = "evren-llmapi.ssyz.org.tr"


@dataclass(frozen=True)
class EvrenTerms:
    """One published version of the evren terms of use."""

    version: int
    content: str


def is_evren_terms_error(base_url: str | None, exc: BaseException) -> bool:
    """True when ``exc`` is evren refusing a call until its terms are accepted."""
    if not base_url or urlsplit(base_url).hostname != EVREN_HOST:
        return False
    return isinstance(exc, PermissionDeniedError) and exc.code == "terms_not_accepted"


def make_client(config: Config) -> AsyncOpenAI:
    """Build a client for the provider's configured base URL and key."""
    return AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)


async def fetch_terms(client: AsyncOpenAI) -> EvrenTerms:
    """Fetch the current terms text.

    Raises the SDK's ``APIError`` on a failed request and ``ValueError`` on a
    response without an integer ``version`` and a string ``content``.
    """
    data = await client.get("terms/text", cast_to=object)
    if not isinstance(data, dict):
        raise ValueError(f"unexpected evren terms response: {data!r}")
    version, content = data.get("version"), data.get("content")
    if not isinstance(version, int) or not isinstance(content, str):
        raise ValueError(f"unexpected evren terms response: {data!r}")
    return EvrenTerms(version, content)


async def accept_terms(client: AsyncOpenAI, version: int) -> int:
    """Accept terms ``version``; return the version the server recorded.

    Falls back to ``version`` when the response does not name one. Raises the
    SDK's ``APIError`` on a failed request.
    """
    data = await client.post("terms/accept", body={"version": version}, cast_to=object)
    accepted = data.get("accepted_version") if isinstance(data, dict) else None
    return accepted if isinstance(accepted, int) else version
