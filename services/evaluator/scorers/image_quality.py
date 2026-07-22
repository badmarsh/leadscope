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

A LOW score means "not a good lead" =
  - Already has professional product photos, OR
  - Business appears inactive/dead/too small, OR
  - Not an e-commerce business at all

Direction: 100 = great lead (poor photos + active business), 0 = not a lead.

## Past feedback (few-shot)
{few_shot_examples}

## Candidate info
Domain: {domain}
Company name: {company_name}

## Product page text (truncated)
{scraped_content}

## Product images
The following {image_count} product image URLs were found. You will see them
attached as images. Evaluate their quality.

## Instructions
Score 0-100 as an opportunity score (poor photos + active business = HIGH).

Return JSON with:
- "score": integer 0-100
- "rationale": 2-3 sentences explaining the opportunity assessment
- "photo_quality": "poor" | "average" | "good" | "professional"
- "business_activity": "active" | "moderate" | "low" | "inactive"
- "product_count_estimate": approximate number of products visible
- "issues_found": array of specific photo quality issues (e.g. "low resolution",
  "inconsistent lighting", "cluttered backgrounds", "flat/photo-booth style")
"""


def score(candidate: dict, campaign: dict, icp: dict, few_shot: list[dict]) -> dict:
    """
    Score a candidate using image_quality (opportunity) strategy.
    """
    domain = candidate["domain"]

    # Scrape product pages
    product_paths = ["", "/products", "/shop", "/termekek", "/webshop", "/catalogue"]
    pages = firecrawl_client.scrape_domain_pages(domain, paths=product_paths)
    scraped = "\n\n---\n\n".join(
        f"### {url}\n{text[:1500]}" for url, text in list(pages.items())[:4]
    )
    if not scraped:
        scraped = "(No content could be scraped)"

    # Extract image URLs
    all_images = []
    for text in pages.values():
        all_images.extend(firecrawl_client.extract_image_urls(text))
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
            prompt, images, temperature=0.2, model=config.SCORER_VISION_MODEL
        )
    else:
        result, ti, to, model, provider = llm.chat_json(prompt, temperature=0.2, model=config.SCORER_VISION_MODEL)

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
            "product_count_estimate": result.get("product_count_estimate", 0),
            "issues_found": result.get("issues_found", []),
            "images_analyzed": images[:8],
            "pages_scraped": list(pages.keys()),
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
