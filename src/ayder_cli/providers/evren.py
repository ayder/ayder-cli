"""evren LLM gateway: terms-of-use acceptance.

The gateway (https://evren-llmapi.ssyz.org.tr) is OpenAI-compatible but refuses every
call with HTTP 403 ``terms_not_accepted`` until the account accepts the current terms.
"""

from dataclasses import dataclass
from typing import Final

from openai import AsyncOpenAI

from ayder_cli.core.config import Config

EVREN_HOST: Final[str] = "evren-llmapi.ssyz.org.tr"


@dataclass(frozen=True)
class EvrenTerms:
    """One published version of the evren terms of use."""

    version: int
    content: str


def is_evren_terms_error(base_url: str | None, exc: BaseException) -> bool:
    """True when ``exc`` is evren refusing a call until its terms are accepted."""
    return False


def make_client(config: Config) -> AsyncOpenAI:
    """Build a client for the provider's configured base URL and key."""
    return AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)


async def fetch_terms(client: AsyncOpenAI) -> EvrenTerms:
    """Fetch the current terms text."""
    return EvrenTerms(0, "")


async def accept_terms(client: AsyncOpenAI, version: int) -> int:
    """Accept terms ``version``; return the version the server recorded."""
    return 0
