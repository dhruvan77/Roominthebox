# Room in the Box — Backend (FastAPI + Supabase)

FastAPI backend where a **Master AI**, a **Manager AI** and up to **five configurable role AIs**
hold a live, Manager-orchestrated group discussion and converge on a final answer.
API keys live only in the server environment and are never sent to the browser.

```
USER → MASTER → MANAGER → [roles] → MANAGER → [roles] → … → MANAGER: ["conclude"] → FINAL ANSWER
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste your 6 Groq keys
uvicorn app.main:app --reload --port 8000
```

No key yet? `python tests/smoke_test.py` runs the full flow offline with scripted replies (`USE_MOCK=1`). Docker: `docker build -t agents . && docker run --env-file .env -p 8000:8000 agents`.

## Model & API keys

All agents run **Groq `openai/gpt-oss-120b`**, each on its own key (6 total, server-side only):

| Env var | Agent |
|---|---|
| `GROQ_API_KEY_MASTER` | Master AI |
| `GROQ_API_KEY_MANAGER` | Manager AI |
| `GROQ_API_KEY_ROLE1` … `GROQ_API_KEY_ROLE5` | 1st … 5th role the user selects (selection order) |
| `GROQ_API_KEY` | optional fallback for any empty slot |

Every call carries the agent's role prompt plus the shared history from `conversation.txt`.
gpt-oss is a reasoning model, so token limits are generous and `REASONING_EFFORT` (default `low`) keeps
turns fast. A discussion makes roughly 25–40 model calls; the client retries 429s and honours `Retry-After`.

## Endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/roles` | Preset roles + limits (min/max roles, min/max steps) |
| `POST /api/discussions` | Start. Body: `{"task": "...", "roles": ["student", "judge", {"name": "Lawyer", "perspective": "..."}]}` (2–5 roles: preset ids or custom). Returns `{id}` |
| `GET /api/discussions/{id}/stream` | **SSE** live group chat (supports `Last-Event-ID` reconnect/replay) |
| `GET /api/discussions/{id}` | Status, final answer and all events |
| `GET /api/discussions/{id}/conversation` | The shared `conversation.txt` |
| `POST /api/discussions/{id}/stop` | Cancel a running discussion |

If `ACCESS_TOKEN` is set, send it as `X-Access-Token` header or `?token=` (needed for `EventSource`).

### SSE events

`session` · `status` · `typing` · `message` · `final` · `error` · `done`

`message` data: `{speaker, kind: "master"|"manager"|"role"|"system", text, role_id?, query?, targets?, step?}`.
`done` data: `{status: "completed"|"error"|"cancelled"}`.

```js
const es = new EventSource(`/api/discussions/${id}/stream`);
es.addEventListener("message", e => addBubble(JSON.parse(e.data)));
es.addEventListener("final",   e => showFinal(JSON.parse(e.data).text));
es.addEventListener("done",    () => es.close());
```

## How it works

- **Manager output** is JSON: `["<message>", ["student","judge"]]` or `["conclude"]`. Parsing tolerates
  code fences/prose, accepts role ids or names, and retries twice with a correction; if it stays
  unusable the backend falls back to routing to the least-heard role so the loop never stalls.
- **Routing is dynamic**: the Manager sees the full transcript and picks who speaks based on what was
  actually said — no fixed rotation. Roles addressed in the same step answer sequentially, so the
  second can react to the first.
- **Shared memory**: every message is appended to `data/sessions/<id>/conversation.txt`
  (plus `events.jsonl`, `meta.json`, `final.txt`). Each agent gets that history on every call
  (oldest middle trimmed past `MAX_HISTORY_CHARS`, keeping the task, the Master's opening and recent turns).
- **Length**: the backend rejects `conclude` before `MIN_QUERIES` (default 10) routing steps and tells the
  Manager to keep going; `MAX_QUERIES` (default 24) is a hard cap.
- **Conclusion**: on `["conclude"]` the loop stops, the transcript is preserved, and the Master writes the
  final answer from the whole discussion.
- **Safeguards**: task length cap, concurrent-session cap, retries with backoff, abort after 3
  consecutive agent failures, key names (never values) in errors, CORS allow-list, optional access token.

Note: a discussion keeps running if the browser tab closes (so it can be resumed via the stream
endpoint); call `/stop` to cancel and save API spend.

## Layout

```
app/  config.py roles.py memory.py llm.py (Groq client) mock.py routing.py agents.py sessions.py orchestrator.py main.py
tests/smoke_test.py
```
