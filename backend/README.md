# Irish Workers' Rights Chatbot — Backend

FastAPI backend with RAG retrieval pipeline. See the [main README](../README.md) for full project documentation.

## Quick Start

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # Add API keys
uvicorn app.main:app --reload --port 8000
```

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, chat endpoint, 3-tier retrieval, re-ranking |
| `app/system_prompt.py` | Ireland-specific system prompt for Claude |
| `app/query_preprocessing.py` | Synonym expansion, acronym mapping, topic detection |
| `app/ingest.py` | Full corpus ingestion (PDF → chunks → Pinecone) |
| `app/reingest.py` | Single-document re-ingestion for updates |
| `app/check_currency.py` | Monthly URL monitor for source changes |
| `app/test_retrieval.py` | Retrieval regression test suite |
| `app/config.py` | Environment variable configuration |
| `UPDATE_CALENDAR.md` | Annual schedule for content updates |

## Commands

```bash
# Run server
uvicorn app.main:app --reload --port 8000

# Run retrieval tests (15 cases)
python -m app.test_retrieval
python -m app.test_retrieval -v                      # verbose
python -m app.test_retrieval -q "your query here"    # single query

# Ingest full corpus
python -m app.ingest ../data/documents/en

# Re-ingest a single document
python -m app.reingest --list-namespaces
python -m app.reingest --list-docs guides
python -m app.reingest --file path/to/doc.pdf --namespace guides --replace

# Monthly currency check
python -m app.check_currency
python -m app.check_currency --reset                 # first run: store baselines
```

## Retrieval Pipeline

```
User query
  → Query preprocessing (synonyms, acronyms, topic expansion)
  → Embedding (OpenAI text-embedding-3-small)
  → Vector search (Pinecone, 8 namespaces)
  → Three-tier threshold check:
      T1 (≥0.60): proceed to answer
      T2 (0.45–0.59): Haiku rewrites query, search again
      T3 (<0.45): ask user for clarification
  → Post-retrieval re-ranking (title match, type alignment, generic penalty)
  → Context formatting (top 5 sources)
  → Answer generation (Claude Haiku with system prompt)
  → Response with sources + official links
```

## Pinecone Index

**Index:** `irish-workers-chatbot` | **4,862 vectors** | **8 namespaces**

| Namespace | Vectors | Content |
|-----------|---------|---------|
| acts | 2,468 | Primary legislation |
| guides | 1,300 | CI, WRC, HSA, IHREC guides |
| codes | 456 | WRC Codes of Practice |
| procedures | 277 | WRC process guides |
| statutory-instruments | 186 | S.I.s |
| sectors | 92 | EROs/SEOs |
| eu | 48 | EU directive summaries |
| unions | 35 | Union information |

## Environment Variables

```
ANTHROPIC_API_KEY=       # Claude Haiku (chat + Tier 2 rewrites)
OPENAI_API_KEY=          # text-embedding-3-small (embeddings)
PINECONE_API_KEY=        # Vector storage
PINECONE_INDEX_NAME=     # Default: irish-workers-chatbot
```
