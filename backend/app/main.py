"""
Irish Workers' Rights Chatbot - Simplified Backend
No session management, no Redis, no caching - just clean RAG.
"""
import os
import asyncio
import re
from typing import List, Dict, Any, Optional
from datetime import UTC, datetime

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
import httpx

from .system_prompt import SYSTEM_PROMPT
from .query_preprocessing import preprocess_query
from .lookup_store import LookupStore

# ----------------------------------------------------------------------------
# Query Logging
# ----------------------------------------------------------------------------
LOG_DIR = Path("/data/logs")

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_log_entry(entry: dict[str, Any]) -> None:
    """Append a structured event to the durable JSONL log."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "queries.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[LOG] Failed to write log: {e}")


def log_query(message: str, answer: str, sources: list, best_score: float,
              tier: str, has_good_sources: bool, context_used: str = None,
              lookup_id: str | None = None,
              redirect_category: str = "none",
              detected_company: str | None = None,
              rewritten_query: str | None = None,
              tier2_reason: str | None = None):
    """Log query and response to a JSON lines file. One line per interaction."""
    write_log_entry({
        "timestamp": utc_now_iso(),
        "event": "chat",
        "message": message,
        "answer": answer[:500],  # Truncate to keep logs manageable
        "sources": [s.get("title", "?") for s in sources[:3]],
        "best_score": round(best_score, 3),
        "tier": tier,
        "has_good_sources": has_good_sources,
        "context_query": context_used,
        "lookup_id": lookup_id,
        "redirect_category": redirect_category,
        "detected_company": detected_company,
        "rewritten_query": rewritten_query,
        "tier2_reason": tier2_reason,
    })


def log_company_check(
    company: str,
    *,
    lookup_id: str | None = None,
    result: dict[str, Any] | None = None,
    include_mentions: bool | None = None,
    limit: int | None = None,
    status: str = "success",
    error: str | None = None,
) -> None:
    """Log public-record checks without storing the full returned records."""
    summary = (result or {}).get("summary") or {}
    write_log_entry({
        "timestamp": utc_now_iso(),
        "event": "company_check",
        "company": company,
        "lookup_id": lookup_id,
        "status": status,
        "error": error,
        "include_mentions": include_mentions,
        "limit": limit,
        "total_records": summary.get("total_records"),
        "hsa_prosecutions": summary.get("hsa_prosecutions"),
        "decision_records": summary.get(
            "decision_records",
            (summary.get("wrc_decisions") or 0)
            + (summary.get("labour_court_records") or 0)
            + (summary.get("eat_records") or 0)
            + (summary.get("equality_records") or 0),
        ),
        "partial_results": (result or {}).get("partial_results"),
        "elapsed_ms": (result or {}).get("elapsed_ms"),
    })


def log_records_redirect_click(company: str, source_message: str | None = None) -> None:
    write_log_entry({
        "timestamp": utc_now_iso(),
        "event": "records_redirect_click",
        "company": company,
        "source_message": source_message[:500] if source_message else None,
    })

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

META_ONLY_PATTERNS = [
    "help",
    "help me",
    "can you help",
    "can you help me",
    "what can i ask",
    "what topics",
    "what can you do",
    "what do you do",
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
    "universal social charge", "tax return", "tax refund",
    "tax back", "tax relief", "gross to net", "take home pay",
    "net pay", "after tax",
]

PAYSLIP_DEDUCTION_TERMS = [
    "paye",
    "pay as you earn",
    "usc",
    "universal social charge",
    "prsi",
    "pay related social insurance",
]

TAX_CALCULATION_TERMS = [
    "after tax",
    "band",
    "bands",
    "bracket",
    "brackets",
    "calculate",
    "calculated",
    "calculating",
    "calculator",
    "credit",
    "credits",
    "gross to net",
    "how much",
    "net pay",
    "rate",
    "rates",
    "refund",
    "relief",
    "return",
    "take home",
]

DEFINITION_QUESTION_RE = re.compile(
    r"^(?:(?:hi|hello|hey|hiya)[,\s]+)?"
    r"(?:(?:can|could|would) you\s+)?"
    r"(?:what(?:'s| is| are)|what does|what do|explain|define|tell me about|meaning of)\b",
    re.IGNORECASE,
)

DEDUCTION_MEANING_TERMS = [
    "abbreviation",
    "abbreviations",
    "definition",
    "explain",
    "mean",
    "meaning",
    "means",
    "stand for",
    "stands for",
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

def contains_any_term(text: str, terms: List[str]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)


def is_bare_payslip_deduction_query(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return False

    remainder = cleaned
    for term in sorted(PAYSLIP_DEDUCTION_TERMS, key=len, reverse=True):
        remainder = re.sub(rf"\b{re.escape(term)}\b", " ", remainder)
    remainder = re.sub(
        r"\b(?:and|or|the|all|thing|things|stuff|please|pls)\b",
        " ",
        remainder,
    )
    return not re.sub(r"\s+", "", remainder)


def check_out_of_scope(message: str) -> str | None:
    """Check if the message is about a topic we should redirect rather than retrieve."""
    lower = message.strip().lower()
    lower = re.sub(r"\s+", " ", lower)
    has_payslip_deduction_term = contains_any_term(lower, PAYSLIP_DEDUCTION_TERMS)
    asks_for_calculation = contains_any_term(lower, TAX_CALCULATION_TERMS)
    if has_payslip_deduction_term and not asks_for_calculation:
        if DEFINITION_QUESTION_RE.search(lower):
            return None
        if contains_any_term(lower, DEDUCTION_MEANING_TERMS):
            return None
        if is_bare_payslip_deduction_query(lower):
            return None
        if "payslip" in lower and contains_any_term(lower, ["deduction", "deductions"]):
            return None

    if contains_any_term(lower, TAX_PATTERNS):
        return TAX_RESPONSE
    return None


RECORDS_REDIRECT_NONE = "none"
RECORDS_REDIRECT_PASSIVE = "passive_mention"
RECORDS_REDIRECT_ACTIVE = "active_redirect"

COMMON_NON_COMPANY_TERMS = {
    "hsa",
    "wrc",
    "labour court",
    "employment appeals tribunal",
    "equality tribunal",
    "public records",
    "check public records",
    "my employer",
    "employer",
    "boss",
    "company",
    "workplace",
    "someone",
    "anyone",
}

ACTIVE_RECORDS_PATTERNS = [
    r"\bhas\s+(?P<company>.+?)\s+been\s+(?:prosecuted|convicted|fined|taken\s+to\s+court)\b",
    r"\bany\s+(?:hsa\s+)?prosecutions?\s+(?:against|for|about)\s+(?P<company>.+)",
    r"\bis\s+(?P<company>.+?)\s+in\s+trouble\s+with\s+(?:the\s+)?hsa\b",
    r"\bhsa\s+(?:cases?|prosecutions?|records?)\s+(?:for|against|about|on)\s+(?P<company>.+)",
    r"\b(?:wrc|labour\s+court|eat|equality\s+tribunal)\s+(?:cases?|records?|decisions?|determinations?|complaints?)\s+(?:for|against|about|on)\s+(?P<company>.+)",
    r"\badjudications?\s+(?:for|against|about|on)\s+(?P<company>.+)",
    r"\bpublic\s+records?\s+(?:for|against|about|on)\s+(?P<company>.+)",
    r"\bany\s+records?\s+(?:of|for|against|about|on)\s+(?P<company>.+)",
    r"\bhas\s+anyone\s+sued\s+(?P<company>.+)",
    r"\bcomplaints?\s+(?:against|about|for)\s+(?P<company>.+)",
    r"\bis\s+(?P<company>.+?)\s+a\s+(?:bad|good|safe)\s+employer\b",
    r"\bis\s+(?P<company>.+?)\s+safe\s+to\s+work\s+for\b",
]

PASSIVE_COMPANY_PATTERNS = [
    r"\bi\s+work\s+(?:at|for|with)\s+(?P<company>.+?)(?:\s+(?:and|but|because|can|could|should|am|i'm|im)\b|[?.!,;:]|$)",
    r"\bworking\s+(?:at|for|with)\s+(?P<company>.+?)(?:\s+(?:and|but|because|can|could|should|am|i'm|im)\b|[?.!,;:]|$)",
    r"\bat\s+(?P<company>.+?)(?:\s+(?:and|but|because|can|could|should|am|i'm|im)\b|[?.!,;:]|$)",
    r"\bwith\s+(?P<company>.+?)(?:\s+(?:and|but|because|can|could|should|am|i'm|im)\b|[?.!,;:]|$)",
    r"\bmy\s+employer\s+is\s+(?P<company>.+?)(?:\s+(?:and|but|because|can|could|should|am|i'm|im)\b|[?.!,;:]|$)",
]


def clean_detected_company(company: str) -> str | None:
    company = re.sub(r"\s+", " ", company.strip(" \t\r\n\"'“”‘’.,?!;:()[]{}"))
    company = re.sub(
        r"\b(?:now|please|pls|for me|online|records?|cases?|complaints?|prosecutions?)\b$",
        "",
        company,
        flags=re.IGNORECASE,
    ).strip(" \t\r\n\"'“”‘’.,?!;:()[]{}")
    company = re.sub(r"^(?:the\s+)", "", company, flags=re.IGNORECASE)
    if not company or len(company) < 2:
        return None
    lower = company.lower()
    if lower in COMMON_NON_COMPANY_TERMS:
        return None
    if re.search(r"\b(?:vs|versus|or|and)\b", lower):
        return None
    if len(company.split()) > 6:
        return None
    return company


def looks_like_named_employer(company: str, *, allow_single_lowercase: bool = False) -> bool:
    if not company:
        return False
    if re.search(r"\b(?:ltd|limited|plc|dac|uc|clg|ireland|stores|group|company|co)\b", company, re.IGNORECASE):
        return True
    if re.search(r"[A-Z]", company):
        return True
    return allow_single_lowercase and len(company.split()) == 1 and len(company) >= 3


def classify_records_redirect(message: str) -> dict[str, str | None]:
    """Conservatively detect when chat should point to public-records lookup."""
    text = re.sub(r"\s+", " ", message.strip())
    if not text:
        return {"category": RECORDS_REDIRECT_NONE, "company": None}
    if re.search(r"\b(?:vs|versus)\b", text, re.IGNORECASE):
        return {"category": RECORDS_REDIRECT_NONE, "company": None}

    for pattern in ACTIVE_RECORDS_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        company = clean_detected_company(match.group("company"))
        if company and looks_like_named_employer(company):
            return {"category": RECORDS_REDIRECT_ACTIVE, "company": company}

    for pattern in PASSIVE_COMPANY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        company = clean_detected_company(match.group("company"))
        if company and looks_like_named_employer(company):
            return {"category": RECORDS_REDIRECT_PASSIVE, "company": company}

    return {"category": RECORDS_REDIRECT_NONE, "company": None}


def check_greeting_or_meta(message: str) -> str | None:
    """
    Check if the message is a greeting or meta-question about the chatbot.
    Returns a response string if matched, None otherwise.
    """
    lower = message.strip().lower().rstrip("?!.")
    lower = re.sub(r"\s+", " ", lower)
    
    # Exact or near-exact greeting. Do not treat a greeting prefix as a greeting
    # when the rest of the message contains the real employment-law question.
    if lower in GREETING_PATTERNS:
        return GREETING_RESPONSE
    if re.fullmatch(r"(hello|hi|hey|hiya|howdy|greetings|yo|sup)[\s,]*(there|codex|chatbot)?", lower):
        return GREETING_RESPONSE
    
    # Meta questions about the chatbot
    if lower in META_ONLY_PATTERNS:
        return GREETING_RESPONSE
    if any(p in lower for p in META_PATTERNS) and len(lower.split()) <= 5:
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
COMPANY_CHECK_API_URL = os.getenv("COMPANY_CHECK_API_URL", "").rstrip("/")
COMPANY_CHECK_API_TOKEN = os.getenv("COMPANY_CHECK_API_TOKEN", "")
COMPANY_CHECK_LOOKUP_TTL_MINUTES = int(os.getenv("COMPANY_CHECK_LOOKUP_TTL_MINUTES", "30"))

if not COMPANY_CHECK_API_URL or not COMPANY_CHECK_API_TOKEN:
    print("Warning: Company check is not configured - /api/company-check will return 503")

lookup_store = LookupStore(ttl_minutes=COMPANY_CHECK_LOOKUP_TTL_MINUTES)

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
    lookup_id: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    official_links: List[Dict[str, str]] = []
    has_authoritative_sources: bool = True  # False when no sources met relevance threshold
    disclaimer: str = "This is general information only, not legal advice. For specific situations, consult a solicitor, your union, or the WRC."
    knowledge_base_updated: str = KNOWLEDGE_BASE_UPDATED
    lookup_context_expired: bool = False
    redirect_category: str = RECORDS_REDIRECT_NONE
    detected_company: Optional[str] = None


class CompanyCheckRequest(BaseModel):
    company: str = Field(..., min_length=2, max_length=200)
    include_mentions: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class RecordsRedirectClickRequest(BaseModel):
    company: str = Field(..., min_length=2, max_length=200)
    source_message: Optional[str] = Field(default=None, max_length=4000)

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
    print(f"[TIER2] Rewritten: '{query[:40]}...' -> '{rewritten[:60]}...'")
    return rewritten


# ----------------------------------------------------------------------------
# Post-retrieval re-ranking
# ----------------------------------------------------------------------------
# When cosine scores are close, nudge better-fit documents to the top.
# This is much lighter than the Australian version — no profession routing,
# no state detection, no international law. Just topic-title alignment.

def rerank_matches(
    matches: List[Dict[str, Any]],
    query: str,
    original_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Re-rank retrieved matches by applying small score boosts
    when document metadata aligns with the query topic.

    Boosts are additive to the original cosine score so they only
    break ties — they can't promote a genuinely irrelevant document.

    Args:
        matches: Retrieved matches to re-rank.
        query: The query used for embedding (may include preprocessing
            expansions like 'maternity protection act benefit'). Used
            for topic-type lookups so expanded topic terms still trigger
            appropriate boosts.
        original_query: The user's actual words (with conversation context,
            but WITHOUT synthetic preprocessing expansions). Used for
            title-keyword overlap so expansion-added words like 'act',
            'benefit', 'protection' don't spuriously match legislation
            titles (e.g. a bare 'maternity leave' query that expanded to
            include 'act' and 'benefit' should not boost the Paternity
            Leave AND Benefit ACT chunks via title overlap). Falls back to
            `query` when not provided.
    """
    if not matches:
        return matches
    
    q = query.lower()
    orig_q = (original_query or query).lower()
    
    for match in matches:
        meta = match.get("metadata", {})
        title = (meta.get("display_name") or meta.get("title") or "").lower()
        doc_type = (meta.get("doc_type") or "").lower()
        text = (meta.get("text") or meta.get("content") or "").lower()[:1200]
        boost = 0.0
        
        # 1. Title keyword match — strongest signal.
        #    Use the ORIGINAL query (not the expanded one) so synthetic
        #    expansion terms can't match legislation titles. Without this,
        #    a bare "maternity leave" query gets expanded with 'act',
        #    'benefit', 'protection' — which then title-match the
        #    Maternity Protection Act AND the Paternity Leave and Benefit Act
        #    more strongly than the Citizens Information maternity guide.
        query_keywords = set(orig_q.split()) - {"i", "am", "being", "at", "work", "my", "the", "a", "an", "is", "was", "to", "in", "of", "for", "can", "do", "how", "what", "me", "im"}
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

        deduction_term_groups = [
            (["paye", "pay as you earn"], ["paye", "pay as you earn"]),
            (["prsi", "pay related social insurance"], ["prsi", "pay related social insurance"]),
            (["usc", "universal social charge"], ["usc", "universal social charge"]),
        ]
        for query_terms, source_terms in deduction_term_groups:
            if (
                (contains_any_term(orig_q, query_terms) or contains_any_term(q, query_terms))
                and (contains_any_term(title, source_terms) or contains_any_term(text, source_terms))
            ):
                boost += 0.10
        
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
    has_good_sources: bool,
    lookup_context: str | None = None,
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
    
    # Add lookup context only at generation time. It must never influence embedding or retrieval.
    lookup_prefix = f"{lookup_context}\n\n" if lookup_context else ""

    # Add user message with context
    if has_good_sources:
        user_message = f"""{lookup_prefix}User question: {query}

Relevant information from Irish employment law sources:
{context}

Answer the user's question naturally. Do not mention or reference these sources in your response."""
    else:
        # No good sources - be honest about limitations
        user_message = f"""{lookup_prefix}User question: {query}

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
def build_lookup_context(result: dict[str, Any]) -> str:
    summary = result.get("summary") or {}
    records = result.get("records") or []
    total_records = summary.get("total_records", len(records))
    hsa_count = summary.get("hsa_prosecutions", 0)
    decision_count = summary.get(
        "decision_records",
        summary.get("wrc_decisions", 0)
        + summary.get("labour_court_records", 0)
        + summary.get("eat_records", 0)
        + summary.get("equality_records", 0),
    )

    lines = [
        "[COMPANY CHECK CONTEXT]",
        f"Lookup target: {result.get('company', 'Unknown company')}",
        f"Total records: {total_records} (HSA prosecutions: {hsa_count}, public decision records: {decision_count})",
        f"Date range: {_lookup_date_range(records)}",
    ]

    if result.get("partial_results"):
        lines.append("Note: This lookup completed with partial results — some sources may be missing data.")

    top_records = _select_lookup_top_records(records)
    if top_records:
        lines.extend(["", "Top records (most recent + highest-impact, up to 5):"])
        for record in top_records:
            lines.append(f"- {_format_lookup_record(record)}")

        additional_count = max(len(records) - len(top_records), 0)
        if additional_count:
            lines.extend([
                "",
                (
                    f"There are {additional_count} additional records not shown above. "
                    "The user can ask for more detail on any specific year, source, or topic."
                ),
            ])

    lines.extend([
        "",
        "Important framing for your response:",
        "- Public decision records mean the employer name appears in a published case from the WRC, Labour Court, Employment Appeals Tribunal, or Equality Tribunal. They do not show that the employer lost, broke the law, or was at fault. The worker may have lost.",
        "- HSA prosecutions are confirmed convictions or guilty pleas, with fines or sentences as stated.",
        "- The user ran this check themselves. They have the records in front of them in another tab.",
        "[END COMPANY CHECK CONTEXT]",
    ])

    return "\n".join(lines)


def _lookup_date_value(record: dict[str, Any]) -> datetime | None:
    date = record.get("date")
    if not date:
        return None

    value = str(date).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"):
        try:
            return datetime.strptime(value.replace(",", ""), fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _lookup_year(record: dict[str, Any]) -> int | None:
    parsed = _lookup_date_value(record)
    if parsed:
        return parsed.year

    date = record.get("date")
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])

    return None


def _lookup_date_range(records: list[dict[str, Any]]) -> str:
    years = [year for record in records if (year := _lookup_year(record)) is not None]
    if not years:
        return "unknown"
    return f"{min(years)}–{max(years)}"


def _normalise(value: float | None, minimum: float, maximum: float) -> float:
    if value is None:
        return 0.0
    if maximum <= minimum:
        return 1.0
    return (value - minimum) / (maximum - minimum)


def _record_fine(record: dict[str, Any]) -> float | None:
    fine = record.get("fine_amount")
    if fine is None:
        return None
    try:
        return float(fine)
    except (TypeError, ValueError):
        return None


def _select_lookup_top_records(records: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    if len(records) <= limit:
        return sorted(records, key=_lookup_display_sort_key, reverse=True)

    date_values = [
        parsed.timestamp()
        for record in records
        if (parsed := _lookup_date_value(record)) is not None
    ]
    min_date = min(date_values) if date_values else 0.0
    max_date = max(date_values) if date_values else 0.0

    fines = [fine for record in records if (fine := _record_fine(record)) is not None]
    min_fine = min(fines) if fines else 0.0
    max_fine = max(fines) if fines else 0.0

    scored_records = []
    for record in records:
        parsed_date = _lookup_date_value(record)
        recency_rank = _normalise(parsed_date.timestamp() if parsed_date else None, min_date, max_date)
        if str(record.get("source") or "").lower() == "hsa":
            fine_rank = _normalise(_record_fine(record), min_fine, max_fine)
            score = (recency_rank * 0.5) + (fine_rank * 0.5)
        else:
            score = recency_rank
        scored_records.append((score, record))

    chosen = [record for _, record in sorted(scored_records, key=lambda item: item[0], reverse=True)[:limit]]
    return sorted(chosen, key=_lookup_display_sort_key, reverse=True)


def _lookup_display_sort_key(record: dict[str, Any]) -> tuple[float, float]:
    parsed_date = _lookup_date_value(record)
    date_score = parsed_date.timestamp() if parsed_date else 0.0
    return (date_score, _record_fine(record) or 0.0)


def _format_lookup_record(record: dict[str, Any]) -> str:
    date = record.get("date") or "(date unknown)"
    source = str(record.get("source") or "unknown").lower()
    source_label = {
        "hsa": "HSA",
        "wrc": "WRC",
        "labour_court": "Labour Court",
        "eat": "EAT",
        "equality": "Equality Tribunal",
    }.get(source, source.upper())
    url = record.get("url") or "no source URL"

    if source == "hsa":
        defendant = record.get("company_name") or "unknown defendant"
        outcome = record.get("outcome") or "not stated"
        fine = record.get("fine_amount")
        fine_text = _format_euro(fine) if fine is not None else "not stated"
        return f"{date} | {source_label} | {defendant} | Outcome: {outcome}, Fine: {fine_text} | {url}"

    case_number = record.get("case_number") or record.get("case_category") or "decision"
    return f"{date} | {source_label} | {case_number} | {url}"


def _format_euro(value: Any) -> str:
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        return "not stated"
    return f"€{amount:,}"


@app.get("/")
async def root():
    return {
        "message": "Irish Workers' Rights Chatbot API",
        "version": "1.0.0",
        "status": "running"
    }


@app.post("/api/company-check")
@limiter.limit("10/minute")
async def company_check(
    request: Request,
    payload: CompanyCheckRequest,
    _: bool = Depends(verify_token)
):
    if not COMPANY_CHECK_API_URL or not COMPANY_CHECK_API_TOKEN:
        log_company_check(
            payload.company,
            include_mentions=payload.include_mentions,
            limit=payload.limit,
            status="error",
            error="not_configured",
        )
        raise HTTPException(status_code=503, detail="Company check is not configured for this deployment.")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{COMPANY_CHECK_API_URL}/company-check",
                headers={"Authorization": f"Bearer {COMPANY_CHECK_API_TOKEN}"},
                json={
                    "company": payload.company,
                    "include_mentions": payload.include_mentions,
                    "limit": payload.limit,
                },
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        print(f"[COMPANY-CHECK] Upstream lookup failed for '{payload.company[:60]}': {exc}")
        log_company_check(
            payload.company,
            include_mentions=payload.include_mentions,
            limit=payload.limit,
            status="error",
            error=str(exc)[:300],
        )
        raise HTTPException(status_code=503, detail="Lookup service is temporarily unavailable")

    lookup_id = lookup_store.store(result)
    summary = result.get("summary", {})
    log_company_check(
        payload.company,
        lookup_id=lookup_id,
        result=result,
        include_mentions=payload.include_mentions,
        limit=payload.limit,
    )
    print(json.dumps({
        "event": "company_check",
        "company": payload.company,
        "lookup_id": lookup_id,
        "total_records": summary.get("total_records"),
        "partial_results": result.get("partial_results"),
        "elapsed_ms": result.get("elapsed_ms"),
    }))
    return {"lookup_id": lookup_id, "result": result}


@app.post("/api/records-redirect-click")
@limiter.limit("30/minute")
async def records_redirect_click(request: Request, payload: RecordsRedirectClickRequest):
    """Log when a user follows an active chat-to-records redirect."""
    log_records_redirect_click(payload.company, payload.source_message)
    return {"status": "ok"}


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

    lookup_context = None
    lookup_context_expired = False
    if payload.lookup_id:
        lookup_result = lookup_store.get(payload.lookup_id)
        if lookup_result:
            lookup_context = build_lookup_context(lookup_result)
        else:
            lookup_context_expired = True

    records_redirect = classify_records_redirect(payload.message)
    redirect_category = records_redirect["category"] or RECORDS_REDIRECT_NONE
    detected_company = records_redirect["company"]
    
    # Greeting/meta check — skip retrieval entirely for greetings
    greeting_response = check_greeting_or_meta(payload.message)
    if greeting_response:
        print(f"[GREETING] Matched: '{payload.message[:30]}'")
        log_query(
            payload.message,
            greeting_response,
            [],
            0.0,
            "greeting",
            True,
            lookup_id=payload.lookup_id,
            redirect_category=redirect_category,
            detected_company=detected_company,
        )
        return ChatResponse(
            answer=greeting_response,
            sources=[],
            official_links=[OFFICIAL_SOURCES["wrc"], OFFICIAL_SOURCES["citizens_info"]],
            has_authoritative_sources=True,  # Don't show the warning banner
            lookup_context_expired=lookup_context_expired,
            redirect_category=redirect_category,
            detected_company=detected_company,
        )

    if redirect_category == RECORDS_REDIRECT_ACTIVE and detected_company:
        answer = (
            "That's a question for the Check Public Records tab. It searches public records "
            "from the HSA, WRC, Labour Court, Employment Appeals Tribunal, and Equality Tribunal.\n\n"
            f"Use the button below to open that check with **{detected_company}** pre-filled."
        )
        print(f"[RECORDS-REDIRECT] Active: '{payload.message[:60]}' -> {detected_company}")
        log_query(
            payload.message,
            answer,
            [],
            0.0,
            "records-redirect",
            True,
            lookup_id=payload.lookup_id,
            redirect_category=redirect_category,
            detected_company=detected_company,
        )
        return ChatResponse(
            answer=answer,
            sources=[],
            official_links=[],
            has_authoritative_sources=True,
            lookup_context_expired=lookup_context_expired,
            redirect_category=redirect_category,
            detected_company=detected_company,
        )
    
    # Out-of-scope check — redirect common non-employment-rights questions
    oos_response = check_out_of_scope(payload.message)
    if oos_response:
        print(f"[OUT-OF-SCOPE] Matched: '{payload.message[:30]}'")
        log_query(
            payload.message,
            oos_response,
            [],
            0.0,
            "out-of-scope",
            True,
            lookup_id=payload.lookup_id,
            redirect_category=redirect_category,
            detected_company=detected_company,
        )
        return ChatResponse(
            answer=oos_response,
            sources=[],
            official_links=[OFFICIAL_SOURCES["wrc"], OFFICIAL_SOURCES["citizens_info"]],
            has_authoritative_sources=True,  # Don't show the warning banner
            lookup_context_expired=lookup_context_expired,
            redirect_category=redirect_category,
            detected_company=detected_company,
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
        rerank_query = enhanced_query
        tier2_invoked = False
        tier2_reason = None
        rewritten_query = None
        tier2_raw_score = None
        
        # 3. Tier 2: If raw score is below floor, rewrite before giving up.
        #    Lookup-attached chats keep the previous behavior: weak retrieval should
        #    not prevent Claude from using the company-check context.
        if best_raw_score < TIER2_FLOOR and not lookup_context:
            print(f"[TIER2] Raw score {best_raw_score:.3f} below floor - attempting LLM rewrite")
            tier2_invoked = True
            tier2_reason = "floor"
            rewritten_query = await tier2_rewrite_query(payload.message)
            matches, tier2_raw_score = await search_knowledge_base(rewritten_query)
            rerank_query = rewritten_query
            print(f"[TIER2] Floor rewrite raw: {tier2_raw_score:.3f}")
        
        # 4. Re-rank matches (nudge better-fit documents to top)
        #    enhanced_query is used for embedding-aware boosts (topic-type lookups).
        #    contextual_message is used as original_query for title-keyword overlap,
        #    so preprocessing-added legislative words (act/benefit/protection) don't
        #    spuriously match legislation titles via the title-overlap boost.
        if matches:
            matches = rerank_matches(
                matches,
                rerank_query,
                original_query=contextual_message,
            )
        
        # 5. Apply relevance threshold AFTER re-ranking
        #    Boosts can push borderline-but-correct matches over the line
        good_matches = [m for m in matches if m["score"] >= MINIMUM_RELEVANCE_SCORE]
        has_good_sources = len(good_matches) > 0
        
        # 6. Tier 2: If initial re-ranking still has no good sources, try LLM rewrite.
        if not has_good_sources and not tier2_invoked:
            print(f"[TIER2] No matches above threshold after rerank (best raw: {best_raw_score:.3f}) - attempting LLM rewrite")
            tier2_invoked = True
            tier2_reason = "threshold"
            rewritten_query = await tier2_rewrite_query(payload.message)
            matches, tier2_raw_score = await search_knowledge_base(rewritten_query)
            rerank_query = rewritten_query
            if matches:
                matches = rerank_matches(
                    matches,
                    rerank_query,
                    original_query=contextual_message,
                )
            good_matches = [m for m in matches if m["score"] >= MINIMUM_RELEVANCE_SCORE]
            has_good_sources = len(good_matches) > 0
            print(f"[TIER2] Threshold rewrite raw: {tier2_raw_score:.3f} -> good sources: {has_good_sources}")

        if not has_good_sources and not lookup_context:
            best_failed_score = matches[0]["score"] if matches else (tier2_raw_score if tier2_raw_score is not None else best_raw_score)
            print(f"[TIER3] No good sources after retrieval attempts - asking for clarification")
            clarification = "I'd like to help, but could you give me a bit more detail about your situation? For example, are you asking about pay, working hours, leave, dismissal, or something else? The more specific you can be, the better I can point you to the right information."
            log_query(
                payload.message,
                clarification,
                [],
                best_failed_score,
                "tier3",
                False,
                context_used=contextual_message if contextual_message != payload.message else None,
                lookup_id=payload.lookup_id,
                redirect_category=redirect_category,
                detected_company=detected_company,
                rewritten_query=rewritten_query,
                tier2_reason=tier2_reason,
            )
            return ChatResponse(
                answer=clarification,
                sources=[],
                official_links=[OFFICIAL_SOURCES["wrc"], OFFICIAL_SOURCES["citizens_info"]],
                has_authoritative_sources=False,
                lookup_context_expired=lookup_context_expired,
                redirect_category=redirect_category,
                detected_company=detected_company,
            )
        
        # Use good_matches from here on
        matches = good_matches if has_good_sources else matches[:3]  # fallback: show best we have
        
        # 7. Format context
        context = format_context(matches, has_good_sources)
        
        # 8. Generate response. If Tier 2 recovered sources, answer the rewritten
        #    legal topic so broad conversational wording does not collapse back
        #    into a clarification-only response.
        generation_query = (
            (
                f"{payload.message}\n\n"
                f"Answer this as a question about: {rewritten_query}. "
                "Give a brief general answer from the sources before asking any follow-up."
            )
            if tier2_invoked and has_good_sources and rewritten_query
            else payload.message
        )
        answer = await generate_response(
            query=generation_query,
            context=context,
            history=payload.history,
            has_good_sources=has_good_sources,
            lookup_context=lookup_context,
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
        if not tier2_invoked:
            tier = "tier1" if has_good_sources else "tier1-no-sources"
        elif tier2_reason == "floor":
            tier = "tier2-from-floor"
        else:
            tier = "tier2-from-threshold"
        log_query(
            payload.message, answer, sources,
            best_score=matches[0]["score"] if matches else 0.0,
            tier=tier, has_good_sources=has_good_sources,
            context_used=contextual_message if contextual_message != payload.message else None,
            lookup_id=payload.lookup_id,
            redirect_category=redirect_category,
            detected_company=detected_company,
            rewritten_query=rewritten_query,
            tier2_reason=tier2_reason,
        )
        
        return ChatResponse(
            answer=answer, 
            sources=sources,
            official_links=official_links,
            has_authoritative_sources=has_good_sources,
            lookup_context_expired=lookup_context_expired,
            redirect_category=redirect_category,
            detected_company=detected_company,
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
            "timestamp": utc_now_iso(),
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
