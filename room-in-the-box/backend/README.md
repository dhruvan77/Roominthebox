# Room in the Box — Backend (FastAPI + Supabase)

FastAPI backend where a **Master AI**, a **Manager AI**, up to **eight configurable role AIs** (presets and any number of custom ones) and a **Concluder**
hold a live, Manager-orchestrated group discussion and converge on a final answer.
API keys live only in the server environment and are never sent to the browser.

```
USER → MASTER (opening) → [ MANAGER picks ONE role → that role replies ]×N → WRAP-UP turn → CONCLUDER → MASTER (final answer)
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
| `GROQ_API_KEY_CONCLUDER` | Concluder (optional; reuses the Master key if empty) |
| `GROQ_API_KEY_ROLE1` … `GROQ_API_KEY_ROLE10` | roles in selection order; with more roles than keys they share keys round-robin |
| `GROQ_API_KEY` | optional fallback for any empty slot |

Every call carries the agent's role prompt plus the shared history from `conversation.txt`.
gpt-oss is a reasoning model, so token limits are generous and `REASONING_EFFORT` (default `low`) keeps
turns fast. A discussion makes roughly 25–40 model calls; the client retries 429s and honours `Retry-After`.

## Endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/roles` | Preset roles + limits (min/max roles, min/max steps) |
| `POST /api/discussions` | Start. Body: `{"task": "...", "roles": ["student", {"name": "Lawyer", "perspective": "..."}, {"name": "CFO", "perspective": "..."}], "turn_mode": "auto"\|"manual", "turns": 5}` (2–`MAX_ROLES` roles, any mix of presets and custom; `turns` only for manual, clamped to 2–`MAX_QUERIES`). Returns `{id, roles, turn_mode, turns}` |
| `GET /api/discussions/{id}/stream` | **SSE** live group chat (supports `Last-Event-ID` reconnect/replay) |
| `GET /api/discussions/{id}` | Status, final answer and all events |
| `GET /api/discussions/{id}/conversation` | The shared `conversation.txt` |
| `POST /api/discussions/{id}/stop` | Cancel a running discussion |

If `ACCESS_TOKEN` is set, send it as `X-Access-Token` header or `?token=` (needed for `EventSource`).

### SSE events

`session` · `status` · `typing` · `message` · `final` · `error` · `done`

`message` data: `{speaker, kind: "master"|"manager"|"role"|"concluder"|"system", text, role_id?, query?, targets?, step?, phase?}` where `phase` is `explore|narrow|converge|wrapup|concluder`.
`done` data: `{status: "completed"|"error"|"cancelled"}`.

```js
const es = new EventSource(`/api/discussions/${id}/stream`);
es.addEventListener("message", e => addBubble(JSON.parse(e.data)));
es.addEventListener("final",   e => showFinal(JSON.parse(e.data).text));
es.addEventListener("done",    () => es.close());
```

## How it works

- **One turn = one AI message.** The Master's opening is not counted. Each turn the Manager picks exactly one
  role and a short instruction, based on what was actually said; that role replies. Replies can be one line or
  a short paragraph (the prompts allow both, up to ~130 words).
- **Length is exact in MANUAL mode.** With `turns = N`: turns 1…N-2 are open discussion, turn **N-1 is the wrap-up**
  (any role, chosen by the Manager, states the decision it believes was reached) and turn **N is the Concluder**.
  Example: 5 → turns 1-3 discuss, turn 4 starts the conclusion, turn 5 is the Concluder.
- **AUTO mode.** After `MIN_QUERIES` turns the Manager may output `["conclude"]` (optionally `["conclude","role_id"]`).
  That turn becomes the wrap-up and the Concluder follows. Earlier attempts are rejected; `MAX_QUERIES` is a hard
  cap (wrap-up at cap-1, Concluder at cap).
- **Everyone paces themselves.** Every prompt says which turn it is, how many remain and the current phase:
  `explore` (distinct views) → `narrow` (resolve disagreements) → `converge` (commit/concede) → `wrapup`.
- **The Concluder** appears only at the end, reads the whole transcript and writes the decision
  (Decision / Why it won / Trade-offs & dissent / Next steps) as a chat message of `kind: "concluder"`.
  The Master then turns that decision into the final answer (`final` event); the Concluder's ruling is binding.
- **Manager output** is JSON and tolerant (code fences, ids or names); it retries with a correction and falls back to
  the role that has been quiet longest, so the loop never stalls.
- **Shared memory**: every message goes into the shared transcript and each agent receives it on every call
  (oldest middle trimmed past `MAX_HISTORY_CHARS`). Sessions and events are saved to Supabase; the turn settings are
  stored in the first `session` event, so **no schema change is needed**.
- **Safeguards**: task length cap, concurrent-session cap, retries with backoff, abort after 3 consecutive agent
  failures, key names (never values) in errors, CORS allow-list, optional access token.

Note: a discussion keeps running if the browser tab closes (so it can be resumed via the stream
endpoint); call `/stop` to cancel and save API spend.

## Layout

```
app/  config.py roles.py memory.py llm.py (Groq client) mock.py routing.py plan.py agents.py sessions.py orchestrator.py main.py
tests/smoke_test.py
```
