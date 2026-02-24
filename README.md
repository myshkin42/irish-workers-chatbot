# Irish Workers' Rights Chatbot

An AI-powered chatbot that helps workers in Ireland understand their employment rights. Built on a Retrieval Augmented Generation (RAG) architecture, it answers questions about pay, dismissal, working hours, leave, discrimination, and more — grounded in authoritative Irish and EU legal sources.

## How It Works

A worker asks a question in plain language. The system preprocesses the query, searches a curated corpus of Irish employment law documents, retrieves the most relevant sections, and generates an answer using Claude — citing specific legislation, codes of practice, and official guidance.

```
User: "I was fired without warning after 3 years"

→ Query preprocessing (expansion, synonym mapping)
→ Vector search across 8 namespaces (4,862 vectors)
→ Three-tier retrieval (direct match / LLM rewrite / clarification)
→ Post-retrieval re-ranking (boost authoritative sources)
→ Answer generation with Claude Haiku (grounded in retrieved sources)
→ Response with sources, official links, and WRC complaint guidance
```

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌──────────────┐
│    Frontend     │────▶│    FastAPI Backend    │────▶│   Claude     │
│    (Next.js)    │◀────│                      │     │   Haiku      │
└─────────────────┘     │  ┌────────────────┐  │     └──────────────┘
                        │  │ Query Preproc  │  │
                        │  │ 3-Tier Retriev │  │     ┌──────────────┐
                        │  │ Re-ranking     │  │────▶│  Pinecone    │
                        │  │ Safety Rails   │  │     │  (vectors)   │
                        │  └────────────────┘  │     └──────────────┘
                        └──────────────────────┘
                                   │
                                   ▼              ┌──────────────┐
                              ┌─────────┐        │   OpenAI     │
                              │ Embeddings│◀──────│ text-embed-  │
                              └─────────┘        │ 3-small      │
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
- **Topic–doc_type alignment** (+0.02–0.03): bullying queries boost codes of practice, dismissal queries boost legislation
- **Generic document penalty** (−0.02): demotes catch-all guides like "Safety Representatives Resource Book"

This solved a real problem where a 600-page generic guide was outranking topic-specific codes of practice despite similar cosine scores.

## Query Preprocessing

Before embedding, queries are expanded with Irish employment law context:

- **Synonym expansion**: "fired" → "dismissed unfair dismissal"
- **Acronym expansion**: "WRC" → "workplace relations commission"
- **Topic detection**: "bullying" → adds "dignity at work code of practice"
- **Stopword-aware**: doesn't expand common words

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

## Safety Features

- **Minimum relevance threshold** (0.60): won't generate answers from weak sources
- **Content truncation**: limits context window to prevent hallucination from excessive text
- **System prompt guardrails**: instructs Claude to say "I don't know" rather than speculate
- **Source attribution**: every answer cites specific documents
- **Official links**: always provides WRC and Citizens Information links for verification
- **Disclaimer**: responses are informational, not legal advice

## Project Structure

```
irish-workers-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, chat endpoint, retrieval pipeline
│   │   ├── system_prompt.py       # Ireland-specific system prompt for Claude
│   │   ├── query_preprocessing.py # Synonym expansion, acronym mapping, topic detection
│   │   ├── config.py              # Environment config
│   │   ├── ingest.py              # Document ingestion pipeline (PDF → chunks → vectors)
│   │   ├── reingest.py            # Single-document re-ingestion for updates
│   │   ├── check_currency.py      # Monthly URL monitor for source changes
│   │   ├── test_retrieval.py      # Retrieval regression test suite (15 cases)
│   │   └── test_ingest.py         # Ingestion tests
│   ├── requirements.txt
│   ├── .env.example
│   ├── UPDATE_CALENDAR.md         # Annual update schedule with key dates
│   └── README.md
├── frontend/
│   ├── pages/                     # Next.js pages
│   ├── package.json
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
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux
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
  "answer": "The current national minimum wage in Ireland is...",
  "sources": [
    {"title": "National Minimum Wage Act 2000", "section": "..."}
  ],
  "has_authoritative_sources": true,
  "official_links": [
    {"name": "Workplace Relations Commission", "url": "https://www.workplacerelations.ie"},
    {"name": "Citizens Information", "url": "https://www.citizensinformation.ie"}
  ]
}
```

### `GET /health`
Health check.

### `GET /namespaces`
Lists all Pinecone namespaces and vector counts.

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
| Claude Haiku (answers) | ~$2–4/month |
| Claude Haiku (Tier 2 rewrites, ~10% of queries) | ~$0.10/month |
| OpenAI Embeddings | ~$0.50/month |
| Pinecone (free tier) | Free |
| Fly.io (hosting) | ~$5/month |
| **Total** | **~$8–10/month** |

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
