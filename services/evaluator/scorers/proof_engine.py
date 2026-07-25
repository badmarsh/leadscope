"""
scorers/proof_engine.py — The Undeniable Proof Engine for Phase X.

Generates hard evidence of malware infection by exploiting the "sneakiness"
of the malware. Provides undeniable proof like Google SERP spam screenshots
or spoofed mobile redirect traces.
"""
import logging
import os
import requests
from typing import Optional
from urllib.parse import urlparse
import services.common.config as config

_SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

logger = logging.getLogger(__name__)

# Typical SEO Spam Keywords to check via Google Dorks
SEO_SPAM_KEYWORDS = ["casino", "viagra", "cialis", "payday loans", "slot", "betting"]

def confirm_google_serp_spam(domain: str) -> Optional[dict]:
    """
    Checks if Google has indexed SEO spam on the given domain using Serper (Google Search API).
    Uses advanced dork: site:domain.com "casino" OR "viagra" OR ...
    """
    if not _SERPER_API_KEY:
        logger.debug("SERPER_API_KEY not set — skipping SERP spam check for %s", domain)
        return None

    netloc = urlparse(domain).netloc if domain.startswith('http') else domain

    # Google dork: site:example.com "casino" OR "viagra" ...
    spam_terms = " OR ".join(f'"{kw}"' for kw in SEO_SPAM_KEYWORDS)
    query = f"site:{netloc} ({spam_terms})"

    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": _SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": 10},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("organic", [])

        # Keep only results that are actually on the target domain
        spam_results = [r for r in results if netloc in r.get("link", "")]

        if spam_results:
            first = spam_results[0]
            return {
                "proof_type": "google_serp_spam",
                "indexed_spam_pages": len(spam_results),
                "example_url": first.get("link"),
                "example_title": first.get("title"),
                "example_snippet": first.get("snippet"),
                "evidence_text": (
                    f"Google has indexed {len(spam_results)} spam page(s) on your domain "
                    f"(e.g., '{first.get('title')}')."
                ),
            }
    except Exception as e:
        logger.warning("Failed to check SERP spam for %s: %s", domain, e)

    return None


def trigger_cloaked_redirect(domain: str) -> Optional[dict]:
    """
    Attempts to trigger mobile/referer cloaked malware by spoofing
    the User-Agent (iPhone) and Referer (Google).
    Records the redirect chain if the site maliciously redirects us.
    """
    url = domain if domain.startswith("http") else f"https://{domain}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Referer": "https://www.google.com/",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    try:
        # Allow redirects to trace the path
        resp = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
        
        final_url = resp.url
        final_netloc = urlparse(final_url).netloc
        original_netloc = urlparse(url).netloc
        
        # If we ended up on a completely different domain (not just www / non-www)
        if final_netloc.replace('www.', '') != original_netloc.replace('www.', ''):
            # We got redirected!
            chain = [r.url for r in resp.history] + [final_url]
            
            return {
                "proof_type": "cloaked_redirect",
                "redirect_destination": final_url,
                "evidence_text": f"Visitors arriving from Google on mobile devices are being silently redirected to {final_netloc}.",
                "network_trace": chain
            }
    except requests.RequestException as e:
        logger.debug(f"Spoofed redirect check failed/timed out for {domain}: {e}")
        
    return None

def check_wp_admin_exposure(domain: str) -> Optional[dict]:
    """
    Checks if /wp-admin/ or /wp-login.php is exposed and accessible,
    proving it's a WordPress site and potentially vulnerable to brute-force if combined with malware.
    """
    url = domain if domain.startswith("http") else f"https://{domain}"
    target = f"{url.rstrip('/')}/wp-login.php"
    
    try:
        resp = requests.get(target, timeout=10, allow_redirects=True)
        if resp.status_code == 200 and "user_login" in resp.text:
            return {
                "proof_type": "wp_admin_check",
                "exposed_url": target,
                "evidence_text": f"The WordPress login panel is publicly exposed at {target}."
            }
    except requests.RequestException as e:
        logger.debug(f"WP admin check failed for {domain}: {e}")
        
    return None


def check_malicious_file_scan(domain: str) -> Optional[dict]:
    """
    A generic check for exposed sensitive files or known malware dropper paths.
    """
    url = domain if domain.startswith("http") else f"https://{domain}"
    common_droppers = ["/wp-content/uploads/wp-config.php", "/wp-includes/css/wp-settings.php"]
    
    for path in common_droppers:
        target = f"{url.rstrip('/')}{path}"
        try:
            resp = requests.head(target, timeout=5, allow_redirects=False)
            if resp.status_code == 200:
                return {
                    "proof_type": "file_scan",
                    "exposed_file": target,
                    "evidence_text": f"A suspected malicious file was found exposed at {target}."
                }
        except requests.RequestException:
            continue
            
    return None

def generate_proof(domain: str, matched_signatures: list[dict]) -> Optional[dict]:
    """
    Determines which proof method to use based on the malware signatures.
    """
    # Check what proof methods are requested by the signatures
    proof_methods = {sig.get("proof_method") for sig in matched_signatures if sig.get("proof_method")}
    
    if "google_serp_check" in proof_methods or "google_serp_spam" in proof_methods:
        proof = confirm_google_serp_spam(domain)
        if proof: return proof
        
    if "spoof_mobile" in proof_methods:
        proof = trigger_cloaked_redirect(domain)
        if proof: return proof
        
    if "wp_admin_check" in proof_methods:
        proof = check_wp_admin_exposure(domain)
        if proof: return proof
        
    if "file_scan" in proof_methods:
        proof = check_malicious_file_scan(domain)
        if proof: return proof

    # Default fallbacks if the DB doesn't specify but we have sneakiness tier S/A/B
    tiers = {sig.get("sneakiness_tier", "C") for sig in matched_signatures}
    
    if "S" in tiers: # S = Cloaked Redirects
        proof = trigger_cloaked_redirect(domain)
        if proof: return proof
        
    if "A" in tiers: # A = DB/SEO Spam
        proof = confirm_google_serp_spam(domain)
        if proof: return proof
        
    if "B" in tiers: # B = Exposed admin or files
        proof = check_wp_admin_exposure(domain)
        if not proof:
            proof = check_malicious_file_scan(domain)
        if proof: return proof

    return None
