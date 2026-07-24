"""
publicwww_scraper.py — Scrape PublicWWW via Crawl4AI browser (no API key needed).

Uses the crawler service (http://localhost:8003) to:
  1. Load each PublicWWW search results page (Chromium handles the JS PoW challenge)
  2. Parse domain URLs from the rendered HTML
  3. Upsert matched domains as candidates in the wp-remediation campaign

Usage:
    python publicwww_scraper.py            # run all signatures
    python publicwww_scraper.py --dry-run  # print results, don't insert
"""
import argparse
import json
import logging
import re
import time
from urllib.parse import quote, urlparse

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

CRAWLER_ENDPOINT = os.environ.get("CRAWLER_ENDPOINT_LOCAL", os.environ.get("CRAWLER_ENDPOINT", "http://crawler:8003"))
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://leadscope:leadscope_dev@localhost:5432/leadscope")
CAMPAIGN_SLUG = "wp-remediation"

# Domains that belong to PublicWWW itself or are clearly false positives
BLOCKLIST_DOMAINS = {
    "publicwww.com", "google.com", "facebook.com", "twitter.com",
    "youtube.com", "wikipedia.org", "github.com", "stackoverflow.com",
    "w3.org", "schema.org", "jquery.com", "cloudflare.com",
}

# ── DB helpers ────────────────────────────────────────────────────────────────

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


def get_signatures(conn, campaign_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, snippet, malware_family, confidence, source_url FROM malware_signatures "
            "WHERE campaign_id = %s AND status = 'approved' ORDER BY confidence DESC",
            (campaign_id,),
        )
        return cur.fetchall()


def is_do_not_contact(conn, domain: str, campaign_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM do_not_contact
            WHERE (%s = domain OR %s LIKE '%%.' || domain)
              AND (campaign_id = %s OR campaign_id IS NULL)
            LIMIT 1
            """,
            (domain, domain, campaign_id),
        )
        return cur.fetchone() is not None


def upsert_candidate(conn, *, campaign_id: int, domain: str, evidence: dict) -> bool:
    """Insert or reopen candidate. Returns True if row was written."""
    import tldextract
    ext = tldextract.extract(domain)
    if ext.subdomain and ext.subdomain != 'www':
        return False

    if is_do_not_contact(conn, domain, campaign_id):
        return False
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO candidates
                (campaign_id, domain, source, query_used, evidence_data, last_seen_at)
            VALUES (%s, %s, 'code_signature_search', %s, %s, now())
            ON CONFLICT (campaign_id, domain) DO UPDATE SET
                last_seen_at  = now(),
                reopen_count  = candidates.reopen_count + 1,
                evidence_data = EXCLUDED.evidence_data
            WHERE candidates.status = 'stale'
            """,
            (
                campaign_id,
                domain,
                f"publicwww_scrape:{evidence.get('malware_family', 'unknown')}",
                json.dumps(evidence),
            ),
        )
        return cur.rowcount > 0


# ── Parsing helpers ───────────────────────────────────────────────────────────

def extract_domain(url: str) -> str | None:
    """Extract apex domain from URL string, stripping subdomains."""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        host = (parsed.netloc or parsed.path).split(":")[0].strip()
        import tldextract
        ext = tldextract.extract(host)
        top_domain = getattr(ext, "top_domain_under_public_suffix", "") or getattr(ext, "registered_domain", "")
        if top_domain:
            return top_domain.lower()
        return None
    except Exception:
        return None


def parse_results_from_markdown(markdown: str) -> list[dict]:
    """
    Extract result URLs AND code snippet context from PublicWWW markdown table rows.
    Row format: |  rank  |  [](https://domain/) https://domain/  |  snippet context  |
    Returns list of dicts: {domain, context}
    """
    results = []
    seen = set()

    # Capture: URL column + everything up to the next pipe (the Snippets column)
    row_pattern = re.compile(
        r'\[\]\(https?://[^)]+\)\s+(https?://[^\s|]+)[^|]*\|([^|\n]+)',
        re.IGNORECASE,
    )
    for match in row_pattern.finditer(markdown):
        raw_url = match.group(1).rstrip("/")
        context = match.group(2).strip() if match.group(2) else ""
        domain = extract_domain(raw_url)
        if (
            domain
            and domain not in BLOCKLIST_DOMAINS
            and "publicwww.com" not in domain
            and domain not in seen
        ):
            seen.add(domain)
            results.append({"domain": domain, "context": context})

    return results


def parse_domains_from_markdown(markdown: str) -> list[str]:
    """Backwards-compat wrapper — returns just domain strings."""
    return [r["domain"] for r in parse_results_from_markdown(markdown)]


# ── Crawler call ──────────────────────────────────────────────────────────────

def crawl_publicwww(snippet: str, page: int = 1, use_quotes: bool = True) -> str | None:
    """
    Use Crawl4AI crawler service to fetch PublicWWW search results.
    Returns markdown text or None on failure.
    Always uses quoted phrase search for precision (avoids false positives).
    """
    # The user has explicitly noted that wrapping the query in quotes breaks the +depth:all
    # modifier for complex queries like `base64_decode(str_rot13(`.
    search_term = snippet
    encoded = quote(search_term, safe="")
    
    # PublicWWW pagination: ?from=N (0-based, 10 results per page)
    offset = (page - 1) * 10
    # Append +depth:all to do an internal pages search (yields more unredacted results)
    url = f"https://publicwww.com/websites/{encoded}+depth:all/"
    if offset > 0:
        url += f"?from={offset}"

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


def extract_result_count(markdown: str) -> int:
    """Parse '1141 web pages in 0.21 s.' from markdown."""
    match = re.search(r"(\d[\d,]*)\s+web pages? in", markdown)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


# ── Main scrape loop ──────────────────────────────────────────────────────────

def scrape_signature(
    sig: dict,
    campaign_id: int,
    conn,
    dry_run: bool = False,
    max_pages: int = 5,
) -> dict:
    """
    Scrape PublicWWW for a single signature, paginating up to max_pages.
    Returns stats dict.
    """
    snippet = sig["snippet"].strip()
    family = sig["malware_family"] or "Unknown"
    confidence = sig["confidence"]
    
    # PublicWWW's phrase matching breaks if we wrap complex PHP snippets (with their own quotes) in double quotes.
    # We'll rely on the raw snippet for now, which the user verified works.
    use_quotes = False
    
    logger.info(
        "=== Signature #%s | %s | confidence=%s | quoted=%s ===",
        sig["id"], family, confidence, use_quotes,
    )
    
    all_domains = []
    inserted = 0
    skipped = 0

    for page in range(1, max_pages + 1):
        markdown = crawl_publicwww(snippet, page=page, use_quotes=use_quotes)
        if not markdown:
            break

        # On first page, check total result count
        if page == 1:
            total = extract_result_count(markdown)
            logger.info("Total results reported by PublicWWW: %d", total)
            if total == 0:
                logger.info("No results for this signature — skipping")
                break

        results = parse_results_from_markdown(markdown)

        if not results:
            logger.info("Page %d: no new domains found — stopping pagination", page)
            break
            
        logger.info("Page %d: found %d domains", page, len(results))

        for result in results:
            domain = result["domain"]
            context = result.get("context", "")
            all_domains.append(domain)

            if dry_run:
                logger.info("  [DRY RUN] Would insert: %s (context: %s)", domain, context[:80])
                inserted += 1
                continue

            evidence = {
                "matched_signatures": [{
                    "signature_id": sig["id"],
                    "snippet": snippet[:200],
                    "malware_family": family,
                    "confidence": confidence,
                    "source": "publicwww_scrape",
                    "publicwww_context": context[:500],  # The actual code snippet from the site
                }]
            }

            ok = upsert_candidate(
                conn,
                campaign_id=campaign_id,
                domain=domain,
                evidence=evidence,
            )
            if ok:
                inserted += 1
                logger.info("  ✓ Inserted: %s | context: %s", domain, context[:80])
            else:
                skipped += 1

        if not dry_run:
            conn.commit()

        # Polite delay between pages
        if page < max_pages:
            time.sleep(3)

    return {
        "signature_id": sig["id"],
        "malware_family": family,
        "domains_found": len(all_domains),
        "inserted": inserted,
        "skipped": skipped,
    }


def main():
    parser = argparse.ArgumentParser(description="PublicWWW scraper via Crawl4AI")
    parser.add_argument("--dry-run", action="store_true", help="Parse but don't insert")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages per signature")
    parser.add_argument("--sig-id", type=int, help="Only run a specific signature ID")
    args = parser.parse_args()

    logger.info("Starting PublicWWW scraper (dry_run=%s, max_pages=%d)", args.dry_run, args.max_pages)

    conn = get_conn()
    try:
        campaign_id = get_campaign_id(conn)
        logger.info("Campaign ID: %d (%s)", campaign_id, CAMPAIGN_SLUG)

        signatures = get_signatures(conn, campaign_id)
        if args.sig_id:
            signatures = [s for s in signatures if s["id"] == args.sig_id]

        logger.info("Found %d signatures to process", len(signatures))

        total_inserted = 0
        all_results = []

        for sig in signatures:
            try:
                result = scrape_signature(
                    sig, campaign_id, conn,
                    dry_run=args.dry_run,
                    max_pages=args.max_pages,
                )
                all_results.append(result)
                total_inserted += result["inserted"]
                # Polite delay between signatures
                time.sleep(5)
            except Exception as exc:
                logger.error("Failed processing signature %s: %s", sig["id"], exc)
                conn.rollback()

        logger.info("\n=== FINAL REPORT ===")
        logger.info("Total new candidates inserted: %d", total_inserted)
        for r in all_results:
            logger.info(
                "  sig#%d %-30s → %d found, %d inserted, %d skipped",
                r["signature_id"], r["malware_family"],
                r["domains_found"], r["inserted"], r["skipped"],
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
