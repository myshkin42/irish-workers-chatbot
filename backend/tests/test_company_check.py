import json
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


def test_company_check_missing_config(monkeypatch, tmp_path):
    from app import main

    monkeypatch.setattr(main, "COMPANY_CHECK_API_URL", "")
    monkeypatch.setattr(main, "COMPANY_CHECK_API_TOKEN", "")
    monkeypatch.setattr(main, "LOG_DIR", tmp_path)

    client = TestClient(main.app)
    response = client.post("/api/company-check", json={"company": "Tesco Ireland"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Company check is not configured for this deployment."

    entries = [
        json.loads(line)
        for line in (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert entries[-1]["event"] == "company_check"
    assert entries[-1]["company"] == "Tesco Ireland"
    assert entries[-1]["status"] == "error"
    assert entries[-1]["error"] == "not_configured"


def test_company_check_proxy_happy_path(monkeypatch, tmp_path):
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
    monkeypatch.setattr(main, "LOG_DIR", tmp_path)

    client = TestClient(main.app)
    response = client.post("/api/company-check", json={"company": "Tesco Ireland"})

    assert response.status_code == 200
    body = response.json()
    assert body["lookup_id"]
    assert body["result"]["company"] == "Tesco Ireland"
    assert main.lookup_store.get(body["lookup_id"]) == body["result"]

    entries = [
        json.loads(line)
        for line in (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert entries[-1]["event"] == "company_check"
    assert entries[-1]["company"] == "Tesco Ireland"
    assert entries[-1]["status"] == "success"
    assert entries[-1]["lookup_id"] == body["lookup_id"]
    assert entries[-1]["total_records"] == 1
    assert entries[-1]["decision_records"] == 1


def test_records_redirect_click_is_logged(monkeypatch, tmp_path):
    from app import main

    monkeypatch.setattr(main, "LOG_DIR", tmp_path)

    client = TestClient(main.app)
    response = client.post(
        "/api/records-redirect-click",
        json={"company": "Tesco", "source_message": "Has Tesco been prosecuted?"},
    )

    assert response.status_code == 200
    entries = [
        json.loads(line)
        for line in (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert entries[-1]["event"] == "records_redirect_click"
    assert entries[-1]["company"] == "Tesco"
    assert entries[-1]["source_message"] == "Has Tesco been prosecuted?"


def lookup_result(records, partial_results=False):
    hsa = sum(1 for record in records if record["source"] == "hsa")
    wrc = sum(1 for record in records if record["source"] == "wrc")
    return {
        "company": "Example Ltd",
        "partial_results": partial_results,
        "summary": {
            "total_records": len(records),
            "hsa_prosecutions": hsa,
            "wrc_decisions": wrc,
        },
        "records": records,
    }


def hsa_record(date, fine=1000, company="Example Ltd"):
    return {
        "source": "hsa",
        "date": date,
        "company_name": company,
        "outcome": "Guilty plea",
        "fine_amount": fine,
        "url": f"https://example.test/hsa/{date or 'unknown'}",
    }


def wrc_record(date, case_number="ADJ-0001"):
    return {
        "source": "wrc",
        "date": date,
        "case_number": case_number,
        "url": f"https://example.test/wrc/{case_number}",
    }


def record_lines(context):
    return [line for line in context.splitlines() if line.startswith("- ") and " | " in line]


def test_build_lookup_context_empty_records_has_no_top_records():
    from app.main import build_lookup_context

    context = build_lookup_context(lookup_result([]))

    assert "Total records: 0" in context
    assert "Top records" not in context
    assert "[END COMPANY CHECK CONTEXT]" in context


def test_build_lookup_context_three_records_shows_all_without_additional_line():
    from app.main import build_lookup_context

    context = build_lookup_context(lookup_result([
        hsa_record("2020-01-01", fine=1000),
        wrc_record("2021-01-01", case_number="ADJ-2021"),
        hsa_record("2019-01-01", fine=500),
    ]))

    assert "Top records (most recent + highest-impact, up to 5):" in context
    assert len(record_lines(context)) == 3
    assert "additional records not shown" not in context
    assert "2021-01-01 | WRC | ADJ-2021" in context


def test_build_lookup_context_eight_records_shows_top_five_and_additional_line():
    from app.main import build_lookup_context

    context = build_lookup_context(lookup_result([
        hsa_record("2018-01-01", fine=1000),
        hsa_record("2019-01-01", fine=2000),
        hsa_record("2020-01-01", fine=3000),
        hsa_record("2021-01-01", fine=4000),
        hsa_record("2022-01-01", fine=5000),
        hsa_record("2023-01-01", fine=6000),
        wrc_record("2024-01-01", case_number="ADJ-2024"),
        wrc_record("2025-01-01", case_number="ADJ-2025"),
    ]))

    assert len(record_lines(context)) == 5
    assert "There are 3 additional records not shown above." in context


def test_build_lookup_context_partial_results_note_is_included():
    from app.main import build_lookup_context

    context = build_lookup_context(lookup_result([hsa_record("2020-01-01")], partial_results=True))

    assert "Note: This lookup completed with partial results" in context


def test_build_lookup_context_unknown_date_sorts_last_and_displays_unknown():
    from app.main import build_lookup_context

    context = build_lookup_context(lookup_result([
        hsa_record(None, fine=10000, company="Unknown Date Ltd"),
        wrc_record("2022-01-01", case_number="ADJ-2022"),
        hsa_record("2021-01-01", fine=1000, company="Known Date Ltd"),
    ]))

    lines = record_lines(context)
    assert lines[-1].startswith("- (date unknown) | HSA | Unknown Date Ltd")


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
