"""
certstream_enricher.py — Passively enrich CertStream-discovered candidates
against abuse.ch threat intelligence feeds (URLhaus + MalwareBazaar).

This job does NOT actively scan any external targets. It only queries
abuse.ch APIs about domains that are already in our candidates table,
asking "do you already know about this domain?".

Candidates sourced from CertStream start with zero infection signal.
This enricher promotes confirmed-bad domains to 'evaluated' status and
annotates their evidence_data with known malware families and threat types.

Workflow:
    1. Pull all candidates WHERE source='certstream' AND status='new'
    2. For each candidate domain:
       a. Query URLhaus host lookup  → known malware distribution host?
       b. Query MalwareBazaar host   → known malware delivery domain?
    3. Merge findings into evidence_data JSONB and update status:
       - Any hit found  → status = 'evaluated', threat_confirmed = True
       - No hit found   → status = 'evaluated', threat_confirmed = False
    4. Log a summary and commit.

Usage:
    python services/jobs/certstream_enricher.py
    python services/jobs/certstream_enricher.py --dry-run
    python services/jobs/certstream_enricher.py --limit 100
    python services/jobs/certstream_enricher.py --dry-run --limit 50
"""
import argparse
import json
import logging
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from discovery_helpers import get_conn, log_api_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] — %(message)s")
logger = logging.getLogger("certstream_enricher")

# ---------------------------------------------------------------------------
# abuse.ch API endpoints (all passive lookups — no scanning of target)
# ---------------------------------------------------------------------------
URLHAUS_API_URL          = "https://urlhaus-api.abuse.ch/v1/host/"
MALWAREBAZAAR_URL        = "https://mb-api.abuse.ch/api/v1/"
URLHAUS_AUTH_KEY         = os.environ.get("URLHAUS_AUTH_KEY", "")
MALWAREBAZAAR_AUTH_KEY   = os.environ.get("MALWAREBAZAAR_AUTH_KEY", "")

# How long to wait between API calls to stay within abuse.ch rate limits
REQUEST_DELAY_SECONDS = 0.5

# Default batch size if --limit is not specified
DEFAULT_LIMIT = 500


# ---------------------------------------------------------------------------
# Passive lookups
# ---------------------------------------------------------------------------

def lookup_urlhaus(domain: str) -> dict | None:
    """
    Query URLhaus host lookup API for a domain.
    Returns parsed JSON response dict, or None on error.
    abuse.ch docs: https://urlhaus-api.abuse.ch/#host-info
    """
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if URLHAUS_AUTH_KEY:
        headers["Auth-Key"] = URLHAUS_AUTH_KEY

    try:
        resp = requests.post(
            URLHAUS_API_URL,
            data={"host": domain},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("URLhaus lookup failed for %s: %s", domain, e)
        return None


def lookup_malwarebazaar(domain: str) -> dict | None:
    """
    Query MalwareBazaar for samples delivered from a host.
    Returns parsed JSON response dict, or None on error.
    Requires MALWAREBAZAAR_AUTH_KEY env var — get a free key at https://auth.abuse.ch/
    abuse.ch docs: https://bazaar.abuse.ch/api/#query_host
    """
    if not MALWAREBAZAAR_AUTH_KEY:
        return None  # Skip gracefully rather than getting a 401

    try:
        resp = requests.post(
            MALWAREBAZAAR_URL,
            data={"query": "search_host", "host": domain},
            headers={"Auth-Key": MALWAREBAZAAR_AUTH_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("MalwareBazaar lookup failed for %s: %s", domain, e)
        return None


# ---------------------------------------------------------------------------
# Result parsing helpers
# ---------------------------------------------------------------------------

def parse_urlhaus_result(data: dict) -> dict:
    """
    Normalise a URLhaus host-info response into a compact summary dict.
    query_status values: 'is_host' (known bad), 'no_results' (clean/unknown)
    """
    status = data.get("query_status", "no_results")
    if status != "is_host":
        return {"urlhaus_known": False}

    urls = data.get("urls", []) or []
    # Summarise only the live/online URLs to keep evidence_data compact
    live = [
        {
            "url": u.get("url"),
            "threat": u.get("threat"),
            "tags": u.get("tags"),
            "date_added": u.get("date_added"),
        }
        for u in urls
        if u.get("url_status") == "online"
    ]

    return {
        "urlhaus_known": True,
        "urlhaus_url_count": data.get("url_count", 0),
        "urlhaus_blacklists": data.get("blacklists", {}),
        "urlhaus_live_urls": live[:10],   # cap at 10 to avoid huge JSON blobs
    }


def parse_malwarebazaar_result(data: dict) -> dict:
    """
    Normalise a MalwareBazaar search_host response into a compact summary dict.
    query_status values: 'ok' (hit found), 'no_results' (clean/unknown)
    """
    status = data.get("query_status", "no_results")
    if status != "ok":
        return {"malwarebazaar_known": False}

    samples = data.get("data", []) or []
    families = list({s.get("signature") for s in samples if s.get("signature")})
    tags = list({t for s in samples for t in (s.get("tags") or [])})

    return {
        "malwarebazaar_known": True,
        "malwarebazaar_sample_count": len(samples),
        "malwarebazaar_families": families[:10],
        "malwarebazaar_tags": tags[:20],
        "malwarebazaar_first_seen": samples[0].get("first_seen") if samples else None,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_certstream_new_candidates(conn, limit: int) -> list[dict]:
    """
    Return up to `limit` candidates from certstream that haven't been
    enriched yet (status = 'new').
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, campaign_id, domain, evidence_data
            FROM candidates
            WHERE source = 'certstream'
              AND status = 'new'
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def update_candidate_enrichment(
    conn,
    candidate_id: int,
    threat_confirmed: bool,
    enrichment: dict,
    dry_run: bool = False,
) -> None:
    """
    Merge enrichment findings into evidence_data and bump status to 'evaluated'.
    """
    if dry_run:
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE candidates
            SET
                status       = 'evaluated',
                evidence_data = evidence_data || %s::jsonb,
                updated_at   = now()
            WHERE id = %s
            """,
            (
                json.dumps({
                    "threat_confirmed": threat_confirmed,
                    "enrichment": enrichment,
                }),
                candidate_id,
            ),
        )


# ---------------------------------------------------------------------------
# Main enrichment loop
# ---------------------------------------------------------------------------

def run_enrichment(dry_run: bool = False, limit: int = DEFAULT_LIMIT) -> None:
    logger.info(
        "Starting CertStream enricher (dry_run=%s, limit=%d)", dry_run, limit
    )
    if not URLHAUS_AUTH_KEY:
        logger.warning(
            "URLHAUS_AUTH_KEY not set — using unauthenticated URLhaus API "
            "(rate limited to 50 requests/day). Set env var for higher limits."
        )
    if not MALWAREBAZAAR_AUTH_KEY:
        logger.warning(
            "MALWAREBAZAAR_AUTH_KEY not set — MalwareBazaar lookups will be SKIPPED. "
            "Get a free key at https://auth.abuse.ch/ and set MALWAREBAZAAR_AUTH_KEY."
        )

    conn = get_conn()
    try:
        candidates = fetch_certstream_new_candidates(conn, limit)
        logger.info("Fetched %d certstream candidates to enrich", len(candidates))

        if not candidates:
            logger.info("Nothing to enrich. Exiting.")
            return

        confirmed_bad   = 0
        confirmed_clean = 0
        errors          = 0
        api_calls       = 0

        for cand in candidates:
            domain       = cand["domain"]
            cand_id      = cand["id"]
            campaign_id  = cand["campaign_id"]

            logger.info("  Enriching: %s (id=%d)", domain, cand_id)

            # --- URLhaus lookup ---
            urlhaus_raw = lookup_urlhaus(domain)
            api_calls += 1
            time.sleep(REQUEST_DELAY_SECONDS)

            # --- MalwareBazaar lookup ---
            mb_raw = lookup_malwarebazaar(domain)
            api_calls += 1
            time.sleep(REQUEST_DELAY_SECONDS)

            if urlhaus_raw is None and mb_raw is None:
                logger.warning("    Both lookups failed for %s — skipping", domain)
                errors += 1
                continue

            # Parse results
            urlhaus_info = parse_urlhaus_result(urlhaus_raw) if urlhaus_raw else {"urlhaus_known": False, "error": "lookup_failed"}
            mb_info      = parse_malwarebazaar_result(mb_raw)  if mb_raw      else {"malwarebazaar_known": False, "error": "lookup_failed"}

            threat_confirmed = urlhaus_info.get("urlhaus_known", False) or mb_info.get("malwarebazaar_known", False)
            enrichment = {**urlhaus_info, **mb_info}

            if threat_confirmed:
                confirmed_bad += 1
                families = mb_info.get("malwarebazaar_families") or []
                logger.info(
                    "    ⚠ THREAT CONFIRMED: %s | URLhaus=%s | MalwareBazaar=%s | families=%s",
                    domain,
                    urlhaus_info.get("urlhaus_known"),
                    mb_info.get("malwarebazaar_known"),
                    families,
                )
            else:
                confirmed_clean += 1
                logger.info("    ✓ Clean/unknown: %s", domain)

            update_candidate_enrichment(
                conn, cand_id, threat_confirmed, enrichment, dry_run=dry_run
            )

        if not dry_run:
            # Log API usage
            if candidates:
                log_api_call(
                    conn,
                    campaign_id=candidates[0]["campaign_id"],
                    stage="enrichment",
                    provider="urlhaus+malwarebazaar",
                    query_count=api_calls,
                )
            conn.commit()

        logger.info(
            "CertStream enricher finished. "
            "Processed=%d | Threat confirmed=%d | Clean/unknown=%d | Errors=%d | API calls=%d",
            len(candidates), confirmed_bad, confirmed_clean, errors, api_calls,
        )

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Passively enrich CertStream candidates via URLhaus + MalwareBazaar lookups."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run lookups without writing results to the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Maximum number of candidates to process per run (default: {DEFAULT_LIMIT}).",
    )
    args = parser.parse_args()
    run_enrichment(dry_run=args.dry_run, limit=args.limit)
