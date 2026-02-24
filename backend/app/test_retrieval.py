"""
Test retrieval quality through the full pipeline.

Tests: preprocessing → embedding → search → re-ranking → threshold check

Run from backend folder:
    python -m app.test_retrieval
    python -m app.test_retrieval -v          # verbose: show text snippets
    python -m app.test_retrieval -q "query"  # single interactive query
"""
import os
import sys
import argparse
from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI
from pinecone import Pinecone

# Load env from backend/.env
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Import our pipeline components
from .query_preprocessing import preprocess_query
from .main import rerank_matches, MINIMUM_RELEVANCE_SCORE, TIER2_FLOOR

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "irish-workers-chatbot"))

EMBED_MODEL = "text-embedding-3-small"


def embed_query(text: str) -> list[float]:
    response = openai_client.embeddings.create(input=[text], model=EMBED_MODEL)
    return response.data[0].embedding


def search_all_namespaces(query: str, top_k: int = 6) -> list[dict]:
    """Search across all namespaces, return combined results."""
    embedding = embed_query(query)
    stats = index.describe_index_stats()
    namespaces = list(stats.get("namespaces", {}).keys())

    all_results = []
    for ns in namespaces:
        try:
            results = index.query(
                vector=embedding,
                top_k=top_k,
                namespace=ns,
                include_metadata=True
            )
            for match in results.get("matches", []):
                all_results.append({
                    "score": match.score,
                    "namespace": ns,
                    "metadata": match.metadata or {}
                })
        except Exception as e:
            print(f"  Error querying {ns}: {e}")

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


# ============================================================================
# Test cases: (query, expected_title_substring, expected_doc_type_or_None)
#
# expected_title_substring: the TOP result's title should contain this string
# expected_doc_type: if set, the top result should be this doc_type
# ============================================================================
TEST_CASES = [
    # Pay issues (27% of WRC complaints)
    ("What is the minimum wage in Ireland?",
     "minimum wage", None),
    ("Can my employer deduct money from my wages?",
     "payment of wages", None),

    # Unfair dismissal (15%)
    ("I was fired without warning",
     "dismissal", None),
    ("What is constructive dismissal?",
     "constructive dismissal", None),

    # Working time (9%)
    ("How many hours can I work per week?",
     "working", None),
    ("What breaks am I entitled to during work?",
     "break", None),

    # Leave
    ("How many days annual leave am I entitled to?",
     "leave", None),
    ("How much sick leave can I take?",
     "sick leave", None),

    # Bullying (the one we fixed with re-ranking)
    ("I am being bullied at work",
     "bullying", "code_of_practice"),

    # Discrimination
    ("I'm being discriminated against because of my age",
     "equality", None),

    # Employment status
    ("Am I an employee or self-employed?",
     "employment status", None),

    # Procedures
    ("How do I make a complaint to the WRC?",
     "complaint", None),

    # Tier 2 candidate (marginal score, needs rewrite)
    ("Im working 60 hours a week",
     "working", None),

    # Redundancy
    ("Am I entitled to redundancy pay?",
     "redundancy", None),

    # Maternity
    ("How much maternity leave am I entitled to?",
     "maternity", None),
]


def run_single_query(query: str, verbose: bool = False):
    """Run a single query through the full pipeline and display results."""
    # Step 1: Preprocess
    enhanced, qp_meta = preprocess_query(query)
    expanded = qp_meta["was_expanded"]

    # Step 2: Search
    matches = search_all_namespaces(enhanced)
    best_raw = matches[0]["score"] if matches else 0.0

    # Step 3: Re-rank (use enhanced query so expansions feed into ranking)
    matches = rerank_matches(matches, enhanced)

    # Step 4: Threshold
    good = [m for m in matches if m["score"] >= MINIMUM_RELEVANCE_SCORE]
    tier = "T1 ✅" if good else ("T2 ⚡" if best_raw >= TIER2_FLOOR else "T3 ❓")

    print(f"\n{'='*70}")
    print(f"QUERY: {query}")
    if expanded:
        print(f"  EXPANDED: {enhanced[:80]}...")
    print(f"  TIER: {tier}  |  Best raw: {best_raw:.3f}  |  Threshold: {MINIMUM_RELEVANCE_SCORE}")
    print(f"{'='*70}")

    for i, m in enumerate(matches[:5], 1):
        meta = m.get("metadata", {})
        title = meta.get("display_name", "Unknown")
        dtype = meta.get("doc_type", "?")
        ns = m.get("namespace", "?")
        score = m["score"]
        orig = m.get("original_score", score)
        boost_str = f" (boosted from {orig:.3f})" if abs(score - orig) > 0.001 else ""

        above = "✅" if score >= MINIMUM_RELEVANCE_SCORE else "❌"
        print(f"  {above} {i}. [{score:.3f}{boost_str}] {title}")
        print(f"       {dtype} | {ns}")

        if verbose:
            text = (meta.get("text") or "")[:300]
            print(f"       {text}...")

    if not matches:
        print("  No results found.")


def run_test_suite(verbose: bool = False):
    """Run all test cases and report pass/fail."""
    print("="*70)
    print("Irish Workers Chatbot - Retrieval Test Suite")
    print(f"Threshold: {MINIMUM_RELEVANCE_SCORE} | Tier2 floor: {TIER2_FLOOR}")
    print("="*70)

    # Index stats
    stats = index.describe_index_stats()
    ns_info = stats.get("namespaces", {})
    total = sum(v.get("vector_count", 0) for v in ns_info.values())
    print(f"Index: {os.getenv('PINECONE_INDEX_NAME')} | {total} vectors | {len(ns_info)} namespaces")
    print(f"Namespaces: {', '.join(sorted(ns_info.keys()))}")

    passed = 0
    failed = 0
    marginal = 0
    results_summary = []

    for query, expected_title, expected_type in TEST_CASES:
        # Pipeline
        enhanced, qp_meta = preprocess_query(query)
        matches = search_all_namespaces(enhanced)
        best_raw = matches[0]["score"] if matches else 0.0
        matches = rerank_matches(matches, enhanced)
        good = [m for m in matches if m["score"] >= MINIMUM_RELEVANCE_SCORE]

        # Check results
        top = matches[0] if matches else None
        top_title = (top.get("metadata", {}).get("display_name", "") if top else "").lower()
        top_type = (top.get("metadata", {}).get("doc_type", "") if top else "").lower()
        top_score = top["score"] if top else 0.0

        # Pass conditions:
        # 1. Score above threshold (or in Tier 2 marginal band)
        # 2. Top result title contains expected substring
        title_ok = expected_title.lower() in top_title if top else False
        type_ok = (expected_type is None) or (expected_type.lower() == top_type)
        score_ok = bool(good) or (best_raw >= TIER2_FLOOR)

        if title_ok and type_ok and score_ok:
            status = "PASS ✅"
            passed += 1
        elif score_ok and not title_ok:
            status = "WEAK ⚠️"  # Found sources but wrong top doc
            marginal += 1
        else:
            status = "FAIL ❌"
            failed += 1

        result_line = f"  {status} [{top_score:.3f}] {query[:45]:<45} → {top_title[:40]}"
        results_summary.append(result_line)

        if verbose and status != "PASS ✅":
            print(f"\n  {status} {query}")
            print(f"    Expected title containing: '{expected_title}'")
            print(f"    Got: '{top_title}' ({top_type})")
            print(f"    Score: {top_score:.3f} (raw: {best_raw:.3f})")

    # Summary
    total_tests = len(TEST_CASES)
    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    for line in results_summary:
        print(line)
    print(f"\n{'='*70}")
    print(f"PASS: {passed}/{total_tests}  |  WEAK: {marginal}/{total_tests}  |  FAIL: {failed}/{total_tests}")
    print(f"{'='*70}")

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test retrieval pipeline")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show text snippets and failure details")
    parser.add_argument("-q", "--query", type=str, help="Run a single interactive query")
    args = parser.parse_args()

    if args.query:
        run_single_query(args.query, verbose=True)
    else:
        success = run_test_suite(verbose=args.verbose)
        sys.exit(0 if success else 1)
