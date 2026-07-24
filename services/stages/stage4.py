"""
stage4.py — Contact Discovery.

Iterates over candidates that are 'evaluated', 'pending_review', or 'approved'
and attempts to discover contacts (email, name, role) via Hunter.io,
python-whois, and Crawl4AI fallback.
Saves contacts into the `contacts` table.
"""
import logging
import concurrent.futures
from typing import Any

import requests
import whois

import db
import config
from crawler_client import crawler_scrape, CONTACT_PATHS

logger = logging.getLogger(__name__)

def _hunter_search(domain: str) -> list[dict]:
    if not config.HUNTER_API_KEY:
        return []
    try:
        url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={config.HUNTER_API_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = data.get("emails", [])
        contacts = []
        for e in emails:
            contacts.append({
                "email": e.get("value"),
                "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() or None,
                "role": e.get("position"),
                "confidence": e.get("confidence", 0),
                "source": "hunter"
            })
        return contacts
    except Exception as exc:
        logger.warning(f"Hunter API failed for {domain}: {exc}")
        return []

def _whois_search(domain: str) -> list[dict]:
    try:
        w = whois.whois(domain)
        emails = w.emails
        if not emails:
            return []
        if isinstance(emails, str):
            emails = [emails]
        contacts = []
        for email in set(emails):
            if "abuse" not in email.lower():
                contacts.append({
                    "email": email,
                    "name": w.name if isinstance(w.name, str) else None,
                    "role": "whois_contact",
                    "confidence": 40,
                    "source": "whois"
                })
        return contacts
    except Exception as exc:
        logger.debug(f"Whois failed for {domain}: {exc}")
        return []

def _crawler_search(domain: str) -> list[dict]:
    import re
    base_url = f"https://{domain}"
    all_emails = set()
    for path in CONTACT_PATHS[:3]: # check first 3 paths
        text, _ = crawler_scrape(f"{base_url}{path}")
        if text:
            found = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
            all_emails.update(found)
    contacts = []
    for email in all_emails:
        contacts.append({
            "email": email,
            "name": None,
            "role": "scraped",
            "confidence": 20,
            "source": "crawler"
        })
    return contacts

def _discover_contacts(candidate: dict, conn) -> dict:
    domain = candidate["domain"]
    candidate_id = candidate["id"]
    contacts = _hunter_search(domain)
    if not contacts:
        contacts = _whois_search(domain)
    if not contacts:
        contacts = _crawler_search(domain)
    
    inserted = 0
    for c in contacts:
        try:
            db.execute(
                conn,
                """
                INSERT INTO contacts (candidate_id, email, name, role, confidence, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id, email) DO NOTHING
                """,
                (candidate_id, c["email"], c["name"], c["role"], c["confidence"], c["source"])
            )
            inserted += 1
        except Exception as exc:
            logger.error(f"Failed to insert contact for {domain}: {exc}")
    
    return {"candidate_id": candidate_id, "contacts_found": inserted}

def run() -> dict:
    with db.get_conn() as conn:
        approved = db.fetchall(
            conn,
            """
            SELECT c.id, c.campaign_id, c.domain
            FROM candidates c
            WHERE c.status IN ('evaluated', 'pending_review', 'approved')
            """
        )
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for candidate in approved:
            futures.append(executor.submit(
                lambda cand: _discover_contacts(cand, db.get_conn()), candidate
            ))
        
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            results.append(res)
    
    summary = {
        "total": len(results),
        "total_contacts_found": sum(r.get("contacts_found", 0) for r in results)
    }
    logger.info("Stage 4 run complete: %s", summary)
    return summary

if __name__ == "__main__":
    run()
