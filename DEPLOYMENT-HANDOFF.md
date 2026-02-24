# Irish Workers' Rights Chatbot - Deployment Handoff

## Current State (2026-02-24)

### What's Working
- **Backend**: FastAPI on `localhost:8000` — fully functional
- **Frontend**: Next.js 16.1.6 on `localhost:3400` — fully functional
- **Retrieval**: Three-tier system (static preprocessing → LLM rewrite → clarification)
- **Re-ranking**: Post-retrieval boosts applied BEFORE threshold filtering
- **Markdown**: react-markdown rendering in frontend
- **Test suite**: 15/15 passing (`python -m app.test_retrieval`)
- **Vector DB**: Pinecone (free tier), 4,862 vectors across 8 namespaces

### Project Structure
```
C:\Projects\irish-workers-chatbot\
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, retrieval, re-ranking, chat endpoint
│   │   ├── system_prompt.py     # Claude system prompt
│   │   ├── query_preprocessing.py # Tier 1 static expansions
│   │   ├── ingest.py            # Document ingestion to Pinecone
│   │   ├── reingest.py          # Selective re-ingestion
│   │   ├── check_currency.py    # Document currency checker
│   │   ├── test_retrieval.py    # Retrieval test suite
│   │   └── config.py
│   ├── .env                     # API keys (ANTHROPIC, PINECONE, OPENAI)
│   ├── requirements.txt
│   └── UPDATE_CALENDAR.md       # Document update schedule
├── frontend/
│   ├── pages/
│   │   ├── index.tsx            # Main chat UI
│   │   └── _app.tsx             # Global wrapper
│   ├── next.config.js
│   └── package.json
├── data/
│   └── documents/
│       ├── en/                  # English docs (8 subdirs)
│       └── ga/                  # Irish language docs
└── tests/
```

### Tech Stack
- **Backend**: Python 3, FastAPI, Anthropic SDK, Pinecone, OpenAI (embeddings only)
- **Frontend**: Next.js 16.1.6, React 18, TypeScript, react-markdown
- **Vector DB**: Pinecone (free tier, us-east-1, cosine metric)
- **LLM**: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- **Embeddings**: OpenAI `text-embedding-3-small` (1536 dim)

### Environment Variables Needed (.env)
```
ANTHROPIC_API_KEY=sk-ant-...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=irish-workers-chatbot
OPENAI_API_KEY=sk-...
API_BEARER_TOKEN=...          # Optional, for production auth
ENVIRONMENT=development       # Change to "production" for deploy
```

### Frontend Environment
```
NEXT_PUBLIC_API_URL=http://localhost:8000   # Change to production URL for deploy
```

### Deployment Plan (Australian version used)
- **Pinecone**: Already deployed (free tier, persistent)
- **GitHub**: Code repo (needs initial push)
- **Fly.io**: Backend (FastAPI) — Australian version used this
- **Vercel**: Frontend (Next.js) — Australian version used this
- **CORS**: Already configured for `*.vercel.app` (regex in main.py)

### Key Configuration Notes
1. **Port 3400 locally** — Windows Hyper-V reserves 3000-3105. Not relevant for deployment.
2. **CORS in main.py**: Already has Vercel regex (`https://.*\.vercel\.app`). Will need Fly.io URL added.
3. **Rate limiting**: 30/minute per IP via slowapi
4. **Auth**: Optional bearer token (skipped in development mode)
5. **Pinecone index**: `irish-workers-chatbot` — already populated, no re-ingestion needed for deploy

### Things to Watch During Deployment
- Backend needs `--host 0.0.0.0` for Fly.io (not just localhost)
- Frontend `NEXT_PUBLIC_API_URL` must point to Fly.io URL
- Fly.io secrets for all env vars (ANTHROPIC_API_KEY, PINECONE_API_KEY, OPENAI_API_KEY)
- Vercel env var for `NEXT_PUBLIC_API_URL`
- May need Dockerfile for Fly.io backend
- `requirements.txt` should be frozen (`pip freeze > requirements.txt`)
