"""
scorers/exposure_scanner.py — Zero-Day Exposure Engine for Phase X.

Performs passive, WAF-safe checks on known dangerous exposed files.
This is strictly read-only and uses legitimate browser-like User-Agents.
Returns evidence to feed into the Shadow Audit dashboard and the Compound Lead Score.
"""
import logging
import random
import time
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Real, common User-Agents to avoid WAF flags
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
]

EXPOSURE_VECTORS = {
    ".env": {
        "paths": ["/.env", "/.env.production"],
        "critical_markers": ["DB_PASSWORD=", "SECRET_KEY=", "APP_KEY="],
        "severity": "critical"
    },
    "git_config": {
        "paths": ["/.git/config"],
        "critical_markers": ["[core]"],
        "severity": "critical"
    },
    "wp_config_bak": {
        "paths": ["/wp-config.php.bak", "/wp-config.bak"],
        "critical_markers": ["DB_NAME", "define("],
        "severity": "critical"
    },
    "debug_log": {
        "paths": ["/wp-content/debug.log"],
        "critical_markers": ["PHP Fatal error", "/var/www"],
        "severity": "high"
    },
    "xmlrpc": {
        "paths": ["/xmlrpc.php"],
        "critical_markers": ["XML-RPC server accepts POST requests only."],
        "severity": "medium",
        "method": "GET" # A simple GET to xmlrpc.php returns this string if enabled
    },
    "database_dump": {
        "paths": ["/database.sql", "/backup.sql", "/db.sql"],
        "critical_markers": ["-- MySQL dump", "INSERT INTO", "CREATE TABLE"],
        "severity": "critical"
    },
    "wp_config_swp": {
        "paths": ["/.wp-config.php.swp"],
        "critical_markers": ["DB_NAME", "DB_PASSWORD"],
        "severity": "critical"
    }
}

def scan_exposures(domain: str) -> dict:
    """
    Performs serial, rate-limited passive checks for zero-day exposures.
    """
    if not domain.startswith("http"):
        base_url = f"https://{domain}"
    else:
        base_url = domain
        domain = urlparse(base_url).netloc
        
    results = {
        "critical_found": False,
        "high_found": False,
        "exposures": []
    }
    
    session = requests.Session()
    session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
    
    for vector_name, vector_data in EXPOSURE_VECTORS.items():
        for path in vector_data["paths"]:
            target_url = f"{base_url.rstrip('/')}{path}"
            try:
                # WAF Evasion: Small randomized delay
                time.sleep(random.uniform(0.3, 1.2))
                
                # WAF Evasion: HEAD first
                head_resp = session.head(target_url, timeout=5, allow_redirects=False)
                if head_resp.status_code == 200:
                    # If it exists, GET it
                    get_resp = session.get(target_url, timeout=5, allow_redirects=False)
                    if get_resp.status_code == 200:
                        content = get_resp.text
                        for marker in vector_data["critical_markers"]:
                            if marker in content:
                                severity = vector_data["severity"]
                                if severity == "critical":
                                    results["critical_found"] = True
                                elif severity == "high":
                                    results["high_found"] = True
                                    
                                results["exposures"].append({
                                    "type": vector_name,
                                    "url": target_url,
                                    "severity": severity,
                                    "snippet": content[:300] + "..." # Truncate for legal safety
                                })
                                break # Found a marker, move to next vector
                                
            except requests.RequestException as e:
                logger.debug(f"Exposure scan failed for {target_url}: {e}")
                
    return results
