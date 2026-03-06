# Irish Workers' Rights Chatbot

An AI-powered chatbot that helps workers in Ireland understand their employment rights. Built on a Retrieval Augmented Generation (RAG) architecture, it answers questions about pay, dismissal, working hours, leave, discrimination, and more — grounded in authoritative Irish and EU legal sources.

**Live:** Frontend on Vercel | Backend on Fly.io (London region)

## How It Works

A worker asks a question in plain language. The system preprocesses the query, searches a curated corpus of Irish employment law documents, retrieves the most relevant sections, and generates an answer using Claude — citing specific legislation, codes of practice, and official guidance.

```
User: "I was fired without warning after 3 years"

→ Greeting/meta check (skip retrieval for "hello", "who are you", etc.)
→ Context-aware follow-up detection (enrich with conversation history if needed)
→ Query preprocessing (expansion, synonym mapping, abbreviation expansion)
→ Vector search across 8 namespaces (4,862 vectors)
→ Three-tier retrieval (direct match / LLM rewrite / clarification)
→ Post-retrieval re-ranking (boost authoritative sources)
→ Answer generation with Claude Haiku (grounded in retrieved sources)
→ Response with sources, official links, and WRC complaint guidance
→ User feedback collection (thumbs up/down)
```

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌──────────────┐
│    Frontend     │────▶│    FastAPI Backend    │────▶│   Claude     │
│   (Next.js /   │◀────│                      │     │   Haiku      │
│    Vercel)      │     │  ┌────────────────┐  │     └──────────────┘
└─────────────────┘     │  │ Greeting Det.  │  │
                        │  │ Context Follow │  │
                        │  │ Query Preproc  │  │     ┌──────────────┐
                        │  │ 3-Tier Retriev │  │────▶│  Pinecone    │
                        │  │ Re-ranking     │  │     │  (vectors)   │
                        │  │ Safety Rails   │  │     └──────────────┘
                        │  │ Query Logging  │  │
                        │  │ Feedback Log   │  │     ┌──────────────┐
                        │  └────────────────┘  │     │   OpenAI     │
                        └──────────────────────┘     │ text-embed-  │
                              Fly.io (London)        │ 3-small      │
                                                     └──────────────┘
```

### Key Design Decisions (vs Australian Version)

| Decision | Australian | Irish | Why |
|----------|-----------|-------|-----|
| Jurisdiction routing | Federal + 6 states | Single national | Ireland has one jurisdiction |
| Industry awards | 100+ award detection | 6 EROs/SEOs | Vastly simpler wage-setting |
| Session management | Server-side Redis | Client-side history | Simpler, cheaper, stateless |
| LLM | OpenAI GPT-4 | Claude Haiku | Better cost/quality for this use case |
| Caching | Redis layer | None | Small corpus doesn't need it |
| Document corpus | ~400 documents | ~172 documents | Manageable single jurisdiction |

## Smart Query Handling

Before hitting the retrieval pipeline, several layers handle queries efficiently:

### Greeting & Meta Detection
Greetings ("Hello", "Hi there") and meta-questions ("Who are you?", "What can you do?") are caught before retrieval, returning a friendly introduction without any API calls to Pinecone or Claude. Saves embedding costs and avoids false Tier 3 clarification responses.

### Context-Aware Follow-Up Detection
When a user sends a short follow-up like "I am a 20 year old apprentice" after asking about minimum wage, the system detects it as a continuation and enriches the search query with context from the previous exchange. Detection requires 2+ signals (short message, pronouns without antecedent, personal statements after a question) to avoid false positives on standalone queries.

### Out-of-Scope Redirects
Tax questions are detected and redirected to Revenue.ie with a friendly explanation, rather than attempting retrieval on topics outside the employment law corpus.

### Input Safety
A pattern-based filter catches obvious prompt injection attempts ("ignore your instructions", "jailbreak", etc.) before they reach the retrieval pipeline. Not intended to catch sophisticated attacks — Claude handles those via its system prompt.

## Three-Tier Retrieval System

The retrieval pipeline uses score thresholds to decide how to handle each query:

| Tier | Score Range | Action | Cost | Example |
|------|-------------|--------|------|---------|
| **T1** | ≥ 0.60 | Answer directly from sources | Free | "I was fired without warning" |
| **T2** | 0.45–0.59 | LLM rewrites query in legal terminology, search again | ~0.1¢ | "Im working 60 hours a week" |
| **T3** | < 0.45 | Ask user for clarification | Free | "what is the time" |

**Tier 2 example:**
- User query: "Im working 60 hours a week"
- Raw score: 0.596 (below threshold)
- Haiku rewrite: "Potential breaches of Working Time Act 1997 regarding maximum weekly working hours"
- Rewritten score: 0.689 → proceeds to answer generation

## Post-Retrieval Re-Ranking

After vector search, a lightweight re-ranker adjusts scores to prefer authoritative sources:

- **Title keyword match** (+0.03): "bullying" in query matches "Code of Practice on Bullying"
- **Topic–doc_type alignment** (+0.02–0.04): bullying queries boost codes of practice, pay queries boost guides over raw legislation
- **Generic document penalty** (−0.02): demotes catch-all guides like "Safety Representatives Resource Book"

This solved a real problem where a 600-page generic guide was outranking topic-specific codes of practice despite similar cosine scores. The re-ranking runs *before* threshold filtering, so borderline-but-correct matches can be boosted over the relevance threshold rather than being discarded.

## Query Preprocessing

Before embedding, queries are expanded with Irish employment law context:

- **Synonym expansion**: "fired" → appends "unfair dismissal termination of employment"
- **Acronym expansion**: "WRC" → replaces with "workplace relations commission"
- **Topic detection**: "bullying" → appends "dignity at work code of practice"
- **Stopword-aware**: doesn't expand common words
- **Deduplication**: caps appended terms at 25 tokens to prevent query dilution

## Document Corpus

**172 documents across 8 namespaces, 4,862 vectors total.**

| Namespace | Vectors | Contents |
|-----------|---------|----------|
| `acts` | 2,468 | 30 primary Acts (Unfair Dismissals, Working Time, Employment Equality, etc.) |
| `guides` | 1,300 | ~85 guides from Citizens Information, WRC, HSA, IHREC, MRCI |
| `codes` | 456 | 18 WRC Codes of Practice (bullying, disconnect, flexible working, etc.) |
| `procedures` | 277 | 17 WRC process guides (adjudication, mediation, appeals) |
| `statutory-instruments` | 186 | 6 S.I.s (minimum wage order, TUPE regulations, etc.) |
| `sectors` | 92 | 5 EROs/SEOs (construction, cleaning, security, childcare) |
| `unions` | 35 | 2 union/JLC overview documents |
| `eu` | 48 | 2 EU directive summaries (Pay Transparency, Platform Workers) |

### Source Hierarchy
The system prioritises guides for accessible explanations while citing legislation for legal authority:
1. **Citizens Information guides** — plain-language explanations workers can understand
2. **WRC Codes of Practice** — authoritative guidance on specific topics
3. **Primary legislation** — the actual legal text for precise references
4. **Sector-specific orders** — ERO/SEO rates for covered industries

### Bilingual Collection
Irish (Gaeilge) documents collected in `data/documents/ga/` — 3 codes of practice and 7 guides. Not yet ingested (English-only for Phase 1).

## Feedback & Monitoring

### Thumbs Up/Down
Each assistant response includes a "Was this helpful?" prompt with thumbs up/down buttons. Feedback is logged to a JSONL file on the Fly volume, paired with the original query and answer for targeted improvement.

### Query Logging
Every query is logged with timestamp, retrieval scores, tier used, and preprocessing metadata. Logs persist on the Fly volume across redeploys.

### Monitoring Endpoints
- `GET /feedback/summary` — aggregated feedback with thumbs up/down counts and recent entries
- `GET /logs?n=50` — recent query logs for debugging retrieval issues

## Safety Features

- **Input injection filtering**: pattern-based filter for obvious prompt injection attempts
- **Minimum relevance threshold** (0.60): won't generate answers from weak sources
- **Content truncation**: limits context window to prevent hallucination from excessive text
- **System prompt guardrails**: instructs Claude to say "I don't know" rather than speculate
- **Source attribution**: every answer cites specific documents
- **Official links**: always provides WRC and Citizens Information links for verification
- **Out-of-scope redirects**: tax questions redirected to Revenue.ie
- **Rate limiting**: 30 requests/minute per IP
- **Disclaimer**: responses are informational, not legal advice

## Project Structure

```
irish-workers-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, chat endpoint, retrieval pipeline,
│   │   │                          # greeting detection, context follow-ups, feedback,
│   │   │                          # query logging, input safety
│   │   ├── system_prompt.py       # Ireland-specific system prompt for Claude
│   │   ├── query_preprocessing.py # Synonym expansion, acronym mapping, topic detection
│   │   ├── config.py              # Environment config
│   │   ├── ingest.py              # Document ingestion pipeline (PDF → chunks → vectors)
│   │   ├── reingest.py            # Single-document re-ingestion for updates
│   │   ├── check_currency.py      # Monthly URL monitor for source changes
│   │   ├── test_retrieval.py      # Retrieval regression test suite (15 cases)
│   │   └── test_ingest.py         # Ingestion tests
│   ├── Dockerfile                 # Fly.io deployment config
│   ├── fly.toml                   # Fly.io app config (London region)
│   ├── requirements.txt
│   ├── .env.example
│   ├── UPDATE_CALENDAR.md         # Annual update schedule with key dates
│   └── README.md
├── frontend/
│   ├── pages/
│   │   └── index.tsx              # Main chat UI with feedback buttons,
│   │                              # mobile-responsive layout, slide-out sidebar
│   ├── package.json
│   ├── vercel.json                # Vercel deployment config
│   └── .env.example
├── data/
│   └── documents/
│       ├── en/                    # English corpus (172 docs across 8 categories)
│       │   ├── acts/              # 30 primary Acts
│       │   ├── codes/             # 18 Codes of Practice
│       │   ├── guides/            # ~85 guides (CI, WRC, HSA, IHREC)
│       │   ├── procedures/        # 17 WRC process guides
│       │   ├── sectors/           # 5 EROs/SEOs
│       │   ├── statutory-instruments/ # 6 S.I.s
│       │   ├── unions/            # 2 union documents
│       │   └── eu/                # 2 EU directive summaries
│       └── ga/                    # Irish (Gaeilge) collection (Phase 2)
│           ├── codes/             # 3 codes
│           └── guides/            # 7 guides
├── irish-chatbot-research.md      # Research notes and document inventory
└── tests/
```

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- API keys: Anthropic (Claude), OpenAI (embeddings), Pinecone (vectors)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Mac/Linux
# venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env           # Add your API keys
```

### Ingest Documents

```bash
python -m app.ingest ../data/documents/en
```

### Run Backend

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

## Deployment

### Backend (Fly.io)

```bash
cd backend
fly deploy
```

The backend runs on Fly.io in the London region (closest to Ireland). Query logs and feedback are stored on a persistent Fly volume at `/data/logs/`.

```bash
# View logs remotely
fly ssh console -C "cat /data/logs/queries.jsonl" > logs_backup.jsonl
fly ssh console -C "cat /data/logs/feedback.jsonl" > feedback_backup.jsonl
```

### Frontend (Vercel)

Deploys automatically on push to `main` via GitHub integration.

## API Endpoints

### `POST /chat`
Main chat endpoint. Accepts a message and optional conversation history.

**Request:**
```json
{
  "message": "What is the minimum wage in Ireland?",
  "history": [
    {"role": "user", "content": "previous question"},
    {"role": "assistant", "content": "previous answer"}
  ]
}
```

**Response:**
```json
{
  "answer": "The current national minimum wage in Ireland is €14.15...",
  "sources": [
    {"title": "National Minimum Wage Act 2000", "doc_type": "guide", "relevance": 0.72}
  ],
  "has_authoritative_sources": true,
  "official_links": [
    {"name": "Workplace Relations Commission", "url": "https://www.workplacerelations.ie"},
    {"name": "Citizens Information", "url": "https://www.citizensinformation.ie/en/employment/"}
  ],
  "disclaimer": "This is general information only, not legal advice...",
  "knowledge_base_updated": "2026-02-01"
}
```

### `POST /feedback`
Submit thumbs up/down on a response.

**Request:**
```json
{
  "message": "What is the minimum wage?",
  "answer": "The current national minimum wage...",
  "feedback": "up"
}
```

### `GET /health`
Health check — reports API, Pinecone, and namespace status.

### `GET /metadata`
Frontend metadata — disclaimer, knowledge base version, official sources, important contacts.

### `GET /namespaces`
Lists all Pinecone namespaces and vector counts.

### `GET /feedback/summary`
Aggregated feedback stats and recent entries.

### `GET /logs?n=50`
Recent query logs for debugging.

## Testing

### Retrieval Test Suite

```bash
# Full suite (15 test cases covering all major topics)
python -m app.test_retrieval

# Verbose mode (shows failure details)
python -m app.test_retrieval -v

# Single query (interactive debugging)
python -m app.test_retrieval -q "I am being bullied at work"
```

Current results: **15/15 PASS**

## Keeping Content Up to Date

Three tools for managing currency:

### 1. Monthly URL Check

```bash
python -m app.check_currency           # Check for changes
python -m app.check_currency --reset   # Store baseline (first run)
```

Monitors 14 key source URLs (Citizens Information, WRC, HSA, IHREC, ICTU, Irish Statute Book) and flags any pages that have changed since last check.

### 2. Single-Document Re-Ingestion

```bash
python -m app.reingest --list-namespaces                    # See what's there
python -m app.reingest --list-docs guides                   # List docs in namespace
python -m app.reingest --file path/to/doc.pdf --namespace guides --replace
```

Updates individual documents without rebuilding the whole index.

### 3. Annual Calendar

See `backend/UPDATE_CALENDAR.md` for key dates:
- **January**: Minimum wage update, sick leave day count
- **March/April**: ERO/SEO rate reviews
- **June 2026**: EU Pay Transparency Directive transposition deadline
- **October**: Budget announcements
- **End 2026**: EU Platform Workers Directive deadline

## Cost Estimates

At 1,000 queries/month:

| Service | Cost |
|---------|------|
| Claude Haiku (answers) | ~€2–4/month |
| Claude Haiku (Tier 2 rewrites, ~10% of queries) | ~€0.10/month |
| OpenAI Embeddings | ~€0.50/month |
| Pinecone (free tier) | Free |
| Fly.io (hosting) | ~€5/month |
| Vercel (frontend, free tier) | Free |
| **Total** | **~€8–10/month** |

## Key Legal Topics Covered

Based on WRC complaint statistics:

1. **Pay** (27% of complaints) — minimum wage, deductions, overtime, payslips
2. **Unfair Dismissal** (15%) — grounds, constructive dismissal, procedures
3. **Discrimination** (14%) — 9 protected grounds, harassment, equal pay
4. **Working Time** (9%) — 48-hour week, breaks, rest periods, night work
5. **Terms of Employment** (9%) — contracts, changes, banded hours
6. **Leave** — annual, sick (5 days 2025), maternity, paternity, parental, carer's
7. **Bullying & Harassment** — codes of practice, dignity at work
8. **Redundancy** — eligibility, calculation, notice periods
9. **WRC Procedures** — complaints, adjudication, mediation, appeals, time limits
10. **Sector-Specific** — construction, cleaning, security, childcare rates

## EU Law Integration

Irish employment law largely transposes EU directives. The system acknowledges EU foundations where relevant and tracks upcoming changes:

- **Pay Transparency Directive** (transposition deadline: June 2026) — salary disclosure, pay gap reporting
- **Platform Workers Directive** (transposition deadline: ~end 2026) — gig worker protections
- **Adequate Minimum Wages Directive** — collective bargaining requirements

---

*Built by Eamon with Claude | February 2026*
