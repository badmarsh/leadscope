"""
urlscan_monitor.py — Query URLScan.io rendered DOM search API for malware signatures.

Searches rendered DOMs for snippets matching approved malware signatures,
extracting infected domains and upserting into candidates.

Usage:
    python services/jobs/urlscan_monitor.py
    python services/jobs/urlscan_monitor.py --dry-run
    python services/jobs/urlscan_monitor.py --sig-id 39
"""
import argparse
import logging
import time
from urllib.parse import quote
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discovery_helpers import get_conn, get_campaign_id, get_approved_signatures, upsert_candidate, log_api_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s")
logger = logging.getLogger("urlscan_monitor")

URLSCAN_API_KEY = os.environ.get("URLSCAN_API_KEY", "")
URLSCAN_SEARCH_URL = "https://urlscan.io/api/v1/search/"

# URLScan tag-based queries for malware families that security researchers tag on scans.
# These return CURRENT results — scans tagged by the URLScan community in real time.
# Much more reliable than page.body searches (which require exact text match in rendered DOM).
URLSCAN_TAG_MAP = {
    "SocGholish (NDSW)":             "task.tags:socgholish",
    "SocGholish (NDSJ variant)":     "task.tags:ndsw",
    "SocGholish":                    "task.tags:socgholish",
    "Balada Injector":               "task.tags:balada",
    "ClearFake / SocGholish":        "task.tags:clearfake",
    "Sign1 / Generic Redirect":      "task.tags:sign1",
    "msaRAT / Cloudflare Worker C2": "task.tags:msarat",
    "msaRAT":                        "task.tags:msarat",
}

def build_urlscan_query(snippet: str, malware_family: str) -> str:
    """Build the best URLScan query for a given signature.
    Priority:
    1. Tag-based query if the family is known in URLSCAN_TAG_MAP (most results, freshest data)
    2. page.dom phrase search using the longest safe alphanumeric token from the snippet
    3. Falls back to page.body for short snippets
    """
    # Exact family match
    if malware_family in URLSCAN_TAG_MAP:
        return URLSCAN_TAG_MAP[malware_family]
    # Partial family match
    for key, tag_query in URLSCAN_TAG_MAP.items():
        if key.lower() in malware_family.lower() or malware_family.lower() in key.lower():
            return tag_query
    # Extract safest token from snippet (longest alphanumeric run >=6 chars)
    import re
    tokens = re.findall(r'[a-zA-Z0-9_]{6,}', snippet)
    if tokens:
        best_token = max(tokens, key=len)
        return f'page.dom:"{best_token}"'
    return f'page.body:"{snippet[:40]}"'


def search_urlscan(snippet: str, size: int = 100, malware_family: str = "") -> list[dict]:
    query = build_urlscan_query(snippet, malware_family)
    logger.info("  URLScan query: %s", query)

    headers = {"Accept": "application/json"}
    if URLSCAN_API_KEY:
        headers["API-Key"] = URLSCAN_API_KEY

    retries = 3
    backoff = 5
    for attempt in range(retries):
        try:
            # Use params= so requests handles encoding correctly (colons preserved, spaces as %20)
            resp = requests.get(
                URLSCAN_SEARCH_URL,
                params={"q": query, "size": size},
                headers=headers,
                timeout=25,
            )
            if resp.status_code == 429:
                logger.warning("URLScan API rate limit exceeded (HTTP 429). Retrying in %d seconds...", backoff)
                time.sleep(backoff)
                backoff *= 2
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            logger.error("URLScan search request failed for snippet '%s': %s", snippet[:50], e)
            return []
    return []


def process_urlscan(dry_run: bool = False, sig_id: int | None = None):
    logger.info("Starting URLScan monitor (dry_run=%s, sig_id=%s)", dry_run, sig_id)
    if not URLSCAN_API_KEY:
        logger.warning("URLSCAN_API_KEY is not set. Requests will be unauthenticated and subject to strict rate limits (60/day).")
    conn = get_conn()
    try:
        campaign_id = get_campaign_id(conn)
        signatures = get_approved_signatures(conn, campaign_id)

        if sig_id:
            signatures = [s for s in signatures if s["id"] == sig_id]

        if not signatures:
            logger.info("No approved signatures to process.")
            return

        logger.info("Processing %d approved signature(s)", len(signatures))

        total_inserted = 0
        queries_run = 0

        for sig in signatures:
            snippet = sig["snippet"].strip()
            family = sig.get("malware_family") or "Unknown"
            logger.info("Querying URLScan for Sig #%s (%s): '%s'", sig["id"], family, snippet[:60])

            results = search_urlscan(snippet, malware_family=family)
            queries_run += 1
            logger.info("  Found %d scan result(s) from URLScan", len(results))

            sig_inserted = 0
            for res in results:
                page_info = res.get("page", {})
                task_info = res.get("task", {})
                verdicts = res.get("verdicts", {}).get("overall", {})

                domain = page_info.get("domain")
                if not domain:
                    continue

                evidence = {
                    "urlscan_result_url": res.get("result"),
                    "scan_time": task_info.get("time"),
                    "page_url": page_info.get("url"),
                    "is_malicious": verdicts.get("malicious", False),
                    "matched_signature_id": sig["id"],
                    "malware_family": family,
                    "matched_snippet": snippet[:150],
                }

                query_used = f"urlscan:body:{family}"

                if dry_run:
                    logger.info("  [DRY RUN] Would insert: %s", domain)
                    sig_inserted += 1
                    continue

                ok = upsert_candidate(
                    conn,
                    campaign_id=campaign_id,
                    domain=domain,
                    source="urlscan",
                    query_used=query_used,
                    evidence=evidence,
                )

                if ok:
                    sig_inserted += 1
                    logger.info("  ✓ Inserted: %s", domain)

            total_inserted += sig_inserted

            if not dry_run:
                conn.commit()

            # Polite delay between signature searches to respect URLScan API rate limits
            time.sleep(1.5)

        if not dry_run and queries_run > 0:
            log_api_call(conn, campaign_id=campaign_id, stage="discovery", provider="urlscan", query_count=queries_run)
            conn.commit()

        logger.info("URLScan monitor finished. Total inserted: %d across %d queries", total_inserted, queries_run)

    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="URLScan.io DOM search ingest")
    parser.add_argument("--dry-run", action="store_true", help="Search without DB insertion")
    parser.add_argument("--sig-id", type=int, help="Only run a specific signature ID")
    args = parser.parse_args()

    process_urlscan(dry_run=args.dry_run, sig_id=args.sig_id)
