"""
scorers/image_quality.py — Scorer B: shoe-photo-upgrade (image_quality).

Firecrawl scrapes product pages, extracts image URLs,
a vision-capable LLM scores against a rubric. Score is an OPPORTUNITY
score: high = poor photos + active business = great lead.
"""
import json
import logging

import config
import firecrawl_client
import llm

logger = logging.getLogger(__name__)

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
{scraped_content}

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
"""


def score(candidate: dict, campaign: dict, icp: dict, few_shot: list[dict]) -> dict:
    """
    Score a candidate using image_quality (opportunity) strategy.
    """
    domain = candidate["domain"]

    # Scrape product pages
    product_paths = ["", "/products", "/shop", "/termekek", "/webshop", "/catalogue"]
    pages = firecrawl_client.scrape_domain_pages(domain, paths=product_paths, include_html=True)
    
    # pages is {url: {"markdown": md, "html": html}}
    # Extract markdown text for text-based analysis
    pages_markdown = {url: data.get("markdown", "") for url, data in pages.items()}
    
    scraped = "\n\n---\n\n".join(
        f"### {url}\n{text[:1500]}" for url, text in list(pages_markdown.items())[:4]
    )
    if not scraped:
        scraped = "(No content could be scraped)"

    # Tech stack detection
    tech_stack = firecrawl_client.detect_tech_stack(pages_markdown)

    # Early "Dead site" filter
    import re, datetime
    current_year = datetime.datetime.now().year
    has_socials = False
    has_recent_copyright = True
    copyright_found = False

    for text in pages_markdown.values():
        text_lower = text.lower()
        if any(p in text_lower for p in ["facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com"]):
            has_socials = True
            
        years = re.findall(r'(?:copyright|©).*?(20\d\d)', text_lower)
        if years:
            copyright_found = True
            max_year = max(int(y) for y in years)
            if max_year >= current_year - 2:
                has_recent_copyright = True
            else:
                has_recent_copyright = False

    if not has_socials and copyright_found and not has_recent_copyright:
        return {
            "score": 0,
            "rationale": "Early exit: No social media links and copyright dates appear to be older than 2 years. Site is likely inactive.",
            "evidence_urls": list(pages.keys()),
            "evidence_data": {"business_activity": "inactive", "photo_quality": "unknown", "tech_stack": tech_stack},
            "model_used": "rules-engine",
            "provider": "local",
            "tokens_in": 0, "tokens_out": 0,
        }

    # Extract image URLs using Crawl4AI LLM Extraction for the first product-like page
    all_images = []
    
    # Try to find a good product page URL first
    product_url = None
    for url in pages.keys():
        if any(w in url.lower() for w in ["/products", "/termekek", "/shop", "/katalog", "/catalog"]):
            product_url = url
            break
            
    if not product_url and pages:
        # Fallback to homepage
        product_url = list(pages.keys())[0]

    if product_url:
        logger.info("Triggering LLM image extraction for %s", product_url)
        all_images = firecrawl_client.extract_product_grid_images_via_crawler(product_url)
        
    if not all_images:
        logger.warning("LLM extraction failed or returned 0 images. Falling back to simple markdown extraction.")
        for data in pages.values():
            all_images.extend(firecrawl_client.extract_image_urls(data.get("markdown", ""), evaluator_type="image_quality"))
            
    # Deduplicate and limit
    seen = set()
    images = []
    for u in all_images:
        if u not in seen and len(images) < 8:
            seen.add(u)
            images.append(u)

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

    # Use vision model if we have images, otherwise text-only
    if images:
        result, ti, to, model, provider = llm.chat_vision(
            prompt, images, temperature=0.2
        )
    else:
        result, ti, to, model, provider = llm.chat_json(prompt, temperature=0.2)

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
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
