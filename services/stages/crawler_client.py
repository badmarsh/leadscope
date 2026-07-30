"""
crawler_client.py — Shared Crawl4AI scraper client for the stages service.

Extracted from stage5.py to provide a clean, shared interface for crawling web pages
without circular module dependencies between stage5 and kb_ingest.
"""
import logging
import requests
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import services.common.config as config

logger = logging.getLogger(__name__)

CONTACT_PATHS = ["/kapcsolat", "/kontakt", "/contact", "/o-nas", "/impressum", "/about", "/kontakty", "/about-us", "/o-firme"]

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
    retry=retry_if_exception_type(Exception),
    retry_error_callback=lambda retry_state: (None, None),
    reraise=False
)
def crawler_scrape(url: str, force_playwright: bool = False, bypass_cache: bool = False) -> tuple[Optional[str], Optional[list]]:
    """
    Call self-hosted Crawl4AI service to scrape a URL.
    Returns (markdown_text, images_list) or (None, None) on failure.
    Images is a list of strings (image URLs).
    Uses tenacity retry on network failure and returns (None, None) gracefully if all retries fail.
    """
    endpoint = f"{config.CRAWLER_ENDPOINT.rstrip('/')}/crawl"
    try:
        resp = requests.post(
            endpoint,
            json={
                "url": url,
                "bypass_cache": bypass_cache,
                "force_playwright": force_playwright,
                "timeout_ms": 60000,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            logger.warning("Crawler returned failure for %s: %s", url, data.get("error"))
            return None, None

        md = data.get("markdown") or ""
        media = data.get("media") or {}
        images = [
            img.get("src") for img in (media.get("images") or [])
            if img.get("src") and img.get("src", "").startswith("http")
        ]
        return md or None, images or None
    except Exception as exc:
        logger.warning("Crawler service attempt failed for %s: %s", url, exc)
        raise exc
