"""Supabase storage (PostgREST over HTTPS). Replaces the old data/sessions/*.txt|json|jsonl files.

If SUPABASE_URL / SUPABASE_SERVICE_KEY are not set, `enabled` is False and the app falls back to
memory-only sessions (fine for local tests, but nothing is saved).
"""
from __future__ import annotations

import logging

import httpx

from .config import SUPABASE_SERVICE_KEY, SUPABASE_URL

log = logging.getLogger("db")
enabled = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

_client: httpx.AsyncClient | None = None


def _c() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=f"{SUPABASE_URL}/rest/v1",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            timeout=20)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _send(method: str, path: str, **kw) -> httpx.Response | None:
    """Never raises: a database hiccup must not kill a running discussion."""
    if not enabled:
        return None
    try:
        r = await _c().request(method, path, **kw)
        if r.status_code >= 300:
            log.error("supabase %s %s -> %s %s", method, path, r.status_code, r.text[:200])
            return None
        return r
    except httpx.HTTPError as e:
        log.error("supabase %s %s failed: %s", method, path, e)
        return None


async def insert_session(row: dict) -> None:
    await _send("POST", "/sessions", json=row)


async def update_session(sid: str, fields: dict) -> None:
    await _send("PATCH", "/sessions", params={"id": f"eq.{sid}"}, json=fields)


async def insert_event(row: dict) -> None:
    await _send("POST", "/events", json=row)


async def fetch_session(sid: str) -> dict | None:
    r = await _send("GET", "/sessions", params={"id": f"eq.{sid}", "select": "*"},
                    headers={"Prefer": ""})
    rows = r.json() if r is not None else []
    return rows[0] if rows else None


async def fetch_events(sid: str) -> list[dict]:
    r = await _send("GET", "/events", params={"session_id": f"eq.{sid}", "select": "seq,type,ts,data",
                                              "order": "seq.asc", "limit": "1000"},
                    headers={"Prefer": ""})
    return r.json() if r is not None else []
