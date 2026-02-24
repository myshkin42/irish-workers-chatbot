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
    
    # Check for key time limits
    assert "6 months" in SYSTEM_PROMPT
    
    # Check for key topics
    assert "minimum wage" in SYSTEM_PROMPT.lower()
    assert "unfair dismissal" in SYSTEM_PROMPT.lower()
    assert "redundancy" in SYSTEM_PROMPT.lower()


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
