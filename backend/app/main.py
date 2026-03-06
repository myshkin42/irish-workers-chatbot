"""
Irish Workers' Rights Chatbot - Simplified Backend
No session management, no Redis, no caching - just clean RAG.
"""
import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Body, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path

from pinecone import Pinecone
from anthropic import Anthropic

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import json

from .system_prompt import SYSTEM_PROMPT
from .query_preprocessing import preprocess_query

# ----------------------------------------------------------------------------
# Query Logging
# ----------------------------------------------------------------------------
LOG_DIR = Path("/data/logs")

def log_query(message: str, answer: str, sources: list, best_score: float,
              tier: str, has_good_sources: bool, context_used: str = None):
    """Log query and response to a JSON lines file. One line per interaction."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "queries.jsonl"
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": message,
            "answer": answer[:500],  # Truncate to keep logs manageable
            "sources": [s.get("title", "?") for s in sources[:3]],
            "best_score": round(best_score, 3),
            "tier": tier,
            "has_good_sources": has_good_sources,
            "context_query": context_used,
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[LOG] Failed to write log: {e}")

# ----------------------------------------------------------------------------
# Security & Metadata
# ----------------------------------------------------------------------------

# Knowledge base metadata - update when you re-ingest documents
KNOWLEDGE_BASE_VERSION = "1.0.0"
KNOWLEDGE_BASE_UPDATED = "2026-03-06"  # Update this after each ingestion

# Official sources to reference
OFFICIAL_SOURCES = {
    "wrc": {
        "name": "Workplace Relations Commission",
        "url": "https://www.workplacerelations.ie",
        "description": "File complaints, find guides and codes of practice"
    },
    "citizens_info": {
        "name": "Citizens Information",
        "url": "https://www.citizensinformation.ie/en/employment/",
        "description": "Plain-language guides on employment rights"
    },
    "hsa": {
        "name": "Health and Safety Authority",
        "url": "https://www.hsa.ie",
        "description": "Workplace health and safety"
    },
    "irishstatutebook": {
        "name": "Irish Statute Book",
        "url": "https://www.irishstatutebook.ie",
        "description": "Full text of legislation"
    }
}

# Layer 1 security: obvious injection patterns
# Not trying to catch everything - just the lazy/obvious attempts
INJECTION_PATTERNS = [
    "ignore previous",
    "ignore your instructions",
    "ignore all instructions",
    "disregard your",
    "disregard all",
    "forget your instructions",
    "system prompt",
    "reveal your prompt",
    "show your instructions",
    "you are now",
    "act as if",
    "pretend you are",
    "jailbreak",
    "dan mode",
    "developer mode",
    "admin override",
]

def check_input_safety(message: str) -> tuple[bool, str | None]:
    """
    Layer 1 security: check for obvious injection attempts.
    Returns (is_safe, reason_if_blocked)
    
    This is not meant to catch sophisticated attacks - Claude handles those.
    This just filters out lazy copy-paste attempts.
    """
    lower = message.lower()
    
    for pattern in INJECTION_PATTERNS:
        if pattern in lower:
            return False, f"blocked_pattern:{pattern[:20]}"
    
    return True, None


# Greeting and meta-question detection
# These don't need retrieval — handle them directly to save embedding costs
GREETING_PATTERNS = [
    "hello", "hi", "hey", "howdy", "good morning", "good afternoon",
    "good evening", "hiya", "greetings", "sup", "yo",
]

META_PATTERNS = [
    "who are you", "what are you", "what can you do", "how do you work",
    "what is this", "what do you do", "help me", "can you help",
    "what can i ask", "what topics",
]

GREETING_RESPONSE = (
    "Hello! I'm the Irish Workers' Rights Chatbot. I can help you with questions about "
    "your employment rights in Ireland — things like pay, working hours, leave, unfair dismissal, "
    "discrimination, redundancy, and how to make a complaint to the WRC.\n\n"
    "What would you like to know about?"
)

# Out-of-scope topic detection
# These are common questions that aren't employment rights — redirect helpfully
TAX_PATTERNS = [
    "how much tax", "tax rate", "tax rates", "income tax", "pay tax",
    "tax band", "tax credit", "tax bracket", "paye", "usc",
    "universal social charge", "prsi", "tax return", "tax refund",
    "tax back", "tax relief", "gross to net", "take home pay",
    "net pay", "after tax",
]

TAX_RESPONSE = (
    "Tax is quite individual and depends on your income, marital status, credits, and reliefs — "
    "so I'm not the best tool for calculating your specific tax.\n\n"
    "For that, I'd recommend:\n\n"
    "• **Revenue.ie** — Ireland's tax authority. They have a PAYE calculator and detailed guides for your situation.\n"
    "• **Citizens Information** (citizensinformation.ie) — plain-language guides on income tax, USC, and PRSI.\n"
    "• **Your payroll department** — they can explain the deductions on your payslip.\n\n"
    "If you have a question about your employment rights — like deductions from your wages, "
    "not getting a payslip, or being underpaid — I can definitely help with that."
)

def check_out_of_scope(message: str) -> str | None:
    """Check if the message is about a topic we should redirect rather than retrieve."""
    lower = message.strip().lower()
    if any(p in lower for p in TAX_PATTERNS):
        return TAX_RESPONSE
    return None


def check_greeting_or_meta(message: str) -> str | None:
    """
    Check if the message is a greeting or meta-question about the chatbot.
    Returns a response string if matched, None otherwise.
    """
    lower = message.strip().lower().rstrip("?!.")
    
    # Exact or near-exact greeting
    if lower in GREETING_PATTERNS or any(lower.startswith(g) for g in GREETING_PATTERNS):
        return GREETING_RESPONSE
    
    # Meta questions about the chatbot
    if any(p in lower for p in META_PATTERNS):
        return GREETING_RESPONSE
    
    return None

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot")
API_BEARER_TOKEN = os.getenv("API_BEARER_TOKEN")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Model configuration
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # Claude 4.5 Haiku
EMBED_MODEL = "text-embedding-3-small"  # We'll use Anthropic's voyager or keep OpenAI for embeddings

# Retrieval configuration
# Score threshold for relevance (cosine similarity with text-embedding-3-small)
# 0.7+ = good match, 0.6-0.7 = marginal, below 0.6 = probably irrelevant
MINIMUM_RELEVANCE_SCORE = 0.60  # Conservative - rather admit ignorance than cite garbage

assert ANTHROPIC_API_KEY, "ANTHROPIC_API_KEY not set"
assert PINECONE_API_KEY, "PINECONE_API_KEY not set"

# Initialize clients
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

# For embeddings, we still use OpenAI (Anthropic doesn't have embedding API yet)
# We'll need to add this dependency if not using Pinecone's inference
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None
    print("Warning: OPENAI_API_KEY not set - embeddings won't work until configured")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# ----------------------------------------------------------------------------
# FastAPI App
# ----------------------------------------------------------------------------
app = FastAPI(
    title="Irish Workers' Rights Chatbot API",
    version="1.0.0",
    description="A chatbot to help Irish workers understand their employment rights"
)

# CORS - adjust for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3400", "http://127.0.0.1:3400"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Optional token verification - skip in development"""
    if ENVIRONMENT == "development":
        return True
    if not API_BEARER_TOKEN:
        return True  # No token configured = no auth required
    if not credentials or credentials.credentials != API_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------
class Message(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: List[Message] = Field(default_factory=list, max_length=20)

class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    official_links: List[Dict[str, str]] = []
    has_authoritative_sources: bool = True  # False when no sources met relevance threshold
    disclaimer: str = "This is general information only, not legal advice. For specific situations, consult a solicitor, your union, or the WRC."
    knowledge_base_updated: str = KNOWLEDGE_BASE_UPDATED

# ----------------------------------------------------------------------------
# Core Functions
# ----------------------------------------------------------------------------
async def get_embedding(text: str) -> List[float]:
    """Get embedding for text using OpenAI"""
    if not openai_client:
        raise HTTPException(status_code=500, detail="Embedding service not configured")
    
    response = await asyncio.to_thread(
        openai_client.embeddings.create,
        input=text,
        model=EMBED_MODEL
    )
    return response.data[0].embedding


# Retrieval tier thresholds
TIER2_FLOOR = 0.45  # Below this, query is too vague - ask for clarification


def build_contextual_query(message: str, history: List[Message]) -> str:
    """
    Build a context-aware search query when the current message looks
    like a follow-up to a previous exchange.
    
    Examples:
      - "I am a 20 year old apprentice" after "what is the minimum wage?"
        → "I am a 20 year old apprentice minimum wage"
      - "what about part-time?" after discussing annual leave
        → "what about part-time? annual leave"
    
    Only activates when the message is likely a follow-up (short, personal
    statement, contains pronouns/context words, etc.) AND there's recent
    history to draw from.
    """
    if not history or len(history) < 2:
        return message
    
    lower = message.strip().lower()
    
    # Signals that this is a follow-up, not a standalone question.
    # We require 2+ signals to trigger, so standalone questions like
    # "Can I be required to wear high heels?" (long + has '?') don't
    # accidentally pick up context from the previous exchange.
    follow_up_signals = [
        len(lower.split()) <= 4,                     # Very short message (bare topic or fragment)
        lower.startswith(("i am", "i'm", "im ", "my ", "what about", "and ", "but ",
                          "also", "how about", "what if", "does that", "is that",
                          "same for")),              # Ambiguous starters only
        "?" not in message and len(lower.split()) <= 8,  # Statement, not question, and short
    ]
    
    if sum(follow_up_signals) < 2:
        return message
    
    # Find the last user message from history to get the topic
    last_user_msg = None
    for msg in reversed(history):
        if msg.role == "user":
            last_user_msg = msg.content
            break
    
    if not last_user_msg:
        return message
    
    # Extract key topic words from the previous question
    # (strip stopwords to get the core topic)
    stopwords = {"i", "am", "a", "an", "the", "is", "was", "are", "were", "my",
                 "me", "do", "does", "did", "can", "could", "will", "would",
                 "what", "how", "who", "when", "where", "why", "in", "on",
                 "at", "to", "for", "of", "it", "if", "about", "get", "have",
                 "has", "had", "that", "this", "there", "be", "been", "being",
                 "im", "ive", "youre"}
    
    prev_words = last_user_msg.lower().split()
    topic_words = [w.strip("?.,!") for w in prev_words if w.strip("?.,!") not in stopwords]
    
    if not topic_words:
        return message
    
    # Append topic context to the current message
    topic_context = " ".join(topic_words[:8])  # Cap at 8 words to avoid dilution
    contextual_query = f"{message} {topic_context}"
    print(f"[CONTEXT] Follow-up detected: '{message[:40]}' + topic '{topic_context}'")
    
    return contextual_query


async def search_knowledge_base(query: str, top_k: int = 6) -> tuple[List[Dict[str, Any]], float]:
    """
    Search Pinecone for relevant documents.
    
    Returns all matches above TIER2_FLOOR (0.45). Threshold filtering
    happens in the chat endpoint AFTER re-ranking, so boosts can
    push borderline-but-correct matches over the relevance threshold.
    
    Returns:
        tuple: (matches, best_score)
        - matches: List of document matches above floor
        - best_score: Highest raw score from any namespace
    """
    embedding = await get_embedding(query)
    
    # Search all namespaces
    stats = index.describe_index_stats()
    namespaces = list(stats.get("namespaces", {}).keys())
    
    all_matches = []
    for ns in namespaces:
        try:
            results = index.query(
                vector=embedding,
                top_k=top_k,
                namespace=ns,
                include_metadata=True
            )
            for match in results.matches:
                all_matches.append({
                    "score": match.score,
                    "namespace": ns,
                    "metadata": match.metadata or {}
                })
        except Exception as e:
            print(f"Error querying namespace {ns}: {e}")
    
    # Sort by score
    all_matches.sort(key=lambda x: x["score"], reverse=True)
    
    best_score = all_matches[0]["score"] if all_matches else 0.0
    
    # Return all matches above the Tier 2 floor for now.
    # Re-ranking and threshold filtering happen in the chat endpoint
    # AFTER boosts are applied. This prevents good-but-borderline
    # matches from being discarded before re-ranking can help them.
    floor_matches = [m for m in all_matches if m["score"] >= TIER2_FLOOR]
    
    return floor_matches[:top_k], best_score


async def tier2_rewrite_query(query: str) -> str:
    """
    Tier 2: Use Haiku to rewrite a conversational query in Irish employment law terminology.
    Only called when Tier 1 retrieval scores are marginal (0.45-0.60).
    """
    response = await asyncio.to_thread(
        anthropic_client.messages.create,
        model=CLAUDE_MODEL,
        max_tokens=150,
        system="You rewrite worker questions using Irish employment law terminology for a search engine. Return ONLY the rewritten query, nothing else. Use terms from Irish legislation, WRC codes of practice, and Citizens Information guides.",
        messages=[{"role": "user", "content": f"Rewrite this worker's question using Irish employment law terms: {query}"}]
    )
    rewritten = response.content[0].text.strip()
    print(f"[TIER2] Rewritten: '{query[:40]}...' → '{rewritten[:60]}...'")
    return rewritten


# ----------------------------------------------------------------------------
# Post-retrieval re-ranking
# ----------------------------------------------------------------------------
# When cosine scores are close, nudge better-fit documents to the top.
# This is much lighter than the Australian version — no profession routing,
# no state detection, no international law. Just topic-title alignment.

def rerank_matches(matches: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Re-rank retrieved matches by applying small score boosts
    when document metadata aligns with the query topic.
    
    Boosts are additive to the original cosine score so they only
    break ties — they can't promote a genuinely irrelevant document.
    """
    if not matches:
        return matches
    
    q = query.lower()
    
    for match in matches:
        meta = match.get("metadata", {})
        title = (meta.get("display_name") or meta.get("title") or "").lower()
        doc_type = (meta.get("doc_type") or "").lower()
        text = (meta.get("text") or meta.get("content") or "").lower()[:500]
        boost = 0.0
        
        # 1. Title keyword match — strongest signal
        #    If the user asks about "bullying" and the doc title contains "bullying",
        #    that's almost certainly the right document.
        query_keywords = set(q.split()) - {"i", "am", "being", "at", "work", "my", "the", "a", "an", "is", "was", "to", "in", "of", "for", "can", "do", "how", "what", "me", "im"}
        title_words = set(title.split())
        keyword_overlap = query_keywords & title_words
        if keyword_overlap:
            boost += 0.03 * len(keyword_overlap)
        
        # 2. Doc type preference by topic
        #    Codes of practice are authoritative for specific workplace issues.
        #    Guides are best for practical "what are my rights" questions.
        #    Acts are good for "what does the law say" questions.
        topic_type_boosts = {
            # (query_keyword, preferred_doc_type): boost
            # Codes of practice - specific workplace issues
            ("bullying", "code_of_practice"): 0.03,
            ("harassment", "code_of_practice"): 0.03,
            ("disconnect", "code_of_practice"): 0.03,
            ("flexible", "code_of_practice"): 0.03,
            ("remote", "code_of_practice"): 0.03,
            ("grievance", "code_of_practice"): 0.03,
            ("disciplinary", "code_of_practice"): 0.03,
            # Legislation - "what does the law say" questions
            ("dismissed", "legislation"): 0.02,
            ("fired", "legislation"): 0.02,
            ("discrimination", "legislation"): 0.02,
            # Guides - practical rate/entitlement questions
            # Guides explain the actual figures; legislation just defines the framework
            ("minimum wage", "guide"): 0.04,
            ("wage", "guide"): 0.03,
            ("pay", "guide"): 0.02,
            ("redundancy", "guide"): 0.02,
            ("leave", "guide"): 0.02,
            ("sick leave", "guide"): 0.03,
            ("maternity", "guide"): 0.02,
            ("paternity", "guide"): 0.02,
            ("holiday", "guide"): 0.02,
            ("annual leave", "guide"): 0.02,
            ("hours", "guide"): 0.02,
            ("breaks", "guide"): 0.02,
            ("notice", "guide"): 0.02,
            ("contract", "guide"): 0.02,
        }
        for (kw, dtype), b in topic_type_boosts.items():
            if kw in q and dtype == doc_type:
                boost += b
        
        # 3. Penalise generic catch-all documents when specific ones exist
        #    e.g. "Safety Representatives Resource Book" is 600+ pages covering everything
        generic_titles = ["resource book", "guide to employment", "employment law explained"]
        if any(g in title for g in generic_titles) and len(matches) > 1:
            boost -= 0.02
        
        match["original_score"] = match["score"]
        match["boost"] = boost
        match["score"] = match["score"] + boost
    
    # Re-sort
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    # Log re-ranking results
    for i, m in enumerate(matches[:5]):
        meta = m.get("metadata", {})
        title = (meta.get("display_name") or meta.get("title") or "Unknown")[:40]
        dtype = meta.get("doc_type", "?")
        ns = m.get("namespace", "?")
        orig = m.get("original_score", 0)
        boost = m.get("boost", 0)
        final = m.get("score", 0)
        print(f"[RERANK] #{i+1} {title} [{dtype}] ns={ns} | {orig:.3f} + {boost:+.3f} = {final:.3f}")
    
    return matches


def format_context(matches: List[Dict[str, Any]], has_good_sources: bool) -> str:
    """
    Format retrieved documents into context string.
    
    Args:
        matches: List of document matches
        has_good_sources: Whether any matches met the relevance threshold
    """
    if not matches:
        return """NO SOURCES FOUND. You have NO source documents for this query. Follow the 'When NO Sources Are Provided' instructions exactly. Keep your response to 2-3 sentences. Do NOT provide any specific legal information."""
    
    context_parts = []
    for i, match in enumerate(matches, 1):
        meta = match.get("metadata", {})
        title = meta.get("display_name", meta.get("title", "Unknown"))
        doc_type = meta.get("doc_type", "unknown")
        score = match.get("score", 0)
        
        # Truncate text - TODO: improve to sentence boundaries
        text = meta.get("text", meta.get("content", ""))[:800]
        section = meta.get("section_id", "")
        
        source_label = f"{title}"
        if section:
            source_label += f" ({section})"
        source_label += f" [{doc_type}]"
        
        context_parts.append(f"[Source {i}: {source_label} | relevance: {score:.2f}]\n{text}")
    
    return "\n\n".join(context_parts)


def format_history(history: List[Message]) -> List[Dict[str, str]]:
    """Format conversation history for Claude API"""
    return [{"role": msg.role, "content": msg.content} for msg in history]


def select_official_links(query: str) -> List[Dict[str, str]]:
    """
    Select relevant official links based on query content.
    Always returns WRC + Citizens Info, plus topic-specific ones.
    """
    lower = query.lower()
    links = []
    
    # Always include these two
    links.append(OFFICIAL_SOURCES["wrc"])
    links.append(OFFICIAL_SOURCES["citizens_info"])
    
    # Add HSA for safety/health queries
    safety_keywords = ["safety", "health", "accident", "injury", "dangerous", "hazard", "ppe", "risk"]
    if any(kw in lower for kw in safety_keywords):
        links.append(OFFICIAL_SOURCES["hsa"])
    
    # Add Irish Statute Book for legislation queries
    law_keywords = ["act", "legislation", "law", "statute", "section", "regulation"]
    if any(kw in lower for kw in law_keywords):
        links.append(OFFICIAL_SOURCES["irishstatutebook"])
    
    return links


async def generate_response(
    query: str,
    context: str,
    history: List[Message],
    has_good_sources: bool
) -> str:
    """
    Generate response using Claude.
    
    Args:
        query: User's question
        context: Formatted context from knowledge base
        history: Conversation history
        has_good_sources: Whether retrieval found relevant sources
    """
    # Build messages
    messages = format_history(history)
    
    # Add user message with context
    if has_good_sources:
        user_message = f"""User question: {query}

Relevant information from Irish employment law sources:
{context}

Answer the user's question naturally. Do not mention or reference these sources in your response."""
    else:
        # No good sources - be honest about limitations
        user_message = f"""User question: {query}

{context}"""
    
    messages.append({"role": "user", "content": user_message})
    
    # Call Claude
    response = await asyncio.to_thread(
        anthropic_client.messages.create,
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    
    return response.content[0].text


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "message": "Irish Workers' Rights Chatbot API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/metadata")
async def metadata():
    """
    Returns metadata for the frontend UI.
    Use this on initial page load to display disclaimer, last updated, etc.
    """
    return {
        "disclaimer": "This chatbot provides general information about Irish employment law. It is not legal advice. For specific situations, consult a solicitor, your union, or contact the Workplace Relations Commission directly.",
        "knowledge_base_updated": KNOWLEDGE_BASE_UPDATED,
        "knowledge_base_version": KNOWLEDGE_BASE_VERSION,
        "official_sources": list(OFFICIAL_SOURCES.values()),
        "important_contacts": {
            "wrc_info_line": "0818 80 80 90",
            "wrc_online_complaints": "https://www.workplacerelations.ie/en/Complaints_Disputes/Refer_a_Dispute_Make_a_Complaint/",
            "hsa_contact": "1800 289 389",
            "citizens_info_phone": "0818 07 4000"
        },
        "time_limits_warning": "Most WRC complaints must be made within 6 months of the incident. Don't delay seeking advice."
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    checks = {
        "api": "ok",
        "pinecone": "unknown",
        "anthropic": "ok"  # Assume ok if we got this far
    }
    
    try:
        stats = index.describe_index_stats()
        checks["pinecone"] = "ok"
        checks["pinecone_namespaces"] = list(stats.get("namespaces", {}).keys())
    except Exception as e:
        checks["pinecone"] = f"error: {str(e)[:50]}"
    
    return checks


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(
    request: Request,
    payload: ChatRequest,
    _: bool = Depends(verify_token)
):
    """
    Main chat endpoint.
    
    Accepts a message and optional conversation history.
    Returns an answer based on Irish employment law sources.
    """
    # Layer 1 security: check for obvious injection attempts
    is_safe, block_reason = check_input_safety(payload.message)
    if not is_safe:
        # Log for monitoring (don't reveal why to user)
        print(f"[SECURITY] Blocked input: {block_reason}")
        return ChatResponse(
            answer="I'm here to help with Irish employment law. What would you like to know about your workplace rights?",
            sources=[],
            official_links=[OFFICIAL_SOURCES["wrc"], OFFICIAL_SOURCES["citizens_info"]]
        )
    
    # Greeting/meta check — skip retrieval entirely for greetings
    greeting_response = check_greeting_or_meta(payload.message)
    if greeting_response:
        print(f"[GREETING] Matched: '{payload.message[:30]}'")
        log_query(payload.message, greeting_response, [], 0.0, "greeting", True)
        return ChatResponse(
            answer=greeting_response,
            sources=[],
            official_links=[OFFICIAL_SOURCES["wrc"], OFFICIAL_SOURCES["citizens_info"]],
            has_authoritative_sources=True  # Don't show the warning banner
        )
    
    # Out-of-scope check — redirect common non-employment-rights questions
    oos_response = check_out_of_scope(payload.message)
    if oos_response:
        print(f"[OUT-OF-SCOPE] Matched: '{payload.message[:30]}'")
        log_query(payload.message, oos_response, [], 0.0, "out-of-scope", True)
        return ChatResponse(
            answer=oos_response,
            sources=[],
            official_links=[OFFICIAL_SOURCES["wrc"], OFFICIAL_SOURCES["citizens_info"]],
            has_authoritative_sources=True  # Don't show the warning banner
        )
    
    try:
        # 0. Build context-aware query for follow-ups
        contextual_message = build_contextual_query(payload.message, payload.history)
        
        # 1. Preprocess query (Tier 1: static expansions)
        enhanced_query, qp_meta = preprocess_query(contextual_message)
        if qp_meta["was_expanded"]:
            print(f"[QP] {qp_meta['expansions_used']}")
        
        # 2. Search knowledge base (using enhanced query for retrieval)
        #    Returns all matches above Tier 2 floor (0.45) — threshold
        #    filtering happens AFTER re-ranking so boosts can help.
        matches, best_raw_score = await search_knowledge_base(enhanced_query)
        
        # 3. Tier 3: If raw score below floor, ask for clarification
        #    (no point re-ranking or rewriting if nothing is even close)
        if best_raw_score < TIER2_FLOOR:
            print(f"[TIER3] Score {best_raw_score:.3f} below floor - asking for clarification")
            clarification = "I'd like to help, but could you give me a bit more detail about your situation? For example, are you asking about pay, working hours, leave, dismissal, or something else? The more specific you can be, the better I can point you to the right information."
            log_query(payload.message, clarification, [], best_raw_score, "tier3", False, context_used=contextual_message if contextual_message != payload.message else None)
            return ChatResponse(
                answer=clarification,
                sources=[],
                official_links=[OFFICIAL_SOURCES["wrc"], OFFICIAL_SOURCES["citizens_info"]],
                has_authoritative_sources=False
            )
        
        # 4. Re-rank matches (nudge better-fit documents to top)
        #    Use enhanced_query so preprocessing expansions feed into ranking
        if matches:
            matches = rerank_matches(matches, enhanced_query)
        
        # 5. Apply relevance threshold AFTER re-ranking
        #    Boosts can push borderline-but-correct matches over the line
        good_matches = [m for m in matches if m["score"] >= MINIMUM_RELEVANCE_SCORE]
        has_good_sources = len(good_matches) > 0
        best_score = good_matches[0]["score"] if good_matches else best_raw_score
        
        # 6. Tier 2: If still no good sources after re-ranking, try LLM rewrite
        if not has_good_sources:
            print(f"[TIER2] No matches above threshold after rerank (best raw: {best_raw_score:.3f}) - attempting LLM rewrite")
            rewritten_query = await tier2_rewrite_query(payload.message)
            matches, new_raw_score = await search_knowledge_base(rewritten_query)
            if matches:
                matches = rerank_matches(matches, rewritten_query)
            good_matches = [m for m in matches if m["score"] >= MINIMUM_RELEVANCE_SCORE]
            has_good_sources = len(good_matches) > 0
            print(f"[TIER2] Rewrite best raw: {new_raw_score:.3f} → good sources: {has_good_sources}")
        
        # Use good_matches from here on
        matches = good_matches if has_good_sources else matches[:3]  # fallback: show best we have
        
        # 7. Format context
        context = format_context(matches, has_good_sources)
        
        # 8. Generate response (using ORIGINAL query so Claude sees natural language)
        answer = await generate_response(
            query=payload.message,
            context=context,
            history=payload.history,
            has_good_sources=has_good_sources
        )
        
        # 9. Format sources for response (only include if we have good sources)
        sources = [
            {
                "title": m.get("metadata", {}).get("display_name", "Unknown"),
                "doc_type": m.get("metadata", {}).get("doc_type", "unknown"),
                "section": m.get("metadata", {}).get("section_id"),
                "namespace": m.get("namespace"),
                "relevance": round(m.get("score", 0), 2)
            }
            for m in matches[:3]
        ] if has_good_sources else []
        
        # 10. Select relevant official links based on query content
        official_links = select_official_links(payload.message)
        
        # 11. Log the query and response
        tier = "tier1" if has_good_sources else "tier2"
        log_query(
            payload.message, answer, sources,
            best_score=matches[0]["score"] if matches else 0.0,
            tier=tier, has_good_sources=has_good_sources,
            context_used=contextual_message if contextual_message != payload.message else None
        )
        
        return ChatResponse(
            answer=answer, 
            sources=sources,
            official_links=official_links,
            has_authoritative_sources=has_good_sources
        )
    
    except Exception as e:
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)[:100]}")


class FeedbackRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    answer: str = Field(..., min_length=1, max_length=8000)
    feedback: str = Field(..., pattern="^(up|down)$")


@app.post("/feedback")
@limiter.limit("30/minute")
async def submit_feedback(request: Request, payload: FeedbackRequest):
    """Log user feedback (thumbs up/down) on a response."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "feedback.jsonl"
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": payload.message,
            "answer": payload.answer[:500],
            "feedback": payload.feedback,
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"status": "ok"}
    except Exception as e:
        print(f"[FEEDBACK] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to log feedback")


@app.get("/feedback/summary")
async def feedback_summary(_: bool = Depends(verify_token)):
    """View feedback log."""
    log_file = LOG_DIR / "feedback.jsonl"
    if not log_file.exists():
        return {"entries": [], "total": 0, "thumbs_up": 0, "thumbs_down": 0}
    
    with open(log_file, "r") as f:
        lines = f.readlines()
    
    entries = []
    up = 0
    down = 0
    for line in lines:
        try:
            entry = json.loads(line.strip())
            entries.append(entry)
            if entry.get("feedback") == "up":
                up += 1
            else:
                down += 1
        except json.JSONDecodeError:
            continue
    
    # Return newest first
    entries.reverse()
    return {"entries": entries[:100], "total": len(entries), "thumbs_up": up, "thumbs_down": down}


@app.get("/logs")
async def get_logs(n: int = 50, _: bool = Depends(verify_token)):
    """View recent query logs. Returns last n entries."""
    log_file = LOG_DIR / "queries.jsonl"
    if not log_file.exists():
        return {"entries": [], "total": 0}
    
    with open(log_file, "r") as f:
        lines = f.readlines()
    
    # Return last n entries, newest first
    entries = []
    for line in reversed(lines[-n:]):
        try:
            entries.append(json.loads(line.strip()))
        except json.JSONDecodeError:
            continue
    
    return {"entries": entries, "total": len(lines)}


@app.get("/namespaces")
async def list_namespaces(_: bool = Depends(verify_token)):
    """List all namespaces in the index"""
    try:
        stats = index.describe_index_stats()
        namespaces = stats.get("namespaces", {})
        return {
            "namespaces": [
                {"name": ns, "vector_count": info.get("vector_count", 0)}
                for ns, info in namespaces.items()
            ],
            "total_vectors": sum(info.get("vector_count", 0) for info in namespaces.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Handle rate limit errors
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return HTTPException(
        status_code=429,
        detail="Too many requests. Please slow down."
    )


# ----------------------------------------------------------------------------
# Run with: uvicorn app.main:app --reload
# ----------------------------------------------------------------------------
