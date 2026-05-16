"""
Basic tests for the Irish Workers' Rights Chatbot backend
"""
import pytest
from fastapi.testclient import TestClient


def test_imports():
    """Test that all modules can be imported"""
    from app.main import app
    from app.system_prompt import SYSTEM_PROMPT
    from app import ingest
    
    assert app is not None
    assert SYSTEM_PROMPT is not None
    assert len(SYSTEM_PROMPT) > 100


def test_root_endpoint():
    """Test the root endpoint"""
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Irish" in data["message"]


def test_health_endpoint():
    """Test the health endpoint"""
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert "api" in data
    assert data["api"] == "ok"


def test_chat_request_validation():
    """Test that chat endpoint validates requests"""
    from app.main import app
    
    client = TestClient(app)
    
    # Empty message should fail
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422
    
    # Missing message should fail
    response = client.post("/chat", json={})
    assert response.status_code == 422


def test_system_prompt_contains_key_elements():
    """Test that system prompt includes important elements"""
    from app.system_prompt import SYSTEM_PROMPT
    
    # Check for key Irish bodies
    assert "WRC" in SYSTEM_PROMPT
    assert "Workplace Relations Commission" in SYSTEM_PROMPT
    assert "Labour Court" in SYSTEM_PROMPT
    assert "HSA" in SYSTEM_PROMPT
    
    # Check for key time-limit guidance
    assert "time limit" in SYSTEM_PROMPT.lower()
    
    # Check for key topic framing
    assert "workplace rights" in SYSTEM_PROMPT.lower()
    assert "unfair dismissals act" in SYSTEM_PROMPT.lower()


def test_greeting_detection_does_not_swallow_prefaced_questions():
    from app.main import GREETING_RESPONSE, check_greeting_or_meta

    assert check_greeting_or_meta("Hi") == GREETING_RESPONSE
    assert check_greeting_or_meta("Hello there!") == GREETING_RESPONSE
    assert check_greeting_or_meta("Hi I need some help with maternity leave") is None
    assert check_greeting_or_meta("Hello, can you tell me about redundancy?") is None
    assert check_greeting_or_meta("Can you help me with maternity leave?") is None


def test_basic_prsi_questions_are_not_tax_redirected():
    from app.main import TAX_RESPONSE, check_out_of_scope

    assert check_out_of_scope("what is PRSI?") is None
    assert check_out_of_scope("what does PRSI mean") is None
    assert check_out_of_scope("What is PRSI and USC?") is None
    assert check_out_of_scope("What is USC?") is None
    assert check_out_of_scope("what does PAYE mean on my payslip?") is None
    assert check_out_of_scope("Can you explain what all the PAYE and PRSI things mean?") is None
    assert check_out_of_scope("PAye?") is None
    assert check_out_of_scope("USC and PRSI please") is None
    assert check_out_of_scope("how much tax do I pay?") == TAX_RESPONSE
    assert check_out_of_scope("how much USC do I pay?") == TAX_RESPONSE
    assert check_out_of_scope("what is my USC rate?") == TAX_RESPONSE
    assert check_out_of_scope("how is PAYE calculated?") == TAX_RESPONSE
    assert check_out_of_scope("what is my take home pay?") == TAX_RESPONSE


def test_payslip_deduction_queries_are_expanded_for_retrieval():
    from app.query_preprocessing import preprocess_query

    enhanced, metadata = preprocess_query("what is PAYE, PRSI and USC?")
    enhanced_lower = enhanced.lower()

    assert "pay as you earn income tax" in enhanced_lower
    assert "pay related social insurance" in enhanced_lower
    assert "universal social charge" in enhanced_lower
    assert "abbrev:paye" in metadata["expansions_used"]
    assert "abbrev:prsi" in metadata["expansions_used"]
    assert "abbrev:usc" in metadata["expansions_used"]


def test_payslip_deduction_rerank_boosts_exact_sources():
    from app.main import MINIMUM_RELEVANCE_SCORE, rerank_matches

    matches = [{
        "score": 0.53,
        "metadata": {
            "display_name": "Ci Payslips",
            "doc_type": "guide",
            "text": "PRSI means Pay Related Social Insurance. USC means Universal Social Charge.",
        },
    }]

    reranked = rerank_matches(
        matches,
        "what is pay related social insurance and universal social charge?",
        original_query="what is PRSI and USC?",
    )

    assert reranked[0]["score"] >= MINIMUM_RELEVANCE_SCORE


def test_records_redirect_classifier_is_conservative():
    from app.main import (
        RECORDS_REDIRECT_ACTIVE,
        RECORDS_REDIRECT_NONE,
        RECORDS_REDIRECT_PASSIVE,
        classify_records_redirect,
    )

    assert classify_records_redirect("What's the minimum wage?") == {
        "category": RECORDS_REDIRECT_NONE,
        "company": None,
    }
    assert classify_records_redirect("Tell me about WRC complaint procedures") == {
        "category": RECORDS_REDIRECT_NONE,
        "company": None,
    }
    assert classify_records_redirect("I have complaints about pay") == {
        "category": RECORDS_REDIRECT_NONE,
        "company": None,
    }

    assert classify_records_redirect("I work at Tesco and I'm worried about my hours") == {
        "category": RECORDS_REDIRECT_PASSIVE,
        "company": "Tesco",
    }
    assert classify_records_redirect("My boss at Dunnes Stores says I have to work every Sunday") == {
        "category": RECORDS_REDIRECT_PASSIVE,
        "company": "Dunnes Stores",
    }
    assert classify_records_redirect("Has Tesco been prosecuted?") == {
        "category": RECORDS_REDIRECT_ACTIVE,
        "company": "Tesco",
    }
    assert classify_records_redirect("Is Boots Ireland a good employer?") == {
        "category": RECORDS_REDIRECT_ACTIVE,
        "company": "Boots Ireland",
    }
    assert classify_records_redirect("Has Tesco or Aldi been prosecuted?") == {
        "category": RECORDS_REDIRECT_NONE,
        "company": None,
    }


def test_active_records_redirect_short_circuits_chat(monkeypatch, tmp_path):
    from app import main

    monkeypatch.setattr(main, "LOG_DIR", tmp_path)

    client = TestClient(main.app)
    response = client.post("/chat", json={"message": "Has Tesco been prosecuted?", "history": []})

    assert response.status_code == 200
    body = response.json()
    assert body["redirect_category"] == main.RECORDS_REDIRECT_ACTIVE
    assert body["detected_company"] == "Tesco"
    assert "Check Public Records tab" in body["answer"]
    assert body["sources"] == []


def retrieval_match(title="Ci Working Hours", score=0.7):
    return {
        "score": score,
        "namespace": "guides",
        "metadata": {
            "display_name": title,
            "doc_type": "guide",
            "section_id": None,
            "text": "Working hours and rest breaks in Irish employment law.",
        },
    }


def test_floor_rewrite_runs_before_clarification(monkeypatch):
    from app import main

    calls = {"rewrite": 0, "searches": [], "logs": []}

    async def fake_search(query):
        calls["searches"].append(query)
        if query == "working hours legal query":
            return [retrieval_match()], 0.62
        return [], 0.20

    async def fake_rewrite(query):
        calls["rewrite"] += 1
        return "working hours legal query"

    def fake_rerank(matches, query, original_query=None):
        return matches

    async def fake_generate_response(**kwargs):
        assert kwargs["has_good_sources"] is True
        assert "Working Hours" in kwargs["context"]
        return "Here is a sourced answer about working hours."

    def fake_log_query(*args, **kwargs):
        calls["logs"].append({"tier": kwargs.get("tier", args[4] if len(args) > 4 else None), **kwargs})

    monkeypatch.setattr(main, "search_knowledge_base", fake_search)
    monkeypatch.setattr(main, "tier2_rewrite_query", fake_rewrite)
    monkeypatch.setattr(main, "rerank_matches", fake_rerank)
    monkeypatch.setattr(main, "generate_response", fake_generate_response)
    monkeypatch.setattr(main, "log_query", fake_log_query)

    client = TestClient(main.app)
    response = client.post("/chat", json={"message": "I am wondering about my hours", "history": []})

    assert response.status_code == 200
    body = response.json()
    assert body["has_authoritative_sources"] is True
    assert "working hours" in body["answer"].lower()
    assert calls["rewrite"] == 1
    assert calls["logs"][-1]["tier"] == "tier2-from-floor"
    assert calls["logs"][-1]["rewritten_query"] == "working hours legal query"
    assert calls["logs"][-1]["tier2_reason"] == "floor"


def test_nonsense_falls_back_to_clarification_after_rewrite(monkeypatch):
    from app import main

    calls = {"rewrite": 0, "logs": []}

    async def fake_search(query):
        return [], 0.10

    async def fake_rewrite(query):
        calls["rewrite"] += 1
        return "nonsense rewritten query"

    async def fake_generate_response(**kwargs):
        raise AssertionError("generate_response should not run for final Tier 3 fallback")

    def fake_log_query(*args, **kwargs):
        calls["logs"].append({"tier": kwargs.get("tier", args[4] if len(args) > 4 else None), **kwargs})

    monkeypatch.setattr(main, "search_knowledge_base", fake_search)
    monkeypatch.setattr(main, "tier2_rewrite_query", fake_rewrite)
    monkeypatch.setattr(main, "generate_response", fake_generate_response)
    monkeypatch.setattr(main, "log_query", fake_log_query)

    client = TestClient(main.app)
    response = client.post("/chat", json={"message": "asdfghjkl", "history": []})

    assert response.status_code == 200
    body = response.json()
    assert body["has_authoritative_sources"] is False
    assert "could you give me a bit more detail" in body["answer"]
    assert calls["rewrite"] == 1
    assert calls["logs"][-1]["tier"] == "tier3"
    assert calls["logs"][-1]["rewritten_query"] == "nonsense rewritten query"
    assert calls["logs"][-1]["tier2_reason"] == "floor"


def test_tier2_rewrite_refusal_is_not_embedded(monkeypatch):
    from app import main

    calls = {"searches": [], "logs": []}
    refusal = (
        "I'm unable to rewrite this query using Irish employment law terminology, "
        "as it does not contain a recognizable worker question. Please provide a clear question."
    )

    async def fake_search(query):
        calls["searches"].append(query)
        return [], 0.10

    async def fake_rewrite(query):
        return refusal

    async def fake_generate_response(**kwargs):
        raise AssertionError("generate_response should not run for final Tier 3 fallback")

    def fake_log_query(*args, **kwargs):
        calls["logs"].append({"tier": kwargs.get("tier", args[4] if len(args) > 4 else None), **kwargs})

    monkeypatch.setattr(main, "search_knowledge_base", fake_search)
    monkeypatch.setattr(main, "tier2_rewrite_query", fake_rewrite)
    monkeypatch.setattr(main, "generate_response", fake_generate_response)
    monkeypatch.setattr(main, "log_query", fake_log_query)

    client = TestClient(main.app)
    response = client.post("/chat", json={"message": "asdfghjkl", "history": []})

    assert response.status_code == 200
    body = response.json()
    assert body["has_authoritative_sources"] is False
    assert "could you give me a bit more detail" in body["answer"]
    assert calls["searches"] == ["asdfghjkl"]
    assert calls["logs"][-1]["tier"] == "tier3"
    assert calls["logs"][-1]["rewritten_query"] == refusal
    assert calls["logs"][-1]["tier2_reason"] == "floor"


def test_tier1_success_does_not_invoke_rewrite(monkeypatch):
    from app import main

    calls = {"logs": []}

    async def fake_search(query):
        return [retrieval_match("Ci Minimum Wage", 0.72)], 0.72

    async def fake_rewrite(query):
        raise AssertionError("Tier 2 should not run when Tier 1 succeeds")

    def fake_rerank(matches, query, original_query=None):
        return matches

    async def fake_generate_response(**kwargs):
        return "The minimum wage answer is sourced."

    def fake_log_query(*args, **kwargs):
        calls["logs"].append({"tier": kwargs.get("tier", args[4] if len(args) > 4 else None), **kwargs})

    monkeypatch.setattr(main, "search_knowledge_base", fake_search)
    monkeypatch.setattr(main, "tier2_rewrite_query", fake_rewrite)
    monkeypatch.setattr(main, "rerank_matches", fake_rerank)
    monkeypatch.setattr(main, "generate_response", fake_generate_response)
    monkeypatch.setattr(main, "log_query", fake_log_query)

    client = TestClient(main.app)
    response = client.post("/chat", json={"message": "What is the minimum wage?", "history": []})

    assert response.status_code == 200
    body = response.json()
    assert body["has_authoritative_sources"] is True
    assert body["sources"][0]["title"] == "Ci Minimum Wage"
    assert calls["logs"][-1]["tier"] == "tier1"
    assert calls["logs"][-1]["rewritten_query"] is None
    assert calls["logs"][-1]["tier2_reason"] is None


# Integration tests (require API keys - skip in CI)
@pytest.mark.skip(reason="Requires API keys")
def test_chat_integration():
    """Test full chat flow with real APIs"""
    from app.main import app
    
    client = TestClient(app)
    response = client.post("/chat", json={
        "message": "What is the minimum wage?",
        "history": []
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["answer"]) > 50
