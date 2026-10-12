# Room in the Box — deployment guide (Supabase + Render + Vercel)

```
Browser ──► Vercel (frontend, /frontend)
              │  VITE_API_BASE_URL
              ▼
           Render (backend, /backend)  ──► Groq (your 7 keys)
              │  SUPABASE_URL + SUPABASE_SERVICE_KEY
              ▼
           Supabase (saved discussions, replaces the txt/json files)
```

## 1. Supabase (database)
1. supabase.com → New project. Save the database password somewhere.
2. Left menu → **SQL Editor** → New query → paste all of `supabase/schema.sql` → **Run**.
3. **Project Settings → API**: copy the **Project URL** and the **service_role** key
   (newer dashboards may call it the "secret" key). This key is a master password: backend only,
   never in the frontend, never on GitHub.

## 2. Your .env file (backend/.env)
A `.env` is a plain text file of `NAME=value` secrets. Your 7 Groq keys are already in
`backend/.env` and were not changed. Paste the two new values:
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
```
`.env` is in `.gitignore`, so it is NOT uploaded to GitHub. Render and Vercel do not read this
file; you paste the same values into their settings (steps 4 and 5).

Optional local test: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000`,
then `cd frontend && npm install && npm run dev`.

## 3. GitHub
Create a repo and push the whole `room-in-the-box` folder (git push, or GitHub's "upload files").
**Do not upload `backend/.env`.**

## 4. Render (backend)
New + → **Web Service** → connect the repo, then:
- Root Directory: `backend`
- Runtime: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Instance Type: Free
- Health Check Path: `/api/health`
- Environment variables (copy each name/value from your `backend/.env`):
  `GROQ_API_KEY_MASTER`, `GROQ_API_KEY_MANAGER`, `GROQ_API_KEY_ROLE1` … `GROQ_API_KEY_ROLE5`,
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ACCESS_TOKEN` (your chosen site password),
  `PYTHON_VERSION` = `3.12.8`, and `CORS_ORIGINS` (set in step 6).
  The other settings in `.env.example` have defaults and are optional.

Copy the service URL (`https://something.onrender.com`). Check `<URL>/api/health` shows `{"ok":true}`.

## 5. Vercel (frontend)
Add New → Project → import the repo:
- Root Directory: `frontend` (Framework: Vite, auto-detected)
- Environment Variable: `VITE_API_BASE_URL` = your Render URL (no trailing slash)
- Deploy. Copy the Vercel URL.

## 6. Connect them
Back in Render → Environment → set `CORS_ORIGINS` to your Vercel URL
(e.g. `https://room-in-the-box.vercel.app`, no trailing slash; add a custom domain too, comma separated).
Save; Render redeploys.

## 7. Test
Open the Vercel site. If you set `ACCESS_TOKEN`, enter it in the site's settings (gear icon).
Start a discussion. In Supabase → Table Editor, `sessions` and `events` should fill up.

## Notes
- Render's free plan sleeps after 15 min idle; the first visit then takes about a minute.
  If it restarts mid-discussion, that discussion shows as "interrupted" (it is still saved up to that point).
- Your Groq keys were visible in the old `.env.example`. Create fresh keys at console.groq.com/keys
  and update them in Render if that file was ever shared.
