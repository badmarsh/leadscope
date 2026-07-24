"""
scorers/image_quality.py — Scorer B: shoe-photo-upgrade (image_quality).

Firecrawl scrapes product pages, extracts image URLs,
a vision-capable LLM scores against a rubric. Score is an OPPORTUNITY
score: high = poor photos + active business = great lead.
"""
import datetime
import json
import logging
import re
import requests
from typing import Optional

import config
import firecrawl_client
import llm

logger = logging.getLogger(__name__)

def _crawler_scrape(url: str, force_playwright: bool = False) -> tuple[Optional[str], Optional[list]]:
    """
    Call the shared Crawl4AI crawler service.
    Returns (markdown_text, images_list).
    """
    endpoint = f"{config.CRAWLER_ENDPOINT.rstrip('/')}/crawl"
    try:
        resp = requests.post(
            endpoint,
            json={
                "url": url,
                "extract_images": True,
                "force_playwright": force_playwright,
                "bypass_cache": False,
                "timeout_ms": 30000,
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            logger.warning("Crawler returned success=false for %s: %s", url, data.get("error"))
            return None, None
        markdown = data.get("markdown") or ""
        images = data.get("images") or []
        return markdown if markdown else None, images
    except Exception as exc:
        logger.warning("Crawler request failed for %s: %s", url, exc)
        return None, None

SCORING_PROMPT = """
You are evaluating an e-commerce website as a potential customer for a product
photography upgrade service. You are scoring the OPPORTUNITY — how much this
business would benefit from better product photos.

## Scoring rubric (opportunity score, 0-100)
A HIGH score means "great lead" = the business has:
  - Poor/flat/amateur product photos (low resolution, inconsistent lighting,
    cluttered backgrounds, flat photo-booth-style shots)
  - BUT signs the business is active (product count, recent activity, working
    checkout, professional-looking rest of the site)
  - The images MUST depict SHOES or footwear. We only want shoe boutiques!

A LOW score means "not a good lead" =
  - Already has professional product photos, OR
  - Business appears inactive/dead/too small, OR
  - Not an e-commerce business at all, OR
  - They do NOT sell shoes/footwear (if the images show random products, clothes without shoes, jewelry, etc., the score should be 0).

Direction: 100 = great lead (poor photos + active business + sells shoes), 0 = not a lead (or doesn't sell shoes).

## Past feedback (few-shot)
{few_shot_examples}

## Candidate info
Domain: {domain}
Company name: {company_name}

## Product page text (truncated)
The text is provided below in the USER DATA section.

## Product images
The following {image_count} product image URLs were found. You will see them
attached as images. Evaluate their quality and verify they are shoes.

## Instructions
Score 0-100 as an opportunity score (poor photos + active business + sells shoes = HIGH).

Return JSON with:
- "score": integer 0-100
- "rationale": 2-3 sentences explaining the opportunity assessment
- "photo_quality": "poor" | "average" | "good" | "professional"
- "business_activity": "active" | "moderate" | "low" | "inactive"
- "product_type": "shoes" | "other" | "unknown"
- "product_count_estimate": approximate number of products visible
- "issues_found": array of specific photo quality issues (e.g. "low resolution",
  "inconsistent lighting", "cluttered backgrounds", "flat/photo-booth style")
- "cold_email_hook": 1-2 sentences personalized critique of the photos (e.g. "I loved the layout of your homepage, but the harsh lighting on your main product photos makes the textures hard to see."). Must be in the local language of the site.
=== END SYSTEM INSTRUCTIONS ===

=== BEGIN USER DATA ===
{scraped_content}
=== END USER DATA ===
"""


def score(candidate: dict, campaign: dict, icp: dict, few_shot: list[dict]) -> dict:
    """
    Score a candidate using image_quality (opportunity) strategy.
    """
    domain = candidate["domain"]

    # Use _discover_product_paths from firecrawl_client to find likely paths
    product_paths = firecrawl_client._discover_product_paths(domain)
    
    pages_markdown = {}
    all_images = []
    
    # Try up to 3 paths until we find good images
    for path in product_paths[:3]:
        url = f"https://{domain}{path}"
        # We use force_playwright=True for product grids because they are often JS rendered
        md, imgs = _crawler_scrape(url, force_playwright=True)
        if md:
            pages_markdown[url] = md
        if imgs:
            # Prioritize extracted images using existing heuristic
            imgs = [img.get("src") for img in imgs if isinstance(img, dict) and img.get("src")]
            all_images.extend(imgs)

    # Pre-process URLs
    seen = set()
    valid_urls = []
    ignore_patterns = [
        "bat.bing.com", "google-analytics.com", "facebook.com", "twitter.com", "instagram.com", 
        "x.com", "linkedin.com", "youtube.com", "tiktok.com", "pinterest.com",
        "pixel", "tracker", ".svg", "logo", "icon", "spinner", "loader", "social",
        "badge", "trust", "support", "shipping", "payment", "secure", "guarantee", "return",
        "header", "footer", "banner", "hero", "avatar", "profile", "menu",
        "partner", "layout", "element", "blog", "gls", "packeta", "szepkartya",
        "dpd", "mpl-", "foxpost", "cetelem", "mastercard", "visa", "barion", "simplepay",
        "mastercard", "maestro", "paypal", "apple-pay", "google-pay", "alipay",
        "slider", "brand", "carousel", "sponsor", "client", "thumb_brand", "swiper",
        "data:image"
    ]
    for u in all_images:
        if not u or not isinstance(u, str):
            continue
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = f"https://{domain}{u}"
            
        u = u.replace("%7Bwidth%7D", "800").replace("{width}", "800")
        is_tracking = any(pattern in u.lower() for pattern in ignore_patterns)
        
        if u not in seen and u.startswith("http") and not is_tracking:
            seen.add(u)
            valid_urls.append(u)

    def score_url(url: str) -> int:
        u = url.lower()
        score = 0
        if any(w in u for w in ["banner", "hero", "footer", "header", "bg", "background", "menu", "avatar", "profile"]):
            score -= 50
        if ".png" in u:
            score -= 10
        elif any(ext in u for ext in [".jpg", ".jpeg", ".webp"]):
            score += 10
        if any(w in u for w in ["upload", "media", "cdn.shopify.com/s/files", "gallery", "large", "zoom", "thumb"]):
            score += 30
        if any(w in u for w in ["product", "item", "shoe", "sneaker", "boot", "shop", "catalog"]):
            score += 100
        if "interior" in u or "storefront" in u or "store" in u:
            score -= 20
        return score

    valid_urls.sort(key=score_url, reverse=True)
    all_images = valid_urls[:5] # Keep top 5 images

    scraped = "\n\n---\n\n".join(
        f"### {url}\n{text[:1500]}" for url, text in list(pages_markdown.items())[:4]
    )
    if not scraped:
        scraped = "(No content could be scraped)"

    # Tech stack detection
    tech_stack = firecrawl_client.detect_tech_stack(pages_markdown)

    # Early "Dead site" filter — track max copyright year across ALL pages
    current_year = datetime.datetime.now().year
    has_socials = False
    all_copyright_years = []

    for text in pages_markdown.values():
        text_lower = text.lower()
        if any(p in text_lower for p in ["facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com"]):
            has_socials = True
        years = re.findall(r'(?:copyright|\xa9).*?(20\d\d)', text_lower)
        all_copyright_years.extend(int(y) for y in years)

    copyright_found = bool(all_copyright_years)
    has_recent_copyright = copyright_found and max(all_copyright_years) >= current_year - 2

    if not has_socials and copyright_found and not has_recent_copyright:
        return {
            "score": 0,
            "rationale": "Early exit: No social media links and copyright dates appear to be older than 2 years. Site is likely inactive.",
            "evidence_urls": list(pages_markdown.keys()),
            "evidence_data": {"business_activity": "inactive", "photo_quality": "unknown", "tech_stack": tech_stack},
            "model_used": "rules-engine",
            "provider": "local",
            "tokens_in": 0, "tokens_out": 0,
        }
    # Use the images we already selected and limited to top 5
    images = all_images

    # Build few-shot
    few_shot_str = ""
    if few_shot:
        examples = []
        for fb in few_shot:
            examples.append(
                f"- Domain: {fb.get('domain', '?')} | Decision: {fb['decision']} | "
                f"Note: {fb.get('note', 'N/A')}"
            )
        few_shot_str = "\n".join(examples)
    else:
        few_shot_str = "(No prior feedback available)"

    prompt = SCORING_PROMPT.format(
        few_shot_examples=few_shot_str,
        domain=domain,
        company_name=candidate.get("company_name", "Unknown"),
        scraped_content=scraped[:4000],
        image_count=len(images),
    )

    req_fields = ["score", "rationale", "cold_email_hook", "photo_quality", "product_type"]
    # Use vision model if we have images, otherwise text-only
    if images:
        result, ti, to, model, provider = llm.chat_vision(
            prompt, images, temperature=0.2, required_fields=req_fields
        )
    else:
        result, ti, to, model, provider = llm.chat_json(prompt, temperature=0.2, required_fields=req_fields)

    if "_raw" in result:
        logger.warning("image_quality scorer got non-JSON response")
        return {
            "score": 50, "rationale": "LLM returned non-parseable response",
            "evidence_urls": list(pages.keys()),
            "evidence_data": {"raw_response": result["_raw"][:500], "images_found": len(images)},
            "model_used": model, "provider": provider,
            "tokens_in": ti, "tokens_out": to,
        }

    return {
        "score": max(0, min(100, int(result.get("score", 50)))),
        "rationale": result.get("rationale", ""),
        "evidence_urls": list(pages.keys()),
        "evidence_data": {
            "photo_quality": result.get("photo_quality", "unknown"),
            "business_activity": result.get("business_activity", "unknown"),
            "product_type": result.get("product_type", "unknown"),
            "product_count_estimate": result.get("product_count_estimate", 0),
            "issues_found": result.get("issues_found", []),
            "cold_email_hook": result.get("cold_email_hook", ""),
            "tech_stack": tech_stack,
            "images_analyzed": images[:8],
            "pages_scraped": list(pages.keys()),
            "cached_pages": pages_markdown,
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
