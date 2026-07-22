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


def extract_image_urls(markdown: str, evaluator_type: str = "content_relevance") -> list[str]:
    """Extract image URLs from markdown text and prioritize them based on campaign type."""
    pattern = r'!\[.*?\]\((https?://[^\s\)]+)\)'
    urls = re.findall(pattern, markdown)
    # Also grab raw image URLs in img tags
    img_pattern = r'<img[^>]+src=["\']?(https?://[^\s"\']+)["\']?'
    urls.extend(re.findall(img_pattern, markdown))
    
    seen = set()
    valid_urls = []
    
    # Common tracking domains/patterns to completely ignore
    ignore_patterns = [
        "bat.bing.com", "google-analytics.com", "facebook.com", "twitter.com", "instagram.com", 
        "x.com", "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
        "pixel", "tracker", ".svg", "logo", "icon", "spinner", "loader", "social",
        "badge", "trust", "support", "shipping", "payment", "secure", "guarantee", "return"
    ]

    for u in urls:
        u = u.replace("%7Bwidth%7D", "800").replace("{width}", "800")
        is_tracking = any(pattern in u.lower() for pattern in ignore_patterns)
        if u not in seen and u.startswith("http") and not is_tracking:
            seen.add(u)
            valid_urls.append(u)

    def score_url(url: str) -> int:
        u = url.lower()
        score = 0
        
        # Penalize layout/generic images heavily
        if any(w in u for w in ["banner", "hero", "footer", "header", "bg", "background", "menu"]):
            score -= 50
            
        if evaluator_type == "image_quality":
            # Boutique: prioritize shoes, products, shop, items
            if any(w in u for w in ["product", "item", "shoe", "sneaker", "boot", "shop", "catalog"]):
                score += 100
            if "interior" in u or "storefront" in u or "store" in u:
                score -= 20
        else:
            # Jenex: prioritize HVAC, products, portfolios, catalog covers
            if any(w in u for w in ["product", "catalog", "katalog", "portfolio", "cover", "hvac", "duct", "szellozes", "legtechnika", "item"]):
                score += 100
                
        return score

    # Sort URLs descending by heuristic score
    valid_urls.sort(key=score_url, reverse=True)
    return valid_urls


def detect_tech_stack(pages_dict: dict[str, str]) -> list[str]:
    """Detect e-commerce platforms or tech stack footprints from scraped text."""
    stack = set()
    signatures = {
        "Shopify": ["powered by shopify", "cdn.shopify.com"],
        "WooCommerce": ["woocommerce", "wp-content/plugins/woocommerce"],
        "Shoptet": ["shoptet", "powered by shoptet"],
        "PrestaShop": ["prestashop"],
        "Magento": ["magento"],
        "Wix": ["wix.com", "powered by wix"]
    }
    
    for text in pages_dict.values():
        text_lower = text.lower()
        for platform, footprints in signatures.items():
            if any(f in text_lower for f in footprints):
                stack.add(platform)
                
    return list(stack)
