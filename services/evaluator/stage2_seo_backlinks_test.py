"""
stage2_seo_backlinks.py — Phase 2: SEO Backlink Analysis for Federated Discovery.

Takes known compromised domains (status='approved') from the wp-remediation campaign,
queries the Ahrefs API for referring domains (backlinks), and injects them as new
candidates. This helps discover the topology of Black-Hat SEO spam networks.
"""
import json
import logging
import time
from typing import Any

import requests

import config
import db
from stage2 import _upsert_candidate, _extract_domain

logger = logging.getLogger(__name__)

AHREFS_URL = "https://api.ahrefs.com/v3/site-explorer/referring-domains"

def _search_ahrefs_referring_domains(target_domain: str, limit: int = 100) -> list[str]:
    """
    Fetch referring domains using the Ahrefs v3 API.
    """
    if not config.AHREFS_API_KEY:
        logger.warning("AHREFS_API_KEY not set. Cannot run SEO backlink analysis.")
        return []

    headers = {
        "Authorization": f"Bearer {config.AHREFS_API_KEY}",
        "Accept": "application/json"
    }
    
    # We specify exact domain match to find domains linking to this compromised domain.
    params = {
        "target": target_domain,
        "mode": "subdomains",
        "limit": limit
    }

    try:
        resp = requests.get(AHREFS_URL, headers=headers, params=params, timeout=30)
        
        if resp.status_code == 401:
            logger.error("Ahrefs API unauthorized. Check API key.")
            return []
        if resp.status_code == 403:
            logger.error("Ahrefs API forbidden or quota exceeded.")
            return []
            
        resp.raise_for_status()
        data = resp.json()
        
        referring_domains = []
        # Ahrefs v3 response structure for referring-domains usually has 'referring_domains' array
        # where each object has a 'domain' field.
        # Format: {"referring_domains": [{"domain": "example.com", ...}]}
        if "referring_domains" in data:
            for item in data["referring_domains"]:
                domain = item.get("domain")
                if domain:
                    clean = _extract_domain(domain)
                    if clean:
                        referring_domains.append(clean)
        return referring_domains
    except Exception as exc:
        logger.error(f"Ahrefs API request failed for target {target_domain}: {exc}")
        return []


def run_seo_backlink_analysis(campaign_id: int):
    """
    1. Fetch all 'approved' candidates for the given campaign (known compromised).
    2. Pull referring domains via Ahrefs API.
    3. Upsert newly discovered domains as 'new' candidates.
    """
    with db.get_conn() as conn:
        approved_domains = db.fetchall(
            conn,
            """
            SELECT domain FROM candidates
            WHERE campaign_id = %s AND status = 'approved'
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (campaign_id,)
        )
        
        if not approved_domains:
            logger.info("No approved domains found for campaign %s. Skipping backlink analysis.", campaign_id)
            return

        logger.info("Running SEO Backlink Analysis for %d approved domains", len(approved_domains))

        total_injected = 0
        for row in approved_domains:
            target = row["domain"]
            logger.info(f"Fetching referring domains for {target}")
            
            ref_domains = _search_ahrefs_referring_domains(target, limit=100)
            
            inserted_count = 0
            for ref_domain in ref_domains:
                # Avoid injecting the target itself if it links to itself
                if ref_domain == target:
                    continue
                    
                inserted = _upsert_candidate(
                    conn,
                    campaign_id=campaign_id,
                    domain=ref_domain,
                    company_name="",
                    source="ahrefs_seo",
                    query_used=f"backlinks:{target}",
                    evidence_data={"found_via_backlink_from": target}
                )
                if inserted:
                    inserted_count += 1
            
            logger.info(f"Discovered and injected {inserted_count} new candidates from {target} backlinks")
            total_injected += inserted_count
            
            # Rate limit respect for Ahrefs (usually max 10 requests per second, but we play it safe)
            time.sleep(1)

        logger.info(f"SEO Backlink Analysis completed. Total injected: {total_injected}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # The wp-remediation campaign id is usually 3. Look it up dynamically.
    with db.get_conn() as conn:
        campaign = db.fetchone(conn, "SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
        if campaign:
            run_seo_backlink_analysis(campaign["id"])
        else:
            logger.error("wp-remediation campaign not found")
