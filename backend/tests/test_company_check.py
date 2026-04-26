from datetime import timedelta

import pytest
from fastapi.testclient import TestClient


def test_lookup_store_happy_path_and_expiry():
    from app.lookup_store import LookupStore

    store = LookupStore(ttl_minutes=30)
    lookup_id = store.store({"company": "Tesco Ireland"})
    assert store.get(lookup_id) == {"company": "Tesco Ireland"}

    store.ttl = timedelta(minutes=-1)
    assert store.get(lookup_id) is None


def test_company_check_missing_config(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "COMPANY_CHECK_API_URL", "")
    monkeypatch.setattr(main, "COMPANY_CHECK_API_TOKEN", "")

    client = TestClient(main.app)
    response = client.post("/api/company-check", json={"company": "Tesco Ireland"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Company check is not configured for this deployment."


def test_company_check_proxy_happy_path(monkeypatch):
    from app import main

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "company": "Tesco Ireland",
                "elapsed_ms": 5,
                "partial_results": False,
                "summary": {"total_records": 1, "hsa_prosecutions": 0, "wrc_decisions": 1},
                "records": [],
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            assert url == "https://example.test/company-check"
            assert headers["Authorization"] == "Bearer secret-token"
            assert json["company"] == "Tesco Ireland"
            return FakeResponse()

    monkeypatch.setattr(main, "COMPANY_CHECK_API_URL", "https://example.test")
    monkeypatch.setattr(main, "COMPANY_CHECK_API_TOKEN", "secret-token")
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(main.app)
    response = client.post("/api/company-check", json={"company": "Tesco Ireland"})

    assert response.status_code == 200
    body = response.json()
    assert body["lookup_id"]
    assert body["result"]["company"] == "Tesco Ireland"
    assert main.lookup_store.get(body["lookup_id"]) == body["result"]


@pytest.mark.asyncio
async def test_generate_response_receives_lookup_context_without_retrieval_changes(monkeypatch):
    from app import main

    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)

            class Content:
                text = "ok"

            class Response:
                content = [Content()]

            return Response()

    class FakeAnthropic:
        messages = FakeMessages()

    monkeypatch.setattr(main, "anthropic_client", FakeAnthropic())

    answer = await main.generate_response(
        query="What does this mean?",
        context="RAG context",
        history=[],
        has_good_sources=True,
        lookup_context="[COMPANY CHECK CONTEXT]\nExample\n[END COMPANY CHECK CONTEXT]",
    )

    assert answer == "ok"
    user_message = captured["messages"][-1]["content"]
    assert user_message.startswith("[COMPANY CHECK CONTEXT]")
    assert "RAG context" in user_message
