"""FastAPI app: REST endpoints + Server-Sent Events stream of the live AI group chat."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager
from typing import Union

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import db, llm
from .config import (ACCESS_TOKEN, CORS_ORIGINS, MAX_CONCURRENT_SESSIONS, MAX_ROLES, MAX_TASK_CHARS,
                     MIN_QUERIES, MAX_QUERIES, missing_slots)
from .orchestrator import run_discussion
from .roles import PRESETS, resolve_roles
from .sessions import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not db.enabled:
        logging.getLogger("startup").warning("SUPABASE_URL / SUPABASE_SERVICE_KEY not set: sessions will NOT be saved.")
    if missing_slots():
        logging.getLogger("startup").warning("No API key set for: %s", ", ".join(missing_slots()))
    yield
    for s in list(store.sessions.values()):
        if s.handle and not s.handle.done():
            s.handle.cancel()
    await llm.close()
    await db.close()


app = FastAPI(title="Multi-Agent Group Discussion", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["*"])


def auth(request: Request) -> None:
    if not ACCESS_TOKEN:
        return
    token = request.headers.get("x-access-token") or request.query_params.get("token") or ""
    if not hmac.compare_digest(token, ACCESS_TOKEN):
        raise HTTPException(401, "Invalid or missing access token.")


class RoleIn(BaseModel):
    id: str | None = None
    name: str
    perspective: str | None = None


class StartIn(BaseModel):
    task: str = Field(min_length=3)
    roles: list[Union[str, RoleIn]]


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/roles", dependencies=[Depends(auth)])
async def roles():
    return {"presets": [r.to_dict() for r in PRESETS.values()], "min_roles": 2, "max_roles": MAX_ROLES,
            "min_queries": MIN_QUERIES, "max_queries": MAX_QUERIES}


@app.post("/api/discussions", status_code=201, dependencies=[Depends(auth)])
async def start(body: StartIn):
    task = body.task.strip()
    if len(task) > MAX_TASK_CHARS:
        raise HTTPException(422, f"Task is too long (max {MAX_TASK_CHARS} characters).")
    try:
        roles_ = resolve_roles([r.model_dump() if isinstance(r, RoleIn) else r for r in body.roles])
    except ValueError as e:
        raise HTTPException(422, str(e))

    missing = missing_slots(len(roles_))  # names only, never values
    if missing:
        raise HTTPException(500, "Server is missing API keys for: " + ", ".join(f"GROQ_API_KEY_{m}" for m in missing))
    if store.active_count() >= MAX_CONCURRENT_SESSIONS:
        raise HTTPException(429, "Too many discussions running; try again shortly.")

    session = await store.create(task, roles_)
    session.handle = asyncio.create_task(run_discussion(session))
    return {"id": session.id, "roles": [r.to_dict() for r in roles_]}


@app.get("/api/discussions/{sid}/stream", dependencies=[Depends(auth)])
async def stream(sid: str, request: Request):
    session = await store.get(sid)
    if not session:
        raise HTTPException(404, "Discussion not found.")
    last = request.headers.get("last-event-id", "")
    start_at = int(last) + 1 if last.isdigit() else 0

    async def gen():
        yield "retry: 3000\n\n"
        async for ev in session.stream(start_at):
            if ev is None:
                yield ": keep-alive\n\n"
                continue
            payload = json.dumps({**ev["data"], "seq": ev["seq"], "ts": ev["ts"]}, ensure_ascii=False)
            yield f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {payload}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/discussions/{sid}", dependencies=[Depends(auth)])
async def get_discussion(sid: str):
    session = await store.get(sid)
    if not session:
        raise HTTPException(404, "Discussion not found.")
    return {**session.summary(), "events": session.events}


@app.get("/api/discussions/{sid}/conversation", response_class=PlainTextResponse, dependencies=[Depends(auth)])
async def conversation(sid: str):
    session = await store.get(sid)
    if not session:
        raise HTTPException(404, "Discussion not found.")
    return session.conversation_text()


@app.post("/api/discussions/{sid}/stop", dependencies=[Depends(auth)])
async def stop(sid: str):
    session = await store.get(sid)
    if not session:
        raise HTTPException(404, "Discussion not found.")
    if session.handle and not session.handle.done():
        session.handle.cancel()
    return {"id": sid, "status": "stopping" if not session.finished else session.status}
