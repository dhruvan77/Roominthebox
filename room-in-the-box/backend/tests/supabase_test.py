"""Verifies Supabase storage + re-hydration using a fake PostgREST server:  python tests/supabase_test.py"""
import asyncio, os, sys, json
os.environ.update(USE_MOCK="1", MIN_QUERIES="10", MAX_QUERIES="24",
                  SUPABASE_URL="https://fake.supabase.co", SUPABASE_SERVICE_KEY="fake")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from app import db
from app.sessions import store

TABLES = {"sessions": [], "events": []}

def handler(req: httpx.Request) -> httpx.Response:
    t = req.url.path.split("/")[-1]
    q = dict(req.url.params)
    if req.method == "POST":
        TABLES[t].append(json.loads(req.content)); return httpx.Response(201)
    if req.method == "PATCH":
        sid = q["id"][3:]
        for r in TABLES[t]:
            if r["id"] == sid: r.update(json.loads(req.content))
        return httpx.Response(204)
    rows = TABLES[t]
    if t == "sessions": rows = [r for r in rows if r["id"] == q["id"][3:]]
    else: rows = sorted([r for r in rows if r["session_id"] == q["session_id"][3:]], key=lambda r: r["seq"])
    return httpx.Response(200, json=rows)

db._client = httpx.AsyncClient(base_url="https://fake.supabase.co/rest/v1", transport=httpx.MockTransport(handler))

from app.orchestrator import run_discussion
from app.roles import resolve_roles

async def main():
    s = await store.create("Pick a hackathon idea.", resolve_roles(["student", "professor", "judge"]))
    await run_discussion(s)
    assert s.status == "completed"
    row = TABLES["sessions"][0]
    assert row["status"] == "completed" and row["final"] and row["conversation"].startswith("USER:")
    assert len(TABLES["events"]) == len(s.events) and len(s.events) > 20
    store.sessions.clear()                      # simulate server restart / spin-down
    s2 = await store.get(s.id)
    assert s2 and s2.status == "completed" and s2.final == s.final and len(s2.events) == len(s.events)
    assert "FINAL ANSWER:" in s2.conversation_text()
    print("SUPABASE STORAGE TEST PASSED:", len(s2.events), "events saved and reloaded")
asyncio.run(main())
