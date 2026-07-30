"""
urlscan_scraper.py — Utility to fetch URLScan search results and extract domain names.
"""
from typing import List, Dict, Optional
import os
import requests
from urllib.parse import urlparse


def extract_domain(url: str) -> Optional[str]:
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    parsed = urlparse(url)
    netloc = parsed.netloc.split(":")[0]
    return netloc.lower() if netloc else None


def fetch_urlscan_results(query: str, size: int = 50) -> List[Dict]:
    api_key = os.environ.get("URLSCAN_API_KEY", "")
    headers = {"API-Key": api_key} if api_key else {}
    try:
        resp = requests.get(
            "https://urlscan.io/api/v1/search/",
            params={"q": query, "size": size},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return []
