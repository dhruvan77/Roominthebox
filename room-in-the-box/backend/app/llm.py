"""Groq client (OpenAI-compatible API) for openai/gpt-oss-120b, with retry/backoff."""
from __future__ import annotations

import asyncio
import logging

import httpx

from . import mock
from .config import (GROQ_BASE_URL, GROQ_MODEL, LLM_CONCURRENCY, LLM_RETRIES,
                     LLM_TIMEOUT, REASONING_EFFORT, TEMPERATURE, USE_MOCK, get_key)

log = logging.getLogger("llm")
_client: httpx.AsyncClient | None = None
_sems: dict[str, asyncio.Semaphore] = {}  # one limiter per API key / slot

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMError(Exception):
    """Non-recoverable model failure (message never contains the API key)."""


class _Retryable(Exception):
    def __init__(self, msg: str, delay: float | None = None):
        super().__init__(msg)
        self.delay = delay


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=LLM_TIMEOUT)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _groq(slot: str, system: str, user: str, max_tokens: int) -> str:
    body: dict = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        # gpt-oss is a reasoning model: reasoning tokens count toward this limit
        "max_completion_tokens": max_tokens,
        "reasoning_effort": REASONING_EFFORT,
    }
    if TEMPERATURE is not None:
        body["temperature"] = TEMPERATURE
    try:
        r = await _http().post(f"{GROQ_BASE_URL}/chat/completions",
                               headers={"Authorization": f"Bearer {get_key(slot)}"}, json=body)
    except httpx.HTTPError as e:
        raise _Retryable(type(e).__name__) from None
    if r.status_code in RETRY_STATUS:
        try:
            delay = float(r.headers.get("retry-after", ""))
        except ValueError:
            delay = None
        raise _Retryable(f"HTTP {r.status_code}", delay)
    if r.status_code >= 400:
        raise LLMError(f"{slot}: Groq returned HTTP {r.status_code}: {r.text[:300]}")
    try:
        choice = r.json()["choices"][0]
        text = (choice["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, ValueError):
        raise _Retryable("unexpected response shape") from None
    if not text:
        raise _Retryable(f"empty response (finish_reason={choice.get('finish_reason')})")
    return text


async def complete(slot: str, purpose: str, system: str, user: str, max_tokens: int = 1500) -> str:
    """slot: MASTER | MANAGER | ROLE1..ROLE5 (selects the API key).
    purpose: master_initial | master_final | manager | role (for logging and the mock)."""
    if USE_MOCK:
        return mock.complete(purpose, system, user)
    last = "unknown error"
    for attempt in range(LLM_RETRIES + 1):
        try:
            sem = _sems.setdefault(slot, asyncio.Semaphore(LLM_CONCURRENCY))
            async with sem:
                return await _groq(slot, system, user, max_tokens)
        except _Retryable as e:
            last = str(e)
            log.warning("Groq %s (%s) attempt %d failed: %s", slot, purpose, attempt + 1, last)
            if attempt < LLM_RETRIES:
                await asyncio.sleep(min(e.delay if e.delay is not None else 2 ** attempt * 2, 30))
    raise LLMError(f"{slot}: Groq failed after {LLM_RETRIES + 1} attempts ({last})")
