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
    assert check_out_of_scope("how much tax do I pay?") == TAX_RESPONSE
    assert check_out_of_scope("what is my take home pay?") == TAX_RESPONSE


def test_prsi_query_is_expanded_for_retrieval():
    from app.query_preprocessing import preprocess_query

    enhanced, metadata = preprocess_query("what is PRSI?")

    assert "pay related social insurance" in enhanced.lower()
    assert "abbrev:prsi" in metadata["expansions_used"]


def test_prsi_rerank_boosts_exact_prsi_sources():
    from app.main import MINIMUM_RELEVANCE_SCORE, rerank_matches

    matches = [{
        "score": 0.53,
        "metadata": {
            "display_name": "Ci Payslips",
            "doc_type": "guide",
            "text": "PRSI EE means Pay Related Social Insurance paid by the employee.",
        },
    }]

    reranked = rerank_matches(
        matches,
        "what is pay related social insurance?",
        original_query="what is PRSI?",
    )

    assert reranked[0]["score"] >= MINIMUM_RELEVANCE_SCORE


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
