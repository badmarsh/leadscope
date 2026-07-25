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
from pydantic import BaseModel, Field

import services.common.config as config
import firecrawl_client
import services.common.llm as llm

logger = logging.getLogger(__name__)

def _crawler_scrape(url: str, force_playwright: bool = False) -> tuple[Optional[str], Optional[str]]:
    """
    Call the shared Crawl4AI crawler service.
    Returns (markdown_text, html_text).
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
                "timeout_ms": 60000,
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            logger.warning("Crawler returned success=false for %s: %s", url, data.get("error"))
            return None, None
        markdown = data.get("markdown") or ""
        html = data.get("html") or ""
            
        return markdown if markdown else None, html if html else None
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
  - The images MUST depict {icp_target}. We only want {icp_target}!

A LOW score means "not a good lead" =
  - Already has professional product photos, OR
  - Business appears inactive/dead/too small, OR
  - Not an e-commerce business at all, OR
  - They do NOT sell {icp_target} (if the images show random products not matching {icp_target}, the score should be 0).

Direction: 100 = great lead (poor photos + active business + sells {icp_target}), 0 = not a lead (or doesn't sell {icp_target}).

## Past feedback (few-shot)
{few_shot_examples}

## Candidate info
Domain: {domain}
Company name: {company_name}

## Product page text (truncated)
The text is provided below in the USER DATA section.

## Product images
The following {image_count} product image URLs were found. You will see them
attached as images. Evaluate their quality and verify they are {icp_target}.

## Instructions
Score 0-100 as an opportunity score (poor photos + active business + sells {icp_target} = HIGH).

Return JSON with:
- "score": integer 0-100
- "rationale": 2-3 sentences explaining the opportunity assessment
- "photo_quality": "poor" | "average" | "good" | "professional"
- "business_activity": "active" | "moderate" | "low" | "inactive"
- "product_type": "{icp_target_short}" | "other" | "unknown"
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
        md, html_content = _crawler_scrape(url, force_playwright=True)
        if md:
            pages_markdown[url] = md
        if html_content:
            imgs = firecrawl_client.extract_product_grid_images(html_content)
            all_images.extend(imgs)

    # Fallback to markdown image extraction if HTML extraction found 0 images
    if not all_images and pages_markdown:
        for md_text in pages_markdown.values():
            if md_text:
                imgs = firecrawl_client.extract_image_urls(md_text, evaluator_type="image_quality")
                all_images.extend(imgs)

    # Pre-process URLs
    seen = set()
    valid_urls = []
    for u in all_images:
        if not u or not isinstance(u, str):
            continue
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = f"https://{domain}{u}"
            
        u = u.replace("%7Bwidth%7D", "800").replace("{width}", "800")
        
        # extract_product_grid_images already filters heavily, but let's just make sure 
        # it isn't an obvious banner
        u_lower = u.lower()
        if any(w in u_lower for w in ["banner", "hero", "footer", "header", "bg", "background", "menu", "avatar", "profile", "logo", "icon", "svg", "slider", "carousel"]):
            continue
            
        if u not in seen and u.startswith("http"):
            seen.add(u)
            valid_urls.append(u)

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

    icp_target = icp.get("target_products", icp.get("name", "relevant products"))
    icp_target_short = icp_target.split()[0][:10] if icp_target else "target"
    prompt = SCORING_PROMPT.format(
        few_shot_examples=few_shot_str,
        domain=domain,
        company_name=candidate.get("company_name", "Unknown"),
        scraped_content=scraped[:4000],
        image_count=len(images),
        icp_target=icp_target,
        icp_target_short=icp_target_short
    )

    class ImageQualityResponse(BaseModel):
        score: int
        rationale: str
        photo_quality: str
        business_activity: str
        product_type: str
        product_count_estimate: int
        issues_found: list[str]
        cold_email_hook: str

    # Use vision model if we have images, otherwise text-only
    if images:
        result, ti, to, model, provider = llm.chat_vision(
            prompt, images, temperature=0.2, response_model=ImageQualityResponse
        )
    else:
        result, ti, to, model, provider = llm.chat_json(
            prompt, temperature=0.2, response_model=ImageQualityResponse
        )

    if "_raw" in result:
        logger.warning("image_quality scorer got non-JSON response")
        return {
            "score": 50, "rationale": "LLM returned non-parseable response",
            "evidence_urls": list(pages_markdown.keys()),
            "evidence_data": {"raw_response": result["_raw"][:500], "images_found": len(images)},
            "model_used": model, "provider": provider,
            "tokens_in": ti, "tokens_out": to,
        }

    return {
        "score": max(0, min(100, result.get("score", 50) if isinstance(result, dict) else getattr(result, "score", result.get("score", 50)))),
        "rationale": result.get("rationale", "") if isinstance(result, dict) else getattr(result, "rationale", ""),
        "evidence_urls": list(pages_markdown.keys()),
        "evidence_data": {
            "photo_quality": result.get("photo_quality", "unknown") if isinstance(result, dict) else getattr(result, "photo_quality", "unknown"),
            "business_activity": result.get("business_activity", "unknown") if isinstance(result, dict) else getattr(result, "business_activity", "unknown"),
            "product_type": result.get("product_type", "unknown") if isinstance(result, dict) else getattr(result, "product_type", "unknown"),
            "product_count_estimate": result.get("product_count_estimate", 0) if isinstance(result, dict) else getattr(result, "product_count_estimate", 0),
            "issues_found": result.get("issues_found", []) if isinstance(result, dict) else getattr(result, "issues_found", []),
            "cold_email_hook": result.get("cold_email_hook", "") if isinstance(result, dict) else getattr(result, "cold_email_hook", ""),
            "tech_stack": tech_stack,
            "images_analyzed": images[:8],
            "pages_scraped": list(pages_markdown.keys()),
            "cached_pages": pages_markdown,
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
