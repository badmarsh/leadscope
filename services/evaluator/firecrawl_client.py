"""
firecrawl_client.py — Shared Firecrawl scraping helpers for the evaluator.
"""
import logging
import re
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


def scrape_url(url: str, timeout: int = 30) -> Optional[str]:
    """
    Scrape a URL via Firecrawl and return markdown text.
    Returns None on failure.
    """
    endpoint = f"{config.FIRECRAWL_ENDPOINT.rstrip('/')}/v1/scrape"
    try:
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": ["markdown"]},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("markdown") or data.get("markdown")
    except Exception as exc:
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return None


def scrape_domain_pages(domain: str, paths: list[str] | None = None) -> dict[str, str]:
    """
    Scrape multiple pages from a domain.
    Returns {url: markdown_text} for pages that succeeded.
    """
    if paths is None:
        paths = ["", "/products", "/catalogue", "/about", "/kapcsolat", "/termekek"]

    results = {}
    base = f"https://{domain}"
    for i, path in enumerate(paths):
        url = base + path
        text = scrape_url(url)
        if text:
            results[url] = text
        elif i == 0:
            # Early exit: if the first scrape (homepage) fails, 
            # don't waste time on subpaths since the domain is likely down.
            logger.warning("Firecrawl failed on homepage %s. Aborting subpaths to save time.", url)
            break
    return results


def extract_image_urls(markdown: str) -> list[str]:
    """Extract image URLs from markdown text (![alt](url) pattern)."""
    pattern = r'!\[.*?\]\((https?://[^\s\)]+)\)'
    urls = re.findall(pattern, markdown)
    # Also grab raw image URLs in img tags
    img_pattern = r'<img[^>]+src=["\']?(https?://[^\s"\']+)["\']?'
    urls.extend(re.findall(img_pattern, markdown))
    # Deduplicate, fix Shopify templates, and filter out tracking pixels
    seen = set()
    unique = []
    
    # Common tracking domains/patterns to ignore
    ignore_patterns = ["bat.bing.com", "google-analytics.com", "facebook.com/tr", "pixel", "tracker"]

    for u in urls:
        # Fix Shopify responsive image templates
        u = u.replace("%7Bwidth%7D", "800").replace("{width}", "800")
        
        # Check if URL contains any ignore patterns
        is_tracking = any(pattern in u.lower() for pattern in ignore_patterns)
        
        if u not in seen and u.startswith("http") and not is_tracking:
            seen.add(u)
            unique.append(u)
    return unique
