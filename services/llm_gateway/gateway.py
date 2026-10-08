"""S1 LLM gateway: the only way modules call a model (CLAUDE.md LLM rules, docs/03 §4, prompts/README.md).

complete_json(prompt, variables, output_model):
  1. load prompts/<prompt>.md (validated at start-up) and check the variables against its front matter;
  2. render with Jinja2 StrictUndefined, prepend _preamble.md;
  3. get a response from the provider (live), the provider plus a cassette write (record), or a cassette (replay);
  4. parse the whole response as JSON and validate it against output_model; on failure retry once with
     _validation_retry.md appended, then fail. Prose is never "best-effort" parsed;
  5. log every attempt to llm_calls with prompt_file and prompt_sha256.
"""
import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ir_core import canonical_json
from services.common.uuid7 import uuid7, uuid7_str

from .cassettes import CassetteStore
from .db import LlmCall
from .prompts import PREAMBLE, RETRY, Prompt, PromptRegistry, PromptVariablesError
from .providers import Provider, ProviderError, ProviderResponse

Mode = Literal["live", "record", "replay"]
M = TypeVar("M", bound=BaseModel)
TRANSPORT_ATTEMPTS = 3  # docs/06: retry provider failures with backoff (3×)
BACKOFF_SECONDS = (0.5, 2.0)


class LLMOutputInvalid(Exception):
    """The response failed validation twice; the job fails (no best-effort parsing)."""


@dataclass(frozen=True)
class LLMCallRecord:
    call_id: str
    correlation_id: str
    prompt_file: str
    prompt_sha256: str
    variables_sha256: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    attempts: int
    mode: Mode


def variables_sha256(variables: dict[str, Any]) -> str:
    try:
        return hashlib.sha256(canonical_json(variables)).hexdigest()
    except (TypeError, ValueError) as e:
        raise PromptVariablesError(f"variables must be JSON values: {e}") from None


class LLMGateway:
    def __init__(self, prompts: PromptRegistry, *, mode: Mode, default_model: str = "",
                 provider: Provider | None = None, cassettes: CassetteStore | None = None,
                 sessionmaker: async_sessionmaker[AsyncSession] | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        if mode in ("live", "record") and provider is None:
            raise ValueError(f"RS_LLM_MODE={mode} needs a configured provider")
        if mode in ("record", "replay") and cassettes is None:
            raise ValueError(f"RS_LLM_MODE={mode} needs a cassette directory")
        self.prompts, self.mode, self.default_model = prompts, mode, default_model
        self.provider, self.cassettes, self.sessionmaker, self.sleep = provider, cassettes, sessionmaker, sleep

    async def complete_json(self, prompt: str, variables: dict[str, Any], output_model: type[M],
                            correlation_id: str | None = None,
                            process_id: str | None = None) -> tuple[M, LLMCallRecord]:
        p = self.prompts.get(prompt)
        if p.output_model != output_model.__name__:
            raise TypeError(f"prompts/{prompt}.md returns {p.output_model}, not {output_model.__name__}")
        vars_sha = variables_sha256(variables)
        body = p.render(variables)
        preamble = self.prompts.get(PREAMBLE).render({})
        schema = output_model.model_json_schema(by_alias=True)
        correlation_id = correlation_id or uuid7_str()
        model = p.model or self.default_model

        error: str | None = None
        tokens_in = tokens_out = 0
        started = time.monotonic()
        for attempt in range(2):
            text = f"{preamble.strip()}\n\n{body.strip()}\n"
            if error is not None:
                text += "\n" + self.prompts.get(RETRY).render({"validation_error": error}).strip() + "\n"
            response, latency = await self._respond(p, text, schema, model, vars_sha, attempt, correlation_id,
                                                    process_id)
            tokens_in += response.input_tokens or 0
            tokens_out += response.output_tokens or 0
            try:
                result = output_model.model_validate(json.loads(response.text))
            except (json.JSONDecodeError, ValidationError) as e:
                error = str(e)
                await self._log(p, response, correlation_id, process_id, "invalid_output", error[:4000], latency)
                continue
            record_id = await self._log(p, response, correlation_id, process_id, "ok", None, latency)
            return result, LLMCallRecord(record_id, correlation_id, p.name, p.sha256, vars_sha, response.model,
                                         tokens_in or None, tokens_out or None,
                                         int((time.monotonic() - started) * 1000), attempt + 1, self.mode)
        raise LLMOutputInvalid(f"prompts/{prompt}.md: response failed validation twice: {error}")

    async def _respond(self, p: Prompt, text: str, schema: dict, model: str, vars_sha: str, attempt: int,
                       correlation_id: str, process_id: str | None) -> tuple[ProviderResponse, int]:
        """The response for one attempt and its latency in ms (0 when replayed)."""
        if self.mode == "replay":
            return self.cassettes.load(p.name, p.sha256, vars_sha, attempt), 0
        for transport_try in range(TRANSPORT_ATTEMPTS):
            started = time.monotonic()
            try:
                response = await self.provider.complete(model=model, prompt=text, temperature=p.temperature,
                                                        json_schema=schema)
                break
            except ProviderError as e:
                await self._log(p, ProviderResponse(text="", model=model), correlation_id, process_id,
                                "provider_error", str(e)[:4000], int((time.monotonic() - started) * 1000))
                if not e.transient or transport_try == TRANSPORT_ATTEMPTS - 1:
                    raise
                await self.sleep(BACKOFF_SECONDS[min(transport_try, len(BACKOFF_SECONDS) - 1)])
        latency = int((time.monotonic() - started) * 1000)
        if self.mode == "record":
            self.cassettes.save(p.name, p.sha256, vars_sha, attempt, response)
        return response, latency

    async def _log(self, p: Prompt, response: ProviderResponse, correlation_id: str, process_id: str | None,
                   status: str, error: str | None, latency_ms: int) -> str:
        row = LlmCall(id=uuid7(), correlation_id=correlation_id, process_id=process_id, prompt_file=p.name,
                      prompt_sha256=p.sha256, model=response.model or "unknown",
                      input_tokens=response.input_tokens, output_tokens=response.output_tokens,
                      latency_ms=latency_ms, status=status, error=error, mode=self.mode)
        if self.sessionmaker is not None:
            # Own transaction: the call is logged even if the caller's work rolls back.
            async with self.sessionmaker() as session:
                session.add(row)
                await session.commit()
        return str(row.id)
