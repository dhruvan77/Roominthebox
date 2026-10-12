# Room in the Box — Multi-Agent Studio Frontend

Production-oriented Vite + React frontend for the supplied FastAPI backend.

## Run

1. Start the backend on `http://localhost:8000`.
2. `npm install`
3. `npm run dev`
4. Open the Vite URL.

The frontend defaults to `http://localhost:8000`. Change it from the circular settings button and optionally provide the backend `ACCESS_TOKEN`.

## Backend contract used
- GET `/api/roles`
- POST `/api/discussions`
- GET `/api/discussions/{id}/stream` (SSE)
- GET `/api/discussions/{id}`
- GET `/api/discussions/{id}/conversation`
- POST `/api/discussions/{id}/stop`

SSE events handled: `session`, `status`, `typing`, `message`, `final`, `error`, `done`.

The browser never receives or stores Groq API keys. When `ACCESS_TOKEN` is configured, the token is sent to REST as `X-Access-Token` and to EventSource as `?token=` because native EventSource cannot set arbitrary request headers.
