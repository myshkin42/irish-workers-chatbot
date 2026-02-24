"""
Monthly currency check for Irish Workers' Rights Chatbot.

Checks key source URLs for changes since last check.
Stores hashes of page content to detect updates.

Run monthly:
    python -m app.check_currency
    python -m app.check_currency --reset    # Reset all hashes (first run)
"""
import os
import json
import hashlib
import argparse
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Where we store the last-known hashes
HASH_FILE = Path(__file__).parent.parent / "currency_hashes.json"

# URLs to monitor, grouped by priority and update frequency
SOURCES_TO_CHECK = {
    # =====================================================================
    # HIGH PRIORITY - check these carefully every month
    # =====================================================================
    "high": [
        {
            "name": "National Minimum Wage (Citizens Info)",
            "url": "https://www.citizensinformation.ie/en/employment/employment-rights-and-conditions/pay-and-employment/minimum-wage/",
            "notes": "Changes annually in January. Check rate and sub-minimum rates.",
            "update_frequency": "annual",
        },
        {
            "name": "Sick Leave Entitlements (Citizens Info)",
            "url": "https://www.citizensinformation.ie/en/employment/employment-rights-and-conditions/leave-and-holidays/sick-leave-and-sick-pay/",
            "notes": "Days increasing yearly: 5 (2025) → 7 (2026) → 10 (2027).",
            "update_frequency": "annual",
        },
        {
            "name": "WRC - Codes of Practice",
            "url": "https://www.workplacerelations.ie/en/what_you_should_know/codes_practice/",
            "notes": "New codes or updates to existing ones.",
            "update_frequency": "irregular",
        },
        {
            "name": "WRC - Employment Law Explained",
            "url": "https://www.workplacerelations.ie/en/publications_forms/",
            "notes": "Main WRC publications page. PDF at employment-law-explained.pdf",
            "update_frequency": "irregular",
        },
    ],

    # =====================================================================
    # MEDIUM PRIORITY - check quarterly or when flagged
    # =====================================================================
    "medium": [
        {
            "name": "Unfair Dismissal (Citizens Info)",
            "url": "https://www.citizensinformation.ie/en/employment/unemployment-and-redundancy/dismissal/unfair-dismissal/",
            "notes": "Core rights page. Rarely changes but high impact if it does.",
            "update_frequency": "rare",
        },
        {
            "name": "Working Hours (Citizens Info)",
            "url": "https://www.citizensinformation.ie/en/employment/employment-rights-and-conditions/hours-of-work/working-hours/",
            "notes": "Organisation of Working Time Act content.",
            "update_frequency": "rare",
        },
        {
            "name": "Maternity Leave (Citizens Info)",
            "url": "https://www.citizensinformation.ie/en/employment/employment-rights-and-conditions/leave-and-holidays/maternity-leave/",
            "notes": "Leave entitlements and benefit rates.",
            "update_frequency": "annual",
        },
        {
            "name": "Redundancy Payments (Citizens Info)",
            "url": "https://www.citizensinformation.ie/en/employment/unemployment-and-redundancy/redundancy/redundancy-payments/",
            "notes": "Calculation method and eligibility.",
            "update_frequency": "rare",
        },
        {
            "name": "Employment Equality (Citizens Info)",
            "url": "https://www.citizensinformation.ie/en/employment/equality-in-work/equality-in-the-workplace/",
            "notes": "9 grounds of discrimination.",
            "update_frequency": "rare",
        },
        {
            "name": "EROs and SEOs (WRC)",
            "url": "https://www.workplacerelations.ie/en/what_you_should_know/hours-and-wages/employment%20regulation%20orders/",
            "notes": "Sector-specific wage orders. Construction, cleaning, security, childcare.",
            "update_frequency": "annual",
        },
        {
            "name": "HSA - Guides and Publications",
            "url": "https://www.hsa.ie/eng/publications_and_forms/",
            "notes": "Safety guides and codes of practice.",
            "update_frequency": "irregular",
        },
    ],

    # =====================================================================
    # LOW PRIORITY - check every 3-6 months
    # =====================================================================
    "low": [
        {
            "name": "Irish Statute Book - Recent Acts",
            "url": "https://www.irishstatutebook.ie/eli/acts.html",
            "notes": "New employment-related Acts.",
            "update_frequency": "rare",
        },
        {
            "name": "IHREC - Employment Equality Summary",
            "url": "https://www.ihrec.ie/guides-and-tools/human-rights-and-equality-for-employers/what-does-the-law-say/eea-summary/",
            "notes": "Discrimination and equality guidance. 9 grounds summary.",
            "update_frequency": "rare",
        },
        {
            "name": "ICTU - Union Directory",
            "url": "https://www.ictu.ie/unions",
            "notes": "Union listings and contact info.",
            "update_frequency": "rare",
        },
    ],
}


def load_hashes() -> dict:
    """Load previously stored hashes."""
    if HASH_FILE.exists():
        return json.loads(HASH_FILE.read_text())
    return {}


def save_hashes(hashes: dict):
    """Save current hashes."""
    HASH_FILE.write_text(json.dumps(hashes, indent=2))


# Browser-like headers to avoid bot detection (especially Citizens Information)
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IE,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


# Persistent session — reuses connections and cookies across requests
_session = requests.Session()
_session.headers.update(BROWSER_HEADERS)


def get_page_hash(url: str) -> tuple[str | None, str | None]:
    """Fetch a URL and return its content hash. Returns (hash, error)."""
    import time
    time.sleep(1)  # Be polite — 1 second between requests
    try:
        response = _session.get(url, timeout=15)
        response.raise_for_status()
        content_hash = hashlib.sha256(response.text.encode()).hexdigest()[:16]
        return content_hash, None
    except requests.RequestException as e:
        return None, str(e)[:80]


def run_check(reset: bool = False):
    """Run the currency check against all monitored sources."""
    stored_hashes = {} if reset else load_hashes()
    new_hashes = {}
    
    changed = []
    errors = []
    unchanged = []
    new_sources = []

    print("=" * 70)
    print(f"Irish Workers Chatbot - Currency Check")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if reset:
        print("MODE: RESET (storing baseline hashes)")
    print("=" * 70)

    for priority, sources in SOURCES_TO_CHECK.items():
        print(f"\n{'─'*70}")
        print(f"  {priority.upper()} PRIORITY")
        print(f"{'─'*70}")

        for source in sources:
            name = source["name"]
            url = source["url"]
            notes = source["notes"]

            current_hash, error = get_page_hash(url)

            if error:
                status = f"⚠️  ERROR: {error}"
                errors.append(name)
            elif name not in stored_hashes:
                status = "🆕 NEW (no previous hash)"
                new_sources.append(name)
            elif current_hash != stored_hashes.get(name):
                status = "🔄 CHANGED — review and re-ingest if needed"
                changed.append((name, notes))
            else:
                status = "✅ No change"
                unchanged.append(name)

            print(f"\n  {name}")
            print(f"    {status}")
            if current_hash != stored_hashes.get(name) and not error:
                print(f"    Notes: {notes}")
                print(f"    URL: {url}")

            # Store new hash
            if current_hash:
                new_hashes[name] = current_hash

    # Save updated hashes
    save_hashes(new_hashes)

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"  ✅ Unchanged: {len(unchanged)}")
    print(f"  🆕 New:       {len(new_sources)}")
    print(f"  🔄 Changed:   {len(changed)}")
    print(f"  ⚠️  Errors:    {len(errors)}")

    if changed:
        print(f"\n{'─' * 70}")
        print("  SOURCES THAT NEED REVIEW:")
        print(f"{'─' * 70}")
        for name, notes in changed:
            print(f"  → {name}")
            print(f"    {notes}")

    if errors:
        print(f"\n  FETCH ERRORS (may be temporary):")
        for name in errors:
            print(f"  → {name}")

    print(f"\nHashes saved to: {HASH_FILE}")
    print(f"Next check: run again in ~1 month")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check source currency")
    parser.add_argument("--reset", action="store_true", help="Reset all stored hashes (first run)")
    args = parser.parse_args()
    run_check(reset=args.reset)
