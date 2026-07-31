"""
stage4.py — Contact Discovery.

Iterates over candidates that are 'evaluated', 'pending_review', or 'approved'
and attempts to discover contacts (email, name, role) via:
  1. Apollo.io (person-level, job titles, LinkedIn URLs)  — if APOLLO_API_KEY set
  2. Hunter.io domain-search
  3. python-whois
  4. Crawl4AI fallback

All discovered emails are verified via Hunter.io /v2/email-verifier when
HUNTER_VERIFY_CONTACTS=true (default).  The mx_valid flag is stored on the
contact row so outreach can filter unverified addresses.

Decision-maker roles (CEO, Owner, Director, Facilities Manager) are ranked
above generic info@ / admin@ addresses so Stage 5 can address them by name.
"""
import logging
import concurrent.futures
import re
from typing import Any
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import requests
import whois
import json

import db
import services.common.config as config
from crawler_client import crawler_scrape, CONTACT_PATHS

logger = logging.getLogger(__name__)

# ── Role priority for sorting contacts ─────────────────────────────────────
_DECISION_MAKER_TITLES = [
    "ceo", "chief executive", "owner", "founder", "co-founder",
    "director", "managing director", "general manager", "president",
    "vp", "vice president", "head of", "facilities manager",
    "operations manager", "purchasing manager", "procurement",
]
_GENERIC_PREFIXES = ["info", "admin", "contact", "hello", "mail", "sales", "support", "office"]


def _role_priority(contact: dict) -> int:
    """Lower = higher priority. 0 = confirmed decision maker."""
    role = (contact.get("role") or "").lower()
    email_local = (contact.get("email") or "").split("@")[0].lower()
    if any(t in role for t in _DECISION_MAKER_TITLES):
        return 0
    if any(email_local == p for p in _GENERIC_PREFIXES):
        return 20
    return 10


def _prioritize_contacts(contacts: list[dict]) -> list[dict]:
    """Sort contacts: decision-makers first, then named emails, then generic."""
    return sorted(contacts, key=_role_priority)


# ── Apollo.io ───────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
def _apollo_search(domain: str, candidate: dict = None) -> list[dict]:
    """Search Apollo.io People Search API for contacts at this domain."""
    if not config.APOLLO_API_KEY:
        return []
    try:
        url = "https://api.apollo.io/v1/mixed_people/search"
        target_roles = [
            "CEO", "Owner", "Founder", "Director", "Managing Director",
            "Facilities Manager", "Operations Manager", "Purchasing Manager",
        ]
        if candidate and candidate.get("campaign_config"):
            try:
                cfg = json.loads(candidate.get("campaign_config", "{}"))
                if "target_roles" in cfg:
                    target_roles = cfg["target_roles"]
            except Exception:
                pass

        payload = {
            "api_key": config.APOLLO_API_KEY,
            "q_organization_domains": domain,
            "page": 1,
            "per_page": 10,
            "person_titles": target_roles,
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        contacts = []
        for person in people:
            email = person.get("email")
            if not email:
                continue
            name = " ".join(filter(None, [person.get("first_name"), person.get("last_name")]))
            contacts.append({
                "email": email,
                "name": name or None,
                "role": person.get("title"),
                "linkedin_url": person.get("linkedin_url"),
                "confidence": 85,
                "source": "apollo",
            })
        return contacts
    except Exception as exc:
        logger.warning("Apollo API failed for %s: %s", domain, exc)
        return []


# ── Hunter.io domain search ─────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
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
                "source": "hunter",
            })
        return contacts
    except Exception as exc:
        logger.warning("Hunter API failed for %s: %s", domain, exc)
        return []


# ── Hunter.io email verifier ────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
def _hunter_verify(email: str) -> bool | None:
    """
    Call Hunter /v2/email-verifier.  Returns:
      True   — deliverable / valid MX
      False  — invalid / disposable
      None   — API unavailable or key not set
    """
    if not config.HUNTER_API_KEY or not getattr(config, "HUNTER_VERIFY_CONTACTS", True):
        return None
    try:
        url = f"https://api.hunter.io/v2/email-verifier?email={email}&api_key={config.HUNTER_API_KEY}"
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "")
        # Hunter statuses: deliverable, risky, undeliverable, unknown
        if status == "deliverable" or status == "accept_all" or status == "valid":
            return True
        if status in ("undeliverable", "disposable"):
            return False
        return None  # risky / unknown — don't mark invalid
    except Exception as exc:
        logger.debug("Hunter verify failed for %s: %s", email, exc)
        return None


# ── Whois fallback ──────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5), retry=retry_if_exception_type(Exception), reraise=False)
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
                    "source": "whois",
                })
        return contacts
    except Exception as exc:
        logger.debug("Whois failed for %s: %s", domain, exc)
        return []


# ── Crawl4AI fallback ───────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5), retry=retry_if_exception_type(Exception), reraise=False)
def _crawler_search(domain: str) -> list[dict]:
    base_url = f"https://{domain}"
    all_emails = set()
    for path in CONTACT_PATHS[:3]:
        text, _ = crawler_scrape(f"{base_url}{path}")
        if text:
            found = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
            for e in found:
                if not any(e.lower().startswith(x) for x in ['support@', 'noreply@', 'privacy@', 'info@', 'admin@', 'hello@', 'contact@', 'sales@']):
                    all_emails.add(e)
    contacts = []
    for email in all_emails:
        contacts.append({
            "email": email,
            "name": None,
            "role": "scraped",
            "confidence": 20,
            "source": "crawler",
        })
    return contacts


# ── Core discovery + upsert ─────────────────────────────────────────────────

async def _async_discover(domain: str, candidate: dict = None) -> list[dict]:
    # Run all 4 searches in parallel with strict timeouts (e.g. 15s)
    tasks = [
        asyncio.wait_for(asyncio.to_thread(_apollo_search, domain, candidate), timeout=15),
        asyncio.wait_for(asyncio.to_thread(_hunter_search, domain), timeout=15),
        asyncio.wait_for(asyncio.to_thread(_whois_search, domain), timeout=15),
        asyncio.wait_for(asyncio.to_thread(_crawler_search, domain), timeout=15)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    contacts = []
    for res in results:
        if isinstance(res, list):
            contacts.extend(res)
        elif isinstance(res, Exception):
            logger.debug(f"Discovery task failed for {domain}: {res}")
            
    # Remove exact duplicate emails (case insensitive)
    seen = set()
    deduped = []
    for c in contacts:
        email = c.get("email", "").lower()
        if email and email not in seen:
            seen.add(email)
            deduped.append(c)
            
    return deduped

def _discover_contacts(candidate: dict, conn) -> dict:
    domain = candidate["domain"]
    candidate_id = candidate["id"]

    try:
        contacts = asyncio.run(_async_discover(domain, candidate))
    except Exception as exc:
        logger.error(f"Async discover failed for {domain}: {exc}")
        contacts = []
    
    contacts = _prioritize_contacts(contacts)
    
    inserted = 0
    for c in contacts:
        mx_valid = _hunter_verify(c["email"])
        linkedin_url = c.get("linkedin_url")
        try:
            db.execute(
                conn,
                """
                INSERT INTO contacts (candidate_id, email, name, role, confidence, source, mx_valid, linkedin_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id, email) DO UPDATE SET 
                    mx_valid = COALESCE(EXCLUDED.mx_valid, contacts.mx_valid),
                    linkedin_url = COALESCE(EXCLUDED.linkedin_url, contacts.linkedin_url),
                    role = EXCLUDED.role, 
                    confidence = EXCLUDED.confidence
                """,
                (candidate_id, c["email"], c["name"], c["role"], c.get("confidence", 0), c["source"], mx_valid, linkedin_url)
            )
            inserted += 1
        except Exception as exc:
            logger.error("Failed to insert contact for %s: %s", domain, exc)

    return {"candidate_id": candidate_id, "contacts_found": inserted}


def run() -> dict:
    with db.get_conn() as conn:
        approved = db.fetchall(
            conn,
            """
            SELECT c.id, c.campaign_id, c.domain
            FROM candidates c
            WHERE c.status IN ('evaluated', 'enriched', 'pending_review', 'approved')
            """,
        )

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for candidate in approved:
            def _worker(cand):
                with db.get_conn() as conn:
                    return _discover_contacts(cand, conn)
            futures.append(executor.submit(_worker, candidate))
        
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                logger.error("Stage 4 thread error: %s", exc)

    summary = {
        "total": len(results),
        "total_contacts_found": sum(r.get("contacts_found", 0) for r in results),
    }
    logger.info("Stage 4 run complete: %s", summary)
    return summary


if __name__ == "__main__":
    run()
