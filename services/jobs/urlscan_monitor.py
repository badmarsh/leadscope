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

def search_urlscan(snippet: str, size: int = 100) -> list[dict]:
    # Quote snippet for exact phrase matching
    query = f'page.body:"{snippet}"'
    encoded_query = quote(query)
    url = f"{URLSCAN_SEARCH_URL}?q={encoded_query}&size={size}"
    
    headers = {"Accept": "application/json"}
    if URLSCAN_API_KEY:
        headers["API-Key"] = URLSCAN_API_KEY

    retries = 3
    backoff = 5
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=25)
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

            results = search_urlscan(snippet)
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
