import os
import sys
import json
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
FIRECRAWL_ENDPOINT = os.environ.get("FIRECRAWL_ENDPOINT", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def check_budget(cur, provider: str) -> bool:
    """Returns True if budget allows querying, False if quota exceeded."""
    # Sum current month's query count
    cur.execute("""
        SELECT COALESCE(SUM(query_count), 0)
        FROM api_call_log
        WHERE provider = %s
          AND date_trunc('month', created_at) = date_trunc('month', now())
    """, (provider,))
    used = cur.fetchone()[0]

    cur.execute("SELECT monthly_quota FROM provider_budgets WHERE provider = %s", (provider,))
    row = cur.fetchone()
    if not row:
        return True # No budget constraint
    
    quota = row[0]
    return used < quota

def scrape_homepage(domain: str) -> str:
    """Scrape the homepage HTML using Firecrawl. Supports file:// for tests."""
    if domain.startswith("file://"):
        path = domain[7:]
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    if not FIRECRAWL_API_KEY:
        # Fallback to plain requests
        url = f"http://{domain}" if not domain.startswith("http") else domain
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.text

    url = f"http://{domain}" if not domain.startswith("http") else domain
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    # For re-verification, we want the raw HTML to check for code snippets, 
    # not markdown (which might strip scripts/php). 
    payload = {"url": url, "formats": ["html"]}
    
    endpoint = FIRECRAWL_ENDPOINT
    if not endpoint.endswith("/v1/scrape"):
        endpoint = f"{endpoint.rstrip('/')}/v1/scrape"

    r = requests.post(endpoint, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("success") and "data" in data and "html" in data["data"]:
        return data["data"]["html"]
    else:
        raise Exception(f"Firecrawl scrape failed: {data}")

def reverify():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
    row = cur.fetchone()
    if not row:
        print("wp-remediation campaign not found.")
        return
    campaign_id = row[0]

    # Check budget for firecrawl
    provider = "firecrawl" if FIRECRAWL_API_KEY else "requests"
    if provider == "firecrawl" and not check_budget(cur, provider):
        print(f"Skipping re-verification: {provider} budget exceeded for the month.")
        return

    cur.execute("""
        SELECT id, domain, evidence_data
        FROM candidates
        WHERE campaign_id = %s AND status IN ('approved', 'evaluated', 'enriched')
    """, (campaign_id,))
    
    candidates = cur.fetchall()
    print(f"Found {len(candidates)} candidates to re-verify.")

    stale_count = 0
    for cid, domain, evidence in candidates:
        if provider == "firecrawl" and not check_budget(cur, provider):
            print("Budget exhausted mid-run. Stopping.")
            break

        print(f"Checking {domain}...")
        try:
            # Re-fetch homepage
            html = scrape_homepage(domain)
            
            # Log API call
            cur.execute("""
                INSERT INTO api_call_log (campaign_id, stage, provider, query_count)
                VALUES (%s, 'reverification', %s, 1)
            """, (campaign_id, provider))

            # The evidence_data might contain a list of matched snippets
            # "evidence_data populated with which signature(s) matched"
            # We assume it looks like: {"signatures": ["<?php ..."]} or similar.
            snippets = []
            if evidence and isinstance(evidence, dict):
                snippets = evidence.get("signatures", [])
            elif evidence and isinstance(evidence, list):
                snippets = evidence # In case it's just a list of strings
                
            if not snippets:
                print("  No signatures found in evidence_data, skipping.")
                continue

            # Check if ANY of the originally detected snippets are still present
            still_present = False
            for snippet in snippets:
                # normalize whitespace just in case
                if snippet.strip() in html:
                    still_present = True
                    break
            
            if not still_present:
                print("  Signature missing. Flipping to stale.")
                cur.execute("UPDATE candidates SET status = 'stale' WHERE id = %s", (cid,))
                stale_count += 1
            else:
                print("  Signature verified.")

        except Exception as e:
            print(f"  Failed to scrape {domain}: {e}")

    print(f"Done. Re-verified {len(candidates)} candidates, flipped {stale_count} to stale.")
    conn.close()

if __name__ == "__main__":
    reverify()
