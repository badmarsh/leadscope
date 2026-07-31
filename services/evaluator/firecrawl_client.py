"""
firecrawl_client.py — Shared Firecrawl scraping helpers for the evaluator.
"""
import logging
import re
from typing import Optional

import requests

import services.common.config as config

logger = logging.getLogger(__name__)


import time

def scrape_url(url: str, timeout: int = 30, include_html: bool = False) -> dict | str | None:
    """
    Scrape a URL via Firecrawl and return markdown text, or a dict if include_html=True.
    Uses Firecrawl's async batch/scrape API with a polling state machine to prevent connection drops.
    Returns None on failure.
    """
    endpoint = f"{config.FIRECRAWL_ENDPOINT.rstrip('/')}/v1/batch/scrape"
    formats = ["markdown", "html"] if include_html else ["markdown"]
    
    try:
        # 1. Submit async scrape
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"urls": [url], "formats": formats},
            timeout=10,
        )
        resp.raise_for_status()
        job_id = resp.json().get("id")
        
        if not job_id:
            logger.warning("Firecrawl returned no job ID for %s", url)
            return None

        # 2. Poll the status
        poll_endpoint = f"{config.FIRECRAWL_ENDPOINT.rstrip('/')}/v1/batch/scrape/{job_id}"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            time.sleep(2)  # Wait before polling
            poll_resp = requests.get(
                poll_endpoint,
                headers={"Authorization": f"Bearer {config.FIRECRAWL_API_KEY}"},
                timeout=10,
            )
            poll_resp.raise_for_status()
            data = poll_resp.json()
            status = data.get("status")
            
            if status == "completed":
                items = data.get("data", [])
                if not items:
                    return None
                result = items[0]
                md = result.get("markdown")
                if not include_html:
                    return md
                return {
                    "markdown": md,
                    "html": result.get("html", "")
                }
            elif status in ("failed", "error", "cancelled"):
                logger.warning("Firecrawl async scrape failed for %s: %s", url, data.get("error"))
                return None
                
        logger.warning("Firecrawl async scrape timed out for %s after %d seconds", url, timeout)
        return None
        
    except Exception as exc:
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return None


def map_url(url: str, timeout: int = 20) -> list[str]:
    """
    Call Firecrawl's /v1/map endpoint to instantly retrieve the sitemap.
    """
    endpoint = f"{config.FIRECRAWL_ENDPOINT.rstrip('/')}/v1/map"
    try:
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"url": url},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            return data.get("links", [])
    except Exception as exc:
        logger.warning("Firecrawl map failed for %s: %s", url, exc)
    return []


def _discover_product_paths(domain: str, max_paths: int = 4) -> list[str]:
    """
    HARDENING: Dynamically discover likely product/catalogue paths using
    Firecrawl's /map API to instantly get the sitemap.
    """
    from urllib.parse import urlparse
    import re

    PRODUCT_KEYWORDS = [
        "product", "products", "shop", "store", "catalogue", "catalog",
        "termek", "termekek", "aruhaz", "bolt", "kollekcio", "kategoria",
        "kategorie", "produkte", "sortiment", "tovarny", "obchod",
        "felhasznalas", "cikkek", "webshop", "eshop",
    ]
    UI_NOISE = [
        "login", "signin", "register", "account", "cart", "checkout",
        "contact", "kapcsolat", "impressum", "adatvedelem", "cookie",
        "privacy", "terms", "gdpr", "sitemap", "xml", "rss", "feed",
        "javascript:", "mailto:", "#", "tag", "blog", "author", "page"
    ]
    STATIC_FALLBACK = ["/products", "/shop", "/termekek", "/catalogue", "/kategoria"]

    try:
        base_url = f"https://{domain}"
        links = map_url(base_url)
        
        if not links:
            logger.info("Firecrawl map returned 0 links for %s, using static fallback", domain)
            return STATIC_FALLBACK

        scored: dict[str, int] = {}
        for link in links:
            parsed = urlparse(link)
            if parsed.netloc and parsed.netloc != domain and parsed.netloc != f"www.{domain}":
                continue
            
            href = parsed.path.rstrip("/") or "/"
            if len(href) < 2 or href in scored:
                continue

            href_lower = href.lower()
            if any(noise in href_lower for noise in UI_NOISE):
                continue

            score = 0
            for kw in PRODUCT_KEYWORDS:
                if kw in href_lower:
                    score += 10
            # Boost short paths (likely top-level categories)
            depth = href.count("/")
            score -= depth * 2

            if score > 0:
                scored[href] = score

        if not scored:
            return STATIC_FALLBACK

        top_paths = sorted(scored, key=lambda p: scored[p], reverse=True)[:max_paths]
        logger.info(
            "Map path discovery for %s found %d candidates, top: %s",
            domain, len(scored), top_paths,
        )
        return top_paths

    except Exception as exc:
        logger.warning("Map path discovery failed for %s: %s - using static fallback", domain, exc)
        return STATIC_FALLBACK


def scrape_domain_pages(domain: str, paths: list[str] | None = None, include_html: bool = False) -> dict:
    """
    Scrape multiple pages from a domain.
    If paths is None, dynamically discovers product/category links from the homepage.
    Returns {url: markdown_text} or {url: {"markdown": ..., "html": ...}} if include_html=True.
    """
    results = {}
    base = f"https://{domain}"

    if paths is None:
        discovered = _discover_product_paths(domain)
        paths = [""] + discovered  # HARDENING: dynamic discovery, homepage always first

    for i, path in enumerate(paths):
        url = base + path if path.startswith("/") else base + "/" + path if path else base
        res = scrape_url(url, include_html=include_html)
        if res:
            results[url] = res
        elif i == 0:
            logger.warning("Firecrawl failed on homepage %s. Aborting subpaths.", url)
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
        if any(w in u for w in ["banner", "hero", "footer", "header", "bg", "background", "menu", "avatar", "profile", "logo", "icon", "svg", "slider", "carousel"]):
            score -= 1000
            
        # Slight penalty for PNGs (often icons/logos) and boost for photography formats
        if ".png" in u:
            score -= 50
        elif any(ext in u for ext in [".jpg", ".jpeg", ".webp"]):
            score += 20
            
        # E-commerce platforms usually store product images in specific media folders
        if any(w in u for w in ["upload", "media", "cdn.shopify.com/s/files", "gallery", "large", "zoom", "thumb"]):
            score += 30
            
        if evaluator_type == "image_quality":
            # Boutique: prioritize shoes, products, shop, items
            if any(w in u for w in ["product", "item", "shoe", "sneaker", "boot", "shop", "catalog"]):
                score += 200
            if "interior" in u or "storefront" in u or "store" in u:
                score -= 20
        else:
            # Jenex: prioritize HVAC, products, portfolios, catalog covers, works, references
            if any(w in u for w in ["product", "termek", "catalog", "katalog", "portfolio", "cover", "hvac", "duct", "szellozes", "legtechnika", "item", "project", "projekt", "work", "munka", "reference", "referencia", "gallery", "galeria"]):
                score += 500
                
        return score

    # Sort URLs descending by heuristic score
    valid_urls.sort(key=score_url, reverse=True)
    return valid_urls


def extract_product_grid_images(html: str, domain: str = "") -> list[str]:
    """
    Extract product grid images by parsing HTML with BeautifulSoup.
    Looks for repeated images in common grid structures and filters aggressively.
    """
    import services.common.image_filters as image_filters

    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urlparse
    except ImportError:
        logger.warning("beautifulsoup4 not installed. Falling back to markdown regex.")
        return extract_image_urls(html, evaluator_type="image_quality")

    soup = BeautifulSoup(html, "html.parser")
    images = soup.find_all("img")
    
    candidates = []
    
    for img in images:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            continue
            
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/") and domain:
            src = f"https://{domain.rstrip('/')}{src}"
            
        if not src.startswith("http"):
            continue

        if image_filters.is_probably_decorative(src):
            continue

        width_val = img.get("width")
        height_val = img.get("height")
        try:
            width = int(width_val) if width_val else None
        except (ValueError, TypeError):
            width = None
        try:
            height = int(height_val) if height_val else None
        except (ValueError, TypeError):
            height = None

        # Look at the parent tag
        parent = img.parent
        is_linked = parent.name == "a" if parent else False
        if not is_linked:
            parent2 = parent.parent if parent else None
            is_linked = parent2.name == "a" if parent2 else False
            
        score = 10.0 if is_linked else 0.0
        candidates.append({"src": src, "width": width, "height": height, "score": score})
                
    return image_filters.filter_and_dedupe_images(candidates, max_results=20)


def extract_product_grid_images_via_crawler(url: str) -> list[str]:
    """
    Calls the local Crawl4AI crawler service using the LLMExtractionStrategy
    to intelligently pick the 4 best product images from a product grid page.
    """
    endpoint = f"{config.CRAWLER_ENDPOINT.rstrip('/')}/crawl"
    try:
        resp = requests.post(
            endpoint,
            json={
                "url": url,
                "extract_images": True,
                "force_playwright": True,
                "bypass_cache": False,
                "timeout_ms": 60000,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("extracted_data"):
            urls = data["extracted_data"].get("urls", [])
            if isinstance(urls, list):
                valid = []
                for u in urls:
                    if not u:
                        continue
                    u = u if u.startswith("http") else "https:" + u
                    u_lower = u.lower()
                    
                    # Heuristic to reject obvious non-images
                    if u_lower.endswith(".com/") or u_lower.endswith(".com") or u_lower.endswith("/products"):
                        continue
                        
                    if not any(ext in u_lower for ext in [".jpg", ".jpeg", ".png", ".webp", ".avif"]):
                        if not any(cdn in u_lower for cdn in ["cdn", "image", "media", "upload"]):
                            continue
                            
                    valid.append(u)
                return valid
    except Exception as exc:
        logger.warning("Crawler LLM extraction failed for %s: %s", url, exc)
    return []

def detect_tech_stack(pages_dict: dict[str, str | dict]) -> list[str]:
    """
    Detect e-commerce platforms or tech stack footprints from scraped content.
    pages_dict values may be plain markdown strings OR {"markdown":..., "html":...} dicts
    (when scrape_domain_pages was called with include_html=True).
    Returns a list of strings. WooCommerce entries include version if detectable,
    e.g. ["WooCommerce 7.8.2 (outdated)"].
    """
    import re
    stack = set()
    signatures = {
        "Shopify": ["powered by shopify", "cdn.shopify.com"],
        "WooCommerce": ["woocommerce", "wp-content/plugins/woocommerce"],
        "Shoptet": ["shoptet", "powered by shoptet"],
        "PrestaShop": ["prestashop"],
        "Magento": ["magento"],
        "Wix": ["wix.com", "powered by wix"],
    }

    for content in pages_dict.values():
        # Support both plain-string pages and include_html=True dicts
        if isinstance(content, dict):
            text = content.get("markdown", "")
            html = content.get("html", "")
        else:
            text = content
            html = ""

        text_lower = text.lower()
        html_lower = html.lower()
        combined_lower = text_lower + " " + html_lower

        for platform, footprints in signatures.items():
            if any(f in combined_lower for f in footprints):
                if platform == "WooCommerce" and html:
                    # Try to extract version from meta generator tag
                    m = re.search(
                        r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']WooCommerce\s+([\d.]+)["\']',
                        html,
                        re.IGNORECASE,
                    )
                    if m:
                        version_str = m.group(1)
                        parts = version_str.split(".")
                        major = int(parts[0]) if parts else 0
                        minor = int(parts[1]) if len(parts) > 1 else 0
                        outdated = major < 8 or (major == 8 and minor < 5)
                        label = f"WooCommerce {version_str}" + (" (outdated)" if outdated else "")
                        stack.add(label)
                    else:
                        stack.add(platform)
                else:
                    stack.add(platform)

    return list(stack)
