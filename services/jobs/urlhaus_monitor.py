"""
urlhaus_monitor.py — Ingest active malware URLs from abuse.ch URLhaus API.

Polls recent URLhaus entries, filters for live WordPress infections,
and upserts extracted domains into candidates.

Usage:
    python services/jobs/urlhaus_monitor.py
    python services/jobs/urlhaus_monitor.py --dry-run
"""
import argparse
import logging
import requests
import sys
import os
import csv

# Add parent directory to path to allow importing discovery_helpers if needed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discovery_helpers import get_conn, get_campaign_id, extract_domain, upsert_candidate, log_api_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s")
logger = logging.getLogger("urlhaus_monitor")

URLHAUS_AUTH_KEY = os.environ.get("URLHAUS_AUTH_KEY", "")
URLHAUS_API_URL = "https://urlhaus-api.abuse.ch/v1/urls/recent/"
URLHAUS_RECENT_CSV = "https://urlhaus.abuse.ch/downloads/csv_recent/"

def fetch_urlhaus_recent(limit: int = 1000) -> list[dict]:
    """
    Fetch recent URLhaus URLs.
    Uses Auth-Key API via GET if URLHAUS_AUTH_KEY is provided, otherwise falls back to bulk CSV export.
    """
    if URLHAUS_AUTH_KEY:
        try:
            logger.info("Fetching via URLhaus Auth-Key API...")
            headers = {"Auth-Key": URLHAUS_AUTH_KEY}
            resp = requests.get(URLHAUS_API_URL, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("query_status") == "ok":
                urls = data.get("urls", [])
                logger.info("Successfully fetched %d entries via URLhaus API", len(urls))
                return urls[:limit]
            else:
                logger.warning("URLhaus API query status: %s, falling back to CSV", data.get("query_status"))
        except Exception as e:
            logger.warning("URLhaus API failed: %s, falling back to CSV export", e)

    # Fallback to CSV export
    try:
        logger.info("Fetching via URLhaus bulk CSV export...")
        resp = requests.get(URLHAUS_RECENT_CSV, timeout=30, headers={"User-Agent": "LeadScope/1.0"})
        resp.raise_for_status()
        lines = resp.text.splitlines()

        results = []
        data_lines = [l for l in lines if not l.startswith("#") and l.strip()]
        reader = csv.reader(data_lines)
        for parts in reader:
            if len(parts) < 7:
                continue
            
            try:
                results.append({
                    "id": parts[0],
                    "date_added": parts[1],
                    "url": parts[2],
                    "url_status": parts[3],
                    "threat": parts[5],
                    "tags": [t.strip() for t in parts[6].split(",")] if parts[6] else [],
                })
            except IndexError:
                continue

            if len(results) >= limit:
                break

        return results
    except Exception as e:
        logger.error("Failed to fetch URLhaus CSV: %s", e)
        return []

def process_urlhaus(dry_run: bool = False):
    logger.info("Starting URLhaus monitor (dry_run=%s)", dry_run)
    urls = fetch_urlhaus_recent()
    logger.info("Fetched %d recent entries from URLhaus", len(urls))

    conn = get_conn()
    try:
        campaign_id = get_campaign_id(conn)
        inserted = 0
        skipped = 0

        for entry in urls:
            status = entry.get("url_status")
            if status != "online":
                continue

            raw_url = entry.get("url", "")
            tags = [t.lower() for t in entry.get("tags") or []]

            is_wp = (
                "wp-content" in raw_url
                or "wp-admin" in raw_url
                or "wordpress" in raw_url
                or "wp-includes" in raw_url
                or "wordpress" in tags
                or "wp" in tags
            )

            if not is_wp:
                continue

            domain = extract_domain(raw_url)
            if not domain:
                continue

            evidence = {
                "urlhaus_id": entry.get("id"),
                "url": raw_url,
                "threat": entry.get("threat"),
                "tags": entry.get("tags"),
                "date_added": entry.get("date_added"),
                "reporter": entry.get("reporter"),
            }

            query_used = f"urlhaus:wordpress_malware:{entry.get('threat', 'unknown')}"

            if dry_run:
                logger.info("  [DRY RUN] Would insert: %s (%s)", domain, raw_url)
                inserted += 1
                continue

            ok = upsert_candidate(
                conn,
                campaign_id=campaign_id,
                domain=domain,
                source="urlhaus",
                query_used=query_used,
                evidence=evidence,
            )

            if ok:
                inserted += 1
                logger.info("  ✓ Inserted: %s", domain)
            else:
                skipped += 1

        if not dry_run:
            log_api_call(conn, campaign_id=campaign_id, stage="discovery", provider="urlhaus", query_count=1)
            conn.commit()

        logger.info("URLhaus monitor finished. Found WP matching: %d | Inserted: %d | Skipped: %d", inserted + skipped, inserted, skipped)

    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="URLhaus malware feed ingest")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and process without inserting to DB")
    args = parser.parse_args()

    process_urlhaus(dry_run=args.dry_run)
