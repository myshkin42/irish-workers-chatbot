"""
Run lightweight chat regression evals against a local or deployed backend.

The checks are deliberately modest: they catch obvious routing/source regressions
and produce a Markdown report for human review. Use the report as the source of
truth for answer quality.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DEFAULT_CASES_PATH = BACKEND_DIR / "evals" / "chat_eval_cases.json"
DEFAULT_REPORT_DIR = BACKEND_DIR / "evals" / "reports"
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"


@dataclass
class EvalResult:
    case: dict[str, Any]
    response: dict[str, Any] | None
    log_entry: dict[str, Any] | None
    failures: list[str]
    warnings: list[str]
    elapsed_seconds: float

    @property
    def passed(self) -> bool:
        return not self.failures


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: int = 120):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc

        return json.loads(raw) if raw else {}

    def get(self, path: str) -> dict[str, Any]:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, payload)


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_token(env_file: Path, token_env: str) -> str | None:
    return os.environ.get(token_env) or read_env_file(env_file).get(token_env)


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"{path} does not contain a top-level cases list")
    return cases


def select_cases(
    cases: list[dict[str, Any]],
    suites: list[str] | None = None,
    ids: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    selected = cases
    if suites:
        suite_set = set(suites)
        selected = [
            case for case in selected
            if suite_set.intersection(set(case.get("suite", [])))
        ]
    if ids:
        id_set = set(ids)
        selected = [case for case in selected if case.get("id") in id_set]
    if limit:
        selected = selected[:limit]
    return selected


def contains_casefold(haystack: str, needle: str) -> bool:
    return needle.casefold() in haystack.casefold()


def source_titles(response: dict[str, Any]) -> list[str]:
    return [
        str(source.get("title", ""))
        for source in response.get("sources", [])
        if isinstance(source, dict)
    ]


def check_response(
    case: dict[str, Any],
    response: dict[str, Any],
    log_entry: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    checks = case.get("checks", {})
    answer = str(response.get("answer", ""))
    sources = response.get("sources") or []
    titles = source_titles(response)

    if "has_authoritative_sources" in checks:
        expected = checks["has_authoritative_sources"]
        actual = response.get("has_authoritative_sources")
        if actual is not expected:
            failures.append(f"has_authoritative_sources expected {expected!r}, got {actual!r}")

    if "min_sources" in checks and len(sources) < int(checks["min_sources"]):
        failures.append(f"expected at least {checks['min_sources']} sources, got {len(sources)}")

    if "max_sources" in checks and len(sources) > int(checks["max_sources"]):
        failures.append(f"expected at most {checks['max_sources']} sources, got {len(sources)}")

    if "redirect_category" in checks:
        expected = checks["redirect_category"]
        actual = response.get("redirect_category")
        if actual != expected:
            failures.append(f"redirect_category expected {expected!r}, got {actual!r}")

    if "detected_company" in checks:
        expected = checks["detected_company"]
        actual = response.get("detected_company")
        if actual != expected:
            failures.append(f"detected_company expected {expected!r}, got {actual!r}")

    for phrase in checks.get("answer_contains", []):
        if not contains_casefold(answer, str(phrase)):
            failures.append(f"answer missing {phrase!r}")

    contains_any = checks.get("answer_contains_any", [])
    if contains_any and not any(contains_casefold(answer, str(phrase)) for phrase in contains_any):
        failures.append(f"answer missing any of {contains_any!r}")

    for phrase in checks.get("answer_not_contains", []):
        if contains_casefold(answer, str(phrase)):
            failures.append(f"answer unexpectedly contains {phrase!r}")

    for phrase in checks.get("source_title_contains", []):
        if not any(contains_casefold(title, str(phrase)) for title in titles):
            failures.append(f"no source title contains {phrase!r}; titles={titles!r}")

    log_checks = {"log_tier", "log_tier_in", "log_tier_not_in", "log_tier2_reason", "log_has_good_sources"}
    if log_checks.intersection(checks.keys()):
        if not log_entry:
            failures.append("no matching log entry found for log checks")
        else:
            tier = log_entry.get("tier")
            if "log_tier" in checks and tier != checks["log_tier"]:
                failures.append(f"log tier expected {checks['log_tier']!r}, got {tier!r}")
            if "log_tier_in" in checks and tier not in checks["log_tier_in"]:
                failures.append(f"log tier {tier!r} not in {checks['log_tier_in']!r}")
            if "log_tier_not_in" in checks and tier in checks["log_tier_not_in"]:
                failures.append(f"log tier {tier!r} unexpectedly in {checks['log_tier_not_in']!r}")
            if "log_tier2_reason" in checks and log_entry.get("tier2_reason") != checks["log_tier2_reason"]:
                failures.append(
                    f"log tier2_reason expected {checks['log_tier2_reason']!r}, "
                    f"got {log_entry.get('tier2_reason')!r}"
                )
            if "log_has_good_sources" in checks and log_entry.get("has_good_sources") is not checks["log_has_good_sources"]:
                failures.append(
                    f"log has_good_sources expected {checks['log_has_good_sources']!r}, "
                    f"got {log_entry.get('has_good_sources')!r}"
                )

    if not checks:
        warnings.append("case has no automated checks")

    return failures, warnings


def find_log_entry(client: ApiClient, message: str, n: int = 80) -> dict[str, Any] | None:
    data = client.get(f"/logs?n={n}")
    entries = data.get("entries", [])
    for entry in entries:
        if entry.get("message") == message:
            return entry
    return None


def run_case(client: ApiClient, case: dict[str, Any], with_logs: bool = True) -> EvalResult:
    payload = {
        "message": case["message"],
        "history": case.get("history", []),
    }
    if case.get("lookup_id"):
        payload["lookup_id"] = case["lookup_id"]

    started = time.perf_counter()
    warnings: list[str] = []
    response: dict[str, Any] | None = None
    log_entry: dict[str, Any] | None = None
    failures: list[str] = []

    try:
        response = client.post("/chat", payload)
    except Exception as exc:
        return EvalResult(case, None, None, [f"chat request failed: {exc}"], warnings, time.perf_counter() - started)

    if with_logs:
        try:
            # The app writes logs synchronously, but a tiny pause helps remote volumes settle.
            time.sleep(0.1)
            log_entry = find_log_entry(client, case["message"])
        except Exception as exc:
            warnings.append(f"log lookup failed: {exc}")

    check_failures, check_warnings = check_response(case, response, log_entry)
    failures.extend(check_failures)
    warnings.extend(check_warnings)

    return EvalResult(case, response, log_entry, failures, warnings, time.perf_counter() - started)


def should_delay(base_url: str, case_count: int, explicit_delay: float | None) -> float:
    if explicit_delay is not None:
        return explicit_delay
    is_local = "localhost" in base_url or "127.0.0.1" in base_url
    if is_local:
        return 0.1
    # /chat is rate-limited to 30/minute. Full live evals need breathing room.
    return 2.1 if case_count > 20 else 0.5


def run_cases(client: ApiClient, cases: list[dict[str, Any]], with_logs: bool, delay: float) -> list[EvalResult]:
    results: list[EvalResult] = []
    for index, case in enumerate(cases, 1):
        print(f"[{index:02d}/{len(cases):02d}] {case['id']} ... ", end="", flush=True)
        result = run_case(client, case, with_logs=with_logs)
        results.append(result)
        print("PASS" if result.passed else "FAIL")
        if result.failures:
            for failure in result.failures:
                print(f"    - {failure}")
        if delay and index < len(cases):
            time.sleep(delay)
    return results


def write_reports(
    results: list[EvalResult],
    report_dir: Path,
    label: str,
    base_url: str,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in label)
    json_path = report_dir / f"{stamp}-{safe_label}.json"
    md_path = report_dir / f"{stamp}-{safe_label}.md"

    serialisable = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "summary": summary(results),
        "results": [
            {
                "id": result.case.get("id"),
                "suite": result.case.get("suite", []),
                "message": result.case.get("message"),
                "passed": result.passed,
                "failures": result.failures,
                "warnings": result.warnings,
                "elapsed_seconds": round(result.elapsed_seconds, 3),
                "review_status": review_status(result),
                "route_label": route_label(result),
                "source_summary": source_summary(result),
                "answer_preview": answer_preview(result),
                "response": result.response,
                "log_entry": result.log_entry,
                "review_note": result.case.get("review_note"),
            }
            for result in results
        ],
    }
    json_path.write_text(json.dumps(serialisable, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(results, base_url), encoding="utf-8")
    return json_path, md_path


def summary(results: list[EvalResult]) -> dict[str, int]:
    passed = sum(1 for result in results if result.passed)
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "warnings": sum(len(result.warnings) for result in results),
    }


def compact_text(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def markdown_cell(value: Any, limit: int = 160) -> str:
    text = compact_text(value, limit=limit)
    return text.replace("|", "\\|")


def review_status(result: EvalResult) -> str:
    if result.failures:
        return "FAIL"
    if result.warnings:
        return "WARN"
    return "OK"


def route_label(result: EvalResult) -> str:
    response = result.response or {}
    log_entry = result.log_entry or {}
    tier = log_entry.get("tier") or "no-log"
    redirect = response.get("redirect_category")
    company = response.get("detected_company")
    parts = [str(tier)]
    if redirect and redirect != "none":
        parts.append(str(redirect))
    if company:
        parts.append(str(company))
    return " / ".join(parts)


def source_summary(result: EvalResult, limit: int = 2) -> str:
    titles = source_titles(result.response or {})
    unique_titles = list(dict.fromkeys(titles))
    if not unique_titles:
        return "None"
    summary_text = "; ".join(unique_titles[:limit])
    if len(unique_titles) > limit:
        summary_text += f"; +{len(unique_titles) - limit}"
    return summary_text


def answer_preview(result: EvalResult, limit: int = 220) -> str:
    response = result.response or {}
    return compact_text(response.get("answer", ""), limit=limit)


def count_by_tier(results: list[EvalResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        tier = str((result.log_entry or {}).get("tier") or "no-log")
        counts[tier] = counts.get(tier, 0) + 1
    return dict(sorted(counts.items()))


def count_by_suite(results: list[EvalResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        for suite in result.case.get("suite", []):
            counts[str(suite)] = counts.get(str(suite), 0) + 1
    return dict(sorted(counts.items()))


def render_counts_table(title: str, counts: dict[str, int]) -> list[str]:
    if not counts:
        return []
    lines = [f"## {title}", "", "| Name | Count |", "| --- | ---: |"]
    lines.extend([f"| `{markdown_cell(name, 80)}` | {count} |" for name, count in counts.items()])
    lines.append("")
    return lines


def render_failure_index(results: list[EvalResult]) -> list[str]:
    failures = [result for result in results if result.failures]
    if not failures:
        return ["## Needs Attention", "", "No automated failures.", ""]

    lines = ["## Needs Attention", "", "| Case | Failures |", "| --- | --- |"]
    for result in failures:
        case_id = result.case.get("id")
        joined = "; ".join(result.failures)
        lines.append(f"| `{markdown_cell(case_id, 80)}` | {markdown_cell(joined, 260)} |")
    lines.append("")
    return lines


def render_review_table(results: list[EvalResult]) -> list[str]:
    lines = [
        "## Review Table",
        "",
        "Use the **Human Grade** column while eyeballing answers: `good`, `acceptable`, `wrong-source`, `too-vague`, `unsafe`, `tone-issue`, `routing-issue`.",
        "",
        "| Status | Human Grade | Case | Route | Sources | Prompt | Answer Preview |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        case_id = result.case.get("id")
        lines.append(
            "| "
            f"{review_status(result)} | "
            "TODO | "
            f"`{markdown_cell(case_id, 80)}` | "
            f"{markdown_cell(route_label(result), 120)} | "
            f"{markdown_cell(source_summary(result), 140)} | "
            f"{markdown_cell(result.case.get('message'), 150)} | "
            f"{markdown_cell(answer_preview(result), 240)} |"
        )
    lines.append("")
    return lines


def render_case_detail(result: EvalResult) -> list[str]:
    case = result.case
    response = result.response or {}
    log_entry = result.log_entry or {}
    status = review_status(result)
    lines = [
        f"## {status} `{case.get('id')}`",
        "",
        "Human review: `[ ] good` `[ ] acceptable` `[ ] wrong-source` `[ ] too-vague` `[ ] unsafe` `[ ] tone-issue` `[ ] routing-issue`",
        "",
        "Reviewer notes:",
        "",
        "> ",
        "",
        f"Suites: `{', '.join(case.get('suite', []))}`",
        "",
        f"Prompt: {case.get('message')}",
        "",
    ]
    if case.get("review_note"):
        lines.extend([f"Review note: {case['review_note']}", ""])
    if result.failures:
        lines.append("Failures:")
        lines.extend([f"- {failure}" for failure in result.failures])
        lines.append("")
    if result.warnings:
        lines.append("Warnings:")
        lines.extend([f"- {warning}" for warning in result.warnings])
        lines.append("")

    lines.extend([
        "Routing:",
        f"- authoritative: `{response.get('has_authoritative_sources')}`",
        f"- redirect_category: `{response.get('redirect_category')}`",
        f"- detected_company: `{response.get('detected_company')}`",
        f"- log_tier: `{log_entry.get('tier')}`",
        f"- rewritten_query: `{log_entry.get('rewritten_query')}`",
        "",
    ])

    titles = source_titles(response)
    lines.append("Sources:")
    if titles:
        lines.extend([f"- {title}" for title in titles])
    else:
        lines.append("- None")
    lines.extend(["", "Answer:", "", "```text", str(response.get("answer", "")).strip(), "```", ""])
    return lines


def render_markdown(results: list[EvalResult], base_url: str) -> str:
    totals = summary(results)
    lines = [
        "# Chat Eval Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Base URL: `{base_url}`",
        f"- Result: {totals['passed']}/{totals['total']} passed, {totals['failed']} failed, {totals['warnings']} warnings",
        "",
    ]

    lines.extend(render_failure_index(results))
    lines.extend(render_review_table(results))
    lines.extend(render_counts_table("Tier Summary", count_by_tier(results)))
    lines.extend(render_counts_table("Suite Coverage", count_by_suite(results)))
    lines.extend(["# Detailed Answers", ""])

    for result in results:
        lines.extend(render_case_detail(result))

    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chat eval cases against the backend.")
    parser.add_argument("--base-url", default=os.environ.get("CHATBOT_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--suite", action="append", help="Run only cases in this suite. Can be repeated.")
    parser.add_argument("--id", action="append", help="Run only a specific case id. Can be repeated.")
    parser.add_argument("--limit", type=int, help="Run only the first N selected cases.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--token-env", default="API_BEARER_TOKEN")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--delay", type=float, default=None, help="Seconds to wait between chat requests.")
    parser.add_argument("--skip-logs", action="store_true", help="Do not fetch /logs for tier checks.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--label", default=None, help="Report filename label.")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--health", action="store_true", help="Check /health before running cases.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    token = load_token(args.env_file, args.token_env)
    client = ApiClient(args.base_url, token=token, timeout=args.timeout)

    if args.health:
        health = client.get("/health")
        print(f"Health: {json.dumps(health, ensure_ascii=False)}")

    cases = select_cases(load_cases(args.cases), suites=args.suite, ids=args.id, limit=args.limit)
    if not cases:
        print("No eval cases selected.", file=sys.stderr)
        return 2

    delay = should_delay(args.base_url, len(cases), args.delay)
    print(f"Running {len(cases)} case(s) against {args.base_url} with delay={delay}s")
    results = run_cases(client, cases, with_logs=not args.skip_logs, delay=delay)
    totals = summary(results)

    if not args.no_report:
        label = args.label or ("-".join(args.suite) if args.suite else "chat-evals")
        json_path, md_path = write_reports(results, args.report_dir, label, args.base_url)
        print(f"JSON report: {json_path}")
        print(f"Markdown report: {md_path}")

    print(f"Summary: {totals['passed']}/{totals['total']} passed; {totals['failed']} failed; {totals['warnings']} warnings")
    return 0 if totals["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
