"""Discussion sessions: live in memory while running (replayable SSE stream), saved to Supabase."""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

from . import db
from .memory import Transcript
from .roles import Role

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def conversation_from_events(task: str, events: list[dict]) -> str:
    """Rebuild conversation text for sessions that were interrupted (server restarted mid-run)."""
    out = [f"USER:\n{task}\n\n"]
    for ev in events:
        d = ev.get("data") or {}
        if ev["type"] == "message":
            if d.get("kind") == "manager":
                out.append(f"MANAGER:\nAsk: {d.get('query', '')}\n\n")
            else:
                out.append(f"{d.get('speaker', '')}:\n{d.get('text', '')}\n\n")
        elif ev["type"] == "final":
            out.append(f"FINAL ANSWER:\n{d.get('text', '')}\n\n")
    return "".join(out)


@dataclass
class Session:
    id: str
    task: str
    roles: list[Role]
    status: str = "running"  # running | completed | error | cancelled | interrupted
    events: list[dict] = field(default_factory=list)
    final: str | None = None
    transcript: Transcript | None = None
    handle: asyncio.Task | None = None
    conversation: str | None = None
    _cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    _writes: set = field(default_factory=set)

    @property
    def finished(self) -> bool:
        return self.status != "running"

    def conversation_text(self) -> str:
        if self.transcript is not None:
            return self.transcript.full_text()
        return self.conversation or conversation_from_events(self.task, self.events)

    async def emit(self, type_: str, **data) -> dict:
        async with self._cond:
            ev = {"seq": len(self.events), "type": type_, "ts": round(time.time(), 3), "data": data}
            self.events.append(ev)
            if db.enabled:  # fire-and-forget so the live chat is never slowed by the database
                t = asyncio.create_task(db.insert_event({"session_id": self.id, **ev}))
                self._writes.add(t)
                t.add_done_callback(self._writes.discard)
            self._cond.notify_all()
        return ev

    async def finish(self, status: str) -> None:
        await self.emit("done", status=status)
        if self._writes:
            await asyncio.gather(*list(self._writes), return_exceptions=True)
        await db.update_session(self.id, {"status": status, "final": self.final,
                                          "conversation": self.conversation_text()})
        async with self._cond:
            self.status = status
            self._cond.notify_all()

    async def stream(self, start: int = 0) -> AsyncIterator[dict | None]:
        """Yields events from `start`; yields None periodically as a keep-alive."""
        idx = start
        while True:
            batch, keepalive = None, False
            async with self._cond:
                if idx < len(self.events):
                    batch = self.events[idx:]
                elif self.finished:
                    return
                else:
                    try:
                        await asyncio.wait_for(self._cond.wait(), 15)
                    except asyncio.TimeoutError:
                        keepalive = True
            if batch:
                for ev in batch:
                    yield ev
                idx += len(batch)
            elif keepalive:
                yield None

    def summary(self) -> dict:
        return {"id": self.id, "task": self.task, "roles": [r.to_dict() for r in self.roles],
                "status": self.status, "final": self.final}


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def active_count(self) -> int:
        return sum(1 for s in self.sessions.values() if not s.finished)

    async def create(self, task: str, roles: list[Role]) -> Session:
        sid = uuid.uuid4().hex
        s = Session(id=sid, task=task, roles=roles, transcript=Transcript())
        self.sessions[sid] = s
        await db.insert_session({"id": sid, "task": task, "roles": [r.to_dict() for r in roles],
                                 "status": "running"})
        return s

    async def get(self, sid: str) -> Session | None:
        if not _ID_RE.match(sid or ""):
            return None
        if sid in self.sessions:
            return self.sessions[sid]
        return await self._load(sid)

    async def _load(self, sid: str) -> Session | None:
        """Re-hydrate a session from Supabase (e.g. after the server restarted or spun down)."""
        row = await db.fetch_session(sid)
        if not row:
            return None
        s = Session(id=sid, task=row["task"], roles=[Role(**r) for r in row["roles"]],
                    status=row.get("status") or "interrupted", final=row.get("final"),
                    conversation=row.get("conversation"))
        s.events = await db.fetch_events(sid)
        if s.status == "running":  # it was running when the server stopped; nothing is running it now
            s.status = "interrupted"
        self.sessions[sid] = s
        return s


store = SessionStore()
