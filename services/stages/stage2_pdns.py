"""
stage2_pdns.py — Phase 3: Passive DNS (pDNS) Tracking.

Queries VirusTotal for domains known to be compromised (status='approved'),
finds their IP addresses (A records), and then looks up other domains
resolving to those exact same IPs to discover related infrastructure.
"""
import json
import logging
import time
from typing import List

import requests

import services.common.config as config
import db
from stage2 import _upsert_candidate, _extract_domain, _is_out_of_scope_domain

logger = logging.getLogger(__name__)

VT_API_URL = "https://www.virustotal.com/api/v3"

def _vt_get_domain_resolutions(domain: str) -> List[str]:
    """Get recent IP addresses for a domain."""
    if not config.VIRUSTOTAL_API_KEY:
        logger.warning("VIRUSTOTAL_API_KEY not set.")
        return []

    headers = {"x-apikey": config.VIRUSTOTAL_API_KEY}
    url = f"{VT_API_URL}/domains/{domain}/resolutions"
    
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        ips = []
        for item in data.get("data", []):
            attr = item.get("attributes", {})
            ip = attr.get("ip_address")
            if ip and ip not in ips:
                ips.append(ip)
        return ips
    except Exception as exc:
        logger.error(f"VT domain resolution failed for {domain}: {exc}")
        return []

def _vt_get_ip_resolutions(ip: str) -> List[str]:
    """Get domains resolving to an IP address."""
    headers = {"x-apikey": config.VIRUSTOTAL_API_KEY}
    url = f"{VT_API_URL}/ip_addresses/{ip}/resolutions"
    
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        domains = []
        for item in data.get("data", []):
            attr = item.get("attributes", {})
            host = attr.get("host_name")
            if host:
                domains.append(host)
        return domains
    except Exception as exc:
        logger.error(f"VT IP resolution failed for {ip}: {exc}")
        return []

def run_pdns_analysis(campaign_id: int):
    """
    Finds 'approved' domains, resolves them to IPs, and pivots to find co-hosted domains.
    """
    with db.get_conn() as conn:
        approved_domains = db.fetchall(
            conn,
            """
            SELECT domain FROM candidates
            WHERE campaign_id = %s AND status = 'approved'
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (campaign_id,)
        )
        
        if not approved_domains:
            logger.info("No approved domains found. Skipping pDNS analysis.")
            return

        total_injected = 0
        for row in approved_domains:
            target = row["domain"]
            logger.info(f"Resolving IPs for known compromised domain: {target}")
            
            ips = _vt_get_domain_resolutions(target)
            if not ips:
                continue
                
            for ip in ips:
                logger.info(f"Pivoting on IP {ip} (from {target})")
                co_hosted_domains = _vt_get_ip_resolutions(ip)
                
                inserted_count = 0
                for co_host in co_hosted_domains:
                    clean = _extract_domain(co_host)
                    if not clean or clean == target or _is_out_of_scope_domain(clean):
                        continue
                        
                    inserted = _upsert_candidate(
                        conn,
                        campaign_id=campaign_id,
                        domain=clean,
                        company_name="",
                        source="vt_pdns",
                        query_used=f"pdns:{ip}",
                        evidence_data={"found_via_pdns_ip": ip, "original_target": target}
                    )
                    if inserted:
                        inserted_count += 1
                
                logger.info(f"Injected {inserted_count} new domains from IP {ip}")
                total_injected += inserted_count
                time.sleep(2)  # VT rate limit (4 req/min on standard free tier, play safe)
            
            time.sleep(2)

        logger.info(f"pDNS Tracking completed. Total injected: {total_injected}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with db.get_conn() as conn:
        campaign = db.fetchone(conn, "SELECT id FROM campaigns WHERE slug = 'wp-remediation'")
        if campaign:
            run_pdns_analysis(campaign["id"])
        else:
            logger.error("wp-remediation campaign not found")
