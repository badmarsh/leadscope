"""
publicwww_intel_scraper.py — Scrape PublicWWW using intel queries and snipexp, 
and automatically pivot extracted C2 domains to URLScan to find long-tail victims.
"""
import argparse
import json
import logging
import os
import re
import time
from urllib.parse import quote, urlparse

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

from urlscan_scraper import fetch_urlscan_results, extract_domain

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

CRAWLER_ENDPOINT = os.environ.get("CRAWLER_ENDPOINT_LOCAL", os.environ.get("CRAWLER_ENDPOINT", "http://crawler:8003"))
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope")

def get_conn():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    return conn

def crawl_publicwww(query_string: str, snipexp: str, page: int = 1) -> str | None:
    encoded_query = quote(query_string, safe="")
    offset = (page - 1) * 10
    url = f"https://publicwww.com/websites/{encoded_query}/"
    if snipexp:
        url += f"?snipexp={quote(snipexp)}"
    if offset > 0:
        url += f"&from={offset}" if snipexp else f"?from={offset}"

    logger.info("Crawling: %s", url)
    try:
        resp = requests.post(
            f"{CRAWLER_ENDPOINT}/crawl",
            json={
                "url": url,
                "force_playwright": True,
                "magic": True,
                "timeout_ms": 40000,
                "bypass_cache": True,
            },
            timeout=55,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            logger.warning("Crawler failed for %s: %s", url, data.get("error"))
            return None
        return data.get("markdown", "")
    except Exception as exc:
        logger.error("Crawler request failed: %s", exc)
        return None

def extract_c2_domains(markdown: str) -> set:
    """Extract http/https domains from the markdown snippets"""
    # Simple regex to find domains in the markdown text
    urls = re.findall(r'https?://[a-zA-Z0-9.-]+', markdown)
    domains = set()
    for u in urls:
        # Ignore publicwww itself and our target sites in the first column
        if "publicwww.com" in u:
            continue
        d = extract_domain(u)
        if d:
            domains.add(d)
    return domains

def process_query(conn, query_row: dict, dry_run: bool = False):
    campaign_id = query_row["campaign_id"]
    q_id = query_row["id"]
    name = query_row["name"]
    query_string = query_row["query_string"]
    snipexp_regex = query_row["snipexp_regex"]
    confidence = query_row["confidence"]
    
    logger.info("=== Processing Intel Query: %s ===", name)
    
    # 1. Crawl PublicWWW to get C2 domains
    markdown = crawl_publicwww(query_string, snipexp_regex, page=1)
    if not markdown:
        return {"inserted": 0, "skipped": 0, "pivots": 0}
        
    c2_domains = extract_c2_domains(markdown)
    logger.info("  Extracted %d potential C2 domains/URLs from PublicWWW snippets", len(c2_domains))
    
    total_inserted = 0
    total_skipped = 0
    pivots_executed = 0
    
    # 2. Pivot to URLScan for each extracted C2 domain
    for c2 in c2_domains:
        urlscan_query = f'page.url:"{c2}"'
        logger.info("  Pivoting to URLScan -> %s", urlscan_query)
        results = fetch_urlscan_results(urlscan_query, size=50)
        pivots_executed += 1
        
        for res in results:
            page_url = res.get("page", {}).get("url")
            if not page_url:
                continue
            
            domain = extract_domain(page_url)
            if not domain:
                continue
                
            if dry_run:
                logger.info("    [DRY RUN] Would insert %s (via %s pivot)", domain, c2)
                total_inserted += 1
                continue

            evidence = {
                "intel_query_id": q_id,
                "query_name": name,
                "matched_url": page_url,
                "pivot_c2": c2,
                "confidence": confidence,
                "source": "publicwww_snipexp_pivot"
            }
            
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM do_not_contact WHERE (%s = domain OR %s LIKE '%%.' || domain) AND (campaign_id = %s OR campaign_id IS NULL) LIMIT 1",
                    (domain, domain, campaign_id)
                )
                if cur.fetchone():
                    total_skipped += 1
                    continue
                    
                cur.execute(
                    """
                    INSERT INTO candidates
                        (campaign_id, domain, source, query_used, evidence_data, last_seen_at)
                    VALUES (%s, %s, 'publicwww_snipexp_pivot', %s, %s, now())
                    ON CONFLICT (campaign_id, domain) DO UPDATE SET
                        last_seen_at  = now(),
                        reopen_count  = candidates.reopen_count + 1,
                        evidence_data = EXCLUDED.evidence_data
                    WHERE candidates.status = 'stale'
                    """,
                    (campaign_id, domain, query_string, json.dumps(evidence))
                )
                if cur.rowcount > 0:
                    total_inserted += 1
                else:
                    total_skipped += 1
        
        time.sleep(2) # rate limit

    return {"inserted": total_inserted, "skipped": total_skipped, "pivots": pivots_executed}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM intel_queries WHERE engine = 'publicwww_snipexp'")
            queries = cur.fetchall()
            
        logger.info("Found %d PublicWWW+Snipexp queries", len(queries))
        
        total_inserted = 0
        for q in queries:
            stats = process_query(conn, q, dry_run=args.dry_run)
            total_inserted += stats["inserted"]
            logger.info("  Result for %s: %d pivots executed, %d inserted, %d skipped", q["name"], stats["pivots"], stats["inserted"], stats["skipped"])
            time.sleep(5)
            
        logger.info("=== PublicWWW Pivot Scrape Complete. Inserted %d total candidates ===", total_inserted)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
