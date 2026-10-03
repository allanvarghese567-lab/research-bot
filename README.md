# Research Bot

A complete research agent that answers investment-style questions with evidence, calibrated confidence, and source links. **Research only — never financial advice.**

## Architecture

| Layer | Tech |
|-------|------|
| Database / Auth / Realtime | Supabase (Postgres + RLS + Realtime) |
| Worker | Python + LangGraph on GitHub Actions (cron + `repository_dispatch`) |
| API (optional instant trigger) | FastAPI |
| Frontend | React + Vite + TypeScript + Tailwind + Recharts + `@supabase/supabase-js` |
| LLMs | Free-tier Groq / Gemini (OpenAI-compatible) + OpenRouter fallback |

## Project layout

```
research-bot/
├── supabase/migration.sql      # schema, RLS, realtime, view
├── worker/
│   ├── worker.py               # LangGraph agent
│   ├── requirements.txt
│   └── .env.example
├── api/
│   ├── main.py                 # FastAPI (POST /requests/{id}/run)
│   ├── requirements.txt
│   └── .env.example
├── web/                        # React SPA
│   ├── src/
│   ├── package.json
│   └── .env.example
├── .github/workflows/research-worker.yml
├── scripts/test_e2e.py
└── README.md
```

## 1. Supabase setup

1. Create a new Supabase project.
2. Open **SQL Editor** → paste and run `supabase/migration.sql`.
3. In **Authentication → Providers** enable Email.
4. Copy:
   - Project URL → `SUPABASE_URL`
   - `anon` key → frontend `VITE_SUPABASE_ANON_KEY`
   - `service_role` key → worker + API `SUPABASE_SERVICE_KEY`
   - JWT Secret (Project Settings → API → JWT Settings) → API `SUPABASE_JWT_SECRET`
5. Confirm **Realtime** is enabled for `research_requests` and `tickets` (the migration adds them to the publication).

## 2. GitHub Secrets

In the repo **Settings → Secrets and variables → Actions** add:

| Secret | Required | Notes |
|--------|----------|-------|
| `SUPABASE_URL` | ✅ | |
| `SUPABASE_SERVICE_KEY` | ✅ | service_role key |
| `GROQ_API_KEY` | ✅ (or Gemini) | free tier |
| `GEMINI_API_KEY` | recommended | free tier |
| `OPENROUTER_API_KEY` | optional | fallback on 429 |
| `TAVILY_API_KEY` | optional | better search; falls back to ddgs |
| `TG_TOKEN` / `TG_CHAT_ID` | optional | Telegram notifications |

Optional provider overrides: `JUDGE_PROVIDER`, `ANALYST_PROVIDER`, `FALLBACK_PROVIDER`.

## 3. Local development

### Worker

```bash
cd worker
cp .env.example .env   # fill keys
pip install -r requirements.txt
python worker.py
```

### API

```bash
cd api
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd web
cp .env.example .env   # VITE_SUPABASE_* and optional VITE_API_URL
npm install
npm run dev            # http://localhost:5173
```

## 4. Triggering the worker

- **Hourly cron** (default)
- **Manual**: Actions → Research worker → Run workflow
- **Instant** (via API): frontend calls `POST /requests/{id}/run` which fires a `repository_dispatch` event (`research_request`). Requires a GitHub PAT with `repo` scope in the API env (`GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`).

## 5. End-to-end test

```bash
export SUPABASE_URL=...
export SUPABASE_SERVICE_KEY=...
export TEST_USER_ID=<an existing auth.users uuid>
python scripts/test_e2e.py
```

The script inserts a pending request and polls until a ticket appears (or errors).

## Notes

- Worker copies `user_id` from the request into every ticket (required by RLS).
- Failed runs set `status = 'error'` and store `error_message`.
- LLM calls use LangChain `with_fallbacks` so a 429 on the primary provider switches to the fallback.
- Never outputs buy/sell commands — only evidence, stance, confidence, risks, and sources.
