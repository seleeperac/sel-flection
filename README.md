# sel-flection backend (MVP)

FastAPI backend for logging what the user already did (especially today), then viewing simple stats.

Default mode is local-only:
- local login (`/v1/auth/local/login`)
- save logs to local DB (SQLite)
- Google Sheets sync is disabled by default
- AI parsing via local Ollama by default

## 1) Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Health check:
- `GET http://127.0.0.1:8000/health`

## 2) Local login flow

1. Call `POST /v1/auth/local/login`
```json
{
  "email": "me@example.com",
  "name": "Me",
  "timezone": "Asia/Seoul"
}
```
2. Receive `access_token`
3. Use header `Authorization: Bearer <access_token>` for all protected APIs

## 3) Main APIs

- `POST /v1/auth/local/login`
- `GET /v1/me`
- `POST /v1/logs/parse`
- `POST /v1/logs`
- `GET /v1/logs`
- `GET /v1/stats/daily`
- `GET /v1/stats/weekly`
- `GET /v1/stats/monthly`

## 4) Environment variables

Required:
- `APP_SECRET_KEY`

Default local mode:
- `AUTH_MODE=local`
- `ENABLE_GOOGLE_SHEETS=false`
- `AI_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=qwen2.5:7b`

Optional (only if you enable Google mode/sheets):
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `TOKEN_ENCRYPTION_KEY`

Optional (Gemini parser):
- `AI_PROVIDER=gemini`
- `GEMINI_API_KEY`

## 5) Notes

- Ollama quick start:
```bash
ollama serve
ollama pull qwen2.5:7b
```
- Future date saving is blocked.
- `POST /v1/logs` always saves to local DB first.
- When `ENABLE_GOOGLE_SHEETS=false`, response `saved_to_sheet` is always `false`.
- If Ollama fails/unavailable, parser falls back to heuristic mode automatically.
