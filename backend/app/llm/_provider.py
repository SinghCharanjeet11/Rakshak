"""Provider seam.

03-backend.md §3 promises that swapping model providers touches only the two agent
files. Hoisting the client, the pricing table and the usage accounting into one private
module makes it a *one*-file change instead, and keeps the two agent modules about their
prompts rather than about plumbing. Everything above `llm/` stays untouched either way —
the orchestrator, the membrane and `core/` never learn who the provider is.

**OPEN-1 lives here.** `01-architecture.md` frames the orchestration layer on the Claude
Agent SDK while `03-backend.md` §3 specifies OpenAI. This implements the documented
OpenAI contract. Switching to Anthropic means rewriting `complete_json()` below and
nothing else.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import BaseModel

from app.config import settings

log = logging.getLogger("rakshak.llm")

# USD per 1M tokens (gpt-4o-mini list price, 03-backend.md §3 cost note).
PRICE_PER_M_INPUT_USD = 0.15
PRICE_PER_M_OUTPUT_USD = 0.60
# Only used to express the run budget in rupees; a stale rate skews the cost metric,
# never a verdict.
USD_TO_INR = 88.0


class LLMUnavailable(Exception):
    """The model layer was required and could not be reached.

    Surfaces as HTTP 502 with the "submit format:json to bypass parsing" hint. It is
    never raised for the explanation call, which degrades to no prose instead
    (invariant I9).
    """


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_inr(self) -> float:
        usd = (
            self.prompt_tokens / 1_000_000 * PRICE_PER_M_INPUT_USD
            + self.completion_tokens / 1_000_000 * PRICE_PER_M_OUTPUT_USD
        )
        return round(usd * USD_TO_INR, 6)


class LLMResponse(BaseModel):
    data: dict[str, Any]
    usage: Usage = Usage()
    tool_calls: list[str] = []


def _client() -> Any:
    if not settings.llm_enabled:
        raise LLMUnavailable("OPENAI_API_KEY is not set")
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailable(f"openai SDK not installed: {exc}") from exc
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def complete_json(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
) -> LLMResponse:
    """One constrained-JSON call.

    `response_format={"type": "json_object"}` enforces JSON *validity* at the API level,
    so a malformed-syntax response cannot happen. It does not enforce schema
    correctness — that is exactly what the Pydantic re-validation wall is for, which is
    why the membrane stays mandatory regardless (03-backend.md §3).

    No `tools=` argument is passed anywhere in this module. The ingestion agent has
    literally nothing to invoke, so an injection payload inside a submitted log has no
    reachable surface. See `INGESTION_TOOLS` in ingestion_agent.py.
    """
    client = _client()
    try:
        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=temperature,
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except Exception as exc:
        raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc

    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:  # pragma: no cover - json_object mode prevents this
        raise LLMUnavailable(f"provider returned non-JSON despite json_object mode: {exc}") from exc

    usage = Usage(
        prompt_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
    )
    called = [c.function.name for c in (resp.choices[0].message.tool_calls or [])]
    return LLMResponse(data=data if isinstance(data, dict) else {}, usage=usage, tool_calls=called)
