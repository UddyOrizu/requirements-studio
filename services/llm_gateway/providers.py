"""Model providers. The gateway talks to one through this interface; modules never see a provider or SDK."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ProviderError(Exception):
    """A failed provider call. Transient errors (rate limits, timeouts, 5xx) are retried with backoff."""

    def __init__(self, message: str, *, transient: bool = True):
        super().__init__(message)
        self.transient = transient


class Provider(Protocol):
    async def complete(self, *, model: str, prompt: str, temperature: float,
                       json_schema: dict[str, Any]) -> ProviderResponse: ...
