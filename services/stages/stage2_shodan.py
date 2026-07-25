"""
stage2_shodan.py — Shodan Target Finder for WordPress vulnerabilities
"""
import logging
import time
import requests

import services.common.config as config
import db
from stage2 import _upsert_candidate, _extract_domain

logger = logging.getLogger(__name__)

def _search_shodan_cve(cve: str) -> list[str]:
    if not config.SHODAN_API_KEY:
        logger.warning("SHODAN_API_KEY not set. Cannot run Shodan target finder.")
        return []

    url = "https://api.shodan.io/shodan/host/search"
    query = f'http.component:"wordpress" vuln:"{cve}"'
    params = {
        "key": config.SHODAN_API_KEY,
        "query": query
    }
    
    domains = []
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        matches = data.get("matches", [])
        for match in matches:
            hostnames = match.get("hostnames", [])
            if hostnames:
                for h in hostnames:
                    clean = _extract_domain(h)
                    if clean:
                        domains.append(clean)
    except Exception as exc:
        logger.error(f"Shodan search failed for {cve}: {exc}")
    
    return list(set(domains))

def run_shodan_discovery(campaign_id: int):
    cves = ["CVE-2024-4439", "CVE-2024-9047"]
    total_injected = 0
    with db.get_conn() as conn:
        for cve in cves:
            logger.info(f"Searching Shodan for {cve}")
            domains = _search_shodan_cve(cve)
            inserted_count = 0
            for domain in domains:
                inserted = _upsert_candidate(
                    conn,
                    campaign_id=campaign_id,
                    domain=domain,
                    company_name="",
                    source="shodan",
                    query_used=cve,
                    evidence_data={"shodan_vuln": cve}
                )
                if inserted:
                    inserted_count += 1
            logger.info(f"Injected {inserted_count} new candidates for {cve}")
            total_injected += inserted_count
            time.sleep(1)
            
    logger.info(f"Shodan discovery completed. Total injected: {total_injected}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with db.get_conn() as conn:
        campaign = db.fetchone(conn, "SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
        if campaign:
            run_shodan_discovery(campaign["id"])
        else:
            logger.error("wp-remediation campaign not found")
