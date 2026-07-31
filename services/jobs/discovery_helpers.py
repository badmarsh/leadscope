"""
discovery_helpers.py — Shared helpers for all job-based discovery modules.
Mirrors the pattern from publicwww_scraper.py.
"""
import json
import logging
import os
import re
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope")
CAMPAIGN_SLUG = "wp-remediation"

BLOCKLIST_DOMAINS = {
    "publicwww.com", "google.com", "facebook.com", "twitter.com",
    "youtube.com", "wikipedia.org", "github.com", "cloudflare.com",
    "amazonaws.com", "azure.com", "vercel.app", "netlify.app",
    "fastly.net", "pages.dev", "github.io"
}

def get_conn():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn

def get_campaign_id(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM campaigns WHERE slug = %s", (CAMPAIGN_SLUG,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Campaign '{CAMPAIGN_SLUG}' not found in DB")
        return row["id"]

def get_approved_signatures(conn, campaign_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, snippet, malware_family, confidence, proof_method, outbreak_scope "
            "FROM malware_signatures WHERE campaign_id = %s AND status = 'approved' "
            "ORDER BY confidence DESC",
            (campaign_id,),
        )
        return cur.fetchall()

def is_do_not_contact(conn, domain: str, campaign_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM do_not_contact WHERE (%s = domain OR %s LIKE '%%.' || domain) "
            "AND (campaign_id = %s OR campaign_id IS NULL) LIMIT 1",
            (domain, domain, campaign_id),
        )
        return cur.fetchone() is not None

def extract_domain(url: str) -> str | None:
    try:
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        host = (parsed.netloc or parsed.path).split(":")[0].strip()
        import tldextract
        ext = tldextract.extract(host)
        top_domain = f"{ext.domain}.{ext.suffix}" if ext.domain and ext.suffix else ""
        if top_domain:
            return top_domain.lower()
        return None
    except Exception:
        return None

def upsert_candidate(conn, *, campaign_id: int, domain: str, source: str, query_used: str, evidence: dict, status: str = 'new') -> bool:
    import tldextract
    ext = tldextract.extract(domain)
    if ext.subdomain and ext.subdomain != 'www':
        return False

    if domain in BLOCKLIST_DOMAINS or any(domain.endswith(b) for b in BLOCKLIST_DOMAINS):
        return False
    if is_do_not_contact(conn, domain, campaign_id):
        return False
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO candidates (campaign_id, domain, source, query_used, evidence_data, last_seen_at, status) "
            "VALUES (%s, %s, %s, %s, %s, now(), %s) "
            "ON CONFLICT (campaign_id, domain) DO UPDATE SET "
            "last_seen_at = now(), reopen_count = candidates.reopen_count + 1, "
            "evidence_data = EXCLUDED.evidence_data",
            (campaign_id, domain, source, query_used, json.dumps(evidence), status),
        )
        return cur.rowcount > 0

def log_api_call(conn, *, campaign_id: int, stage: str, provider: str, query_count: int):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_call_log (campaign_id, stage, provider, query_count, cost_estimate_usd) "
            "VALUES (%s, %s, %s, %s, 0.0)",
            (campaign_id, stage, provider, query_count),
        )
