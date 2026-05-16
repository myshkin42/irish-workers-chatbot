"""
Post-deploy smoke test for the live backend.

Runs the curated smoke subset from evals/chat_eval_cases.json, checks /health,
confirms /logs is readable through the eval runner, and optionally exercises the
company-check proxy with a small Tesco lookup.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from run_chat_evals import (
    ApiClient,
    DEFAULT_CASES_PATH,
    DEFAULT_ENV_FILE,
    DEFAULT_REPORT_DIR,
    load_cases,
    load_token,
    run_cases,
    select_cases,
    summary,
    write_reports,
)


DEFAULT_LIVE_URL = "https://irish-workers-chatbot.fly.dev"


def run_company_check_smoke(client: ApiClient, company: str) -> tuple[bool, str, dict[str, Any] | None]:
    try:
        response = client.post("/api/company-check", {"company": company, "limit": 3})
    except Exception as exc:
        return False, f"company-check request failed: {exc}", None

    result = response.get("result") if isinstance(response.get("result"), dict) else response
    summary_data = result.get("summary") or {}
    records = result.get("records") or []
    if result.get("partial_results"):
        return False, "company-check returned partial_results=true", response
    if summary_data.get("total_records", len(records)) < 1:
        return False, "company-check returned no records", response
    return True, f"company-check ok: {summary_data.get('total_records', len(records))} record(s)", response


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live post-deploy smoke checks.")
    parser.add_argument("--base-url", default=os.environ.get("CHATBOT_BASE_URL", DEFAULT_LIVE_URL))
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--token-env", default="API_BEARER_TOKEN")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--skip-company-check", action="store_true")
    parser.add_argument("--company", default="Tesco")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    token = load_token(args.env_file, args.token_env)
    client = ApiClient(args.base_url, token=token, timeout=args.timeout)

    print(f"Smoke target: {args.base_url}")
    health = client.get("/health")
    print(f"Health: {json.dumps(health, ensure_ascii=False)}")
    health_ok = health.get("api") == "ok"

    cases = select_cases(load_cases(args.cases), suites=["smoke"])
    results = run_cases(client, cases, with_logs=True, delay=args.delay)
    totals = summary(results)

    company_ok = True
    company_message = "company-check skipped"
    if not args.skip_company_check:
        company_ok, company_message, _ = run_company_check_smoke(client, args.company)
    print(company_message)

    json_path, md_path = write_reports(results, args.report_dir, "live-smoke", args.base_url)
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    print(f"Summary: {totals['passed']}/{totals['total']} chat checks passed; company_check={company_ok}")

    if not health_ok:
        print("Health check failed.", file=sys.stderr)
    return 0 if health_ok and company_ok and totals["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
