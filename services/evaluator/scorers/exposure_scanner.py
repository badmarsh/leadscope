"""
scorers/exposure_scanner.py — Zero-Day Exposure Engine for Phase X.

Performs passive, WAF-safe checks on known dangerous exposed files.
This is strictly read-only and uses legitimate browser-like User-Agents.
Returns evidence to feed into the Shadow Audit dashboard and the Compound Lead Score.
"""
import logging
import random
import concurrent.futures
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

def _check_vector(session, base_url, vector_name, vector_data):
    """Check a single exposure vector. Returns finding dict or None."""
    for path in vector_data["paths"]:
        target_url = f"{base_url.rstrip('/')}{path}"
        try:
            head_resp = session.head(target_url, timeout=4, allow_redirects=False)
            if head_resp.status_code == 200:
                get_resp = session.get(target_url, timeout=4, allow_redirects=False)
                if get_resp.status_code == 200:
                    content = get_resp.text
                    for marker in vector_data["critical_markers"]:
                        if marker in content:
                            return {
                                "type": vector_name,
                                "url": target_url,
                                "severity": vector_data["severity"],
                                "snippet": content[:300] + "...",
                            }
        except requests.RequestException:
            continue
    return None

def scan_exposures(domain: str) -> dict:
    base_url = f"https://{domain}" if not domain.startswith("http") else domain
    results = {"critical_found": False, "high_found": False, "exposures": []}

    session = requests.Session()
    session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_check_vector, session, base_url, name, data): name
            for name, data in EXPOSURE_VECTORS.items()
        }
        for future in concurrent.futures.as_completed(futures, timeout=15):
            finding = future.result()
            if finding:
                if finding["severity"] == "critical":
                    results["critical_found"] = True
                elif finding["severity"] == "high":
                    results["high_found"] = True
                results["exposures"].append(finding)

    return results
