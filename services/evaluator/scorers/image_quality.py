"""
scorers/image_quality.py — Scorer B: shoe-photo-upgrade (image_quality).

Rewritten to use a pure Vision AI approach.
Connects to Browserless to take screenshots of the homepage and product list page,
then feeds them to Gemini Vision for evaluation.

Note: Screenshots are clipped to the top 2000px (above-the-fold + first product section)
to reduce Vision AI token costs by ~60-70%.
"""
import datetime
import logging
import re
import threading
from typing import Optional
from pydantic import BaseModel
import base64
from playwright.sync_api import sync_playwright

import services.common.config as config
import firecrawl_client
import services.common.llm as llm

logger = logging.getLogger(__name__)

# Limit concurrent Playwright sessions to protect Browserless (max 25 total)
_BROWSER_SEMAPHORE = threading.Semaphore(4)

SCORING_PROMPT = """
You are evaluating an e-commerce website as a potential customer for a product
photography upgrade service. You are scoring the OPPORTUNITY — how much this
business would benefit from better product photos.

You will receive screenshots of the website's homepage and product list page.

## Scoring rubric (opportunity score, 0-100)
A HIGH score means "great lead" = the business has:
  - Amateur, suboptimal, or flat product photos (e.g. basic photos on a white background, cluttered lifestyle shots, poor lighting)
  - BUT signs the business is active (product count, recent activity, working checkout, professional-looking rest of the site)
  - It clearly represents an INDEPENDENT retailer or small brand.
  - The images MUST depict {icp_target}. We only want {icp_target}!

A LOW score (0) means "not a good lead" =
  - Already has professional, high-end studio product photos/campaigns.
  - Looks like a global retail giant, massive marketplace, or corporate brand.
  - Business appears inactive/dead/too small.
  - Not an e-commerce business at all (just a blog, social media page, etc).
  - They do NOT sell {icp_target}.

Direction: 100 = great lead (amateur photos + independent active business + sells {icp_target}), 0 = not a lead (or doesn't sell {icp_target}).

## Past feedback (few-shot)
{few_shot_examples}

## Candidate info
<DOMAIN>{domain}</DOMAIN>
<COMPANY_NAME>{company_name}</COMPANY_NAME>

## Instructions
Review the attached screenshots carefully.
Score 0-100 as an opportunity score (amateur photos + independent business + sells {icp_target} = HIGH).

Return JSON with:
- "score": integer 0-100
- "rationale": 2-3 sentences explaining the opportunity assessment based on the visual evidence.
- "photo_quality": "poor" | "average" | "good" | "professional" | "irrelevant"
- "business_activity": "active" | "moderate" | "low" | "inactive"
- "product_type": "{icp_target_short}" | "other" | "unknown"
- "product_count_estimate": approximate number of products visible
- "issues_found": array of specific photo quality issues (e.g. "low resolution", "inconsistent lighting", "cluttered backgrounds", "flat/photo-booth style", "basic white background")
- "cold_email_hook": 1-2 sentences personalized critique of the photos (e.g. "I loved the layout of your homepage, but the harsh lighting on your main product photos makes the textures hard to see."). Must be in the local language of the site.
"""

def take_screenshots(domain: str, product_paths: list[str]) -> list[str]:
    """
    Connects to browserless and takes screenshots of the homepage and best product path.
    Screenshots are clipped to the top 2000px to reduce Vision AI token costs.
    Returns a list of base64 encoded strings.
    """
    token = os.environ.get("BROWSERLESS_TOKEN", "")
    ws_url = f"ws://browserless:3000/?token={token}" if token else "ws://browserless:3000"
    base64_images = []
    
    urls_to_capture = [f"https://{domain}"]
    if product_paths:
        urls_to_capture.append(f"https://{domain}{product_paths[0]}")

    # Viewport clip: capture only above-the-fold + first product section (2000px)
    # This reduces base64 token size by ~60-70% vs full_page=True
    CLIP_HEIGHT = 2000
        
    try:
        with _BROWSER_SEMAPHORE:  # Max 4 concurrent Playwright sessions
            with sync_playwright() as p:
                logger.info("Connecting to Browserless for %s...", domain)
                browser = p.chromium.connect_over_cdp(ws_url)
                
                for url in urls_to_capture:
                    logger.info("Capturing screenshot of %s", url)
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 1080},
                        ignore_https_errors=True
                    )
                    page = context.new_page()
                    try:
                        response = None
                        try:
                            response = page.goto(url, timeout=15000, wait_until="domcontentloaded")
                        except Exception as e:
                            err_msg = str(e)
                            if "https://" in url and any(err in err_msg for err in ["ERR_CONNECTION_REFUSED", "ERR_SSL", "SSL", "ERR_CERT", "Connection refused"]):
                                http_url = url.replace("https://", "http://", 1)
                                logger.info("HTTPS failed (%s). Retrying with HTTP: %s", err_msg, http_url)
                                response = page.goto(http_url, timeout=15000, wait_until="domcontentloaded")
                            else:
                                raise

                        if not response or not response.ok:
                            logger.warning("Failed to load %s: HTTP %s", url, response.status if response else "Unknown")
                            continue
                            
                        page.wait_for_timeout(2000) # Let animations/images settle
                        screenshot_bytes = page.screenshot(
                            type="jpeg",
                            quality=55,
                            clip={"x": 0, "y": 0, "width": 1280, "height": CLIP_HEIGHT},
                        )
                        base64_str = base64.b64encode(screenshot_bytes).decode("utf-8")
                        
                        # Prefix with data URI for LLM compatibility
                        base64_images.append(f"data:image/jpeg;base64,{base64_str}")
                    except Exception as e:
                        logger.warning("Playwright error on %s: %s", url, e)
                    finally:
                        context.close()
                        
                browser.close()
    except Exception as e:
        logger.error("Failed to connect to Browserless for %s: %s", domain, e)
        
    return base64_images

def extract_direct_product_images(domain: str, product_paths: list[str]) -> list[str]:
    """
    Extracts direct product image URLs (HTTP/HTTPS) from the store / product listing page.
    Uses crawler extraction, extruct (JSON-LD, OpenGraph), and BeautifulSoup grid parsing.
    Returns a deduplicated list of HTTP/HTTPS product image URLs.
    """
    product_images = []
    
    # 1. Try crawler LLM extraction on best product path and homepage
    target_urls = []
    if product_paths:
        target_urls.append(f"https://{domain}{product_paths[0]}")
    target_urls.append(f"https://{domain}")

    for target_url in target_urls:
        try:
            crawler_imgs = firecrawl_client.extract_product_grid_images_via_crawler(target_url)
            if crawler_imgs:
                for img in crawler_imgs:
                    if isinstance(img, str) and img.startswith("http") and img not in product_images:
                        product_images.append(img)
                if len(product_images) >= 4:
                    break
        except Exception as e:
            logger.warning("Crawler grid extraction failed for %s: %s", target_url, e)

    # 2. Fallback to HTML / extruct / OpenGraph parsing if fewer than 4 images found
    if len(product_images) < 4:
        for target_url in target_urls:
            try:
                import requests, extruct
                from w3lib.html import get_base_url
                resp = requests.get(target_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    base_url = get_base_url(resp.text, resp.url)
                    html_imgs = firecrawl_client.extract_product_grid_images(resp.text, domain=domain)
                    for img in html_imgs:
                        if isinstance(img, str) and img.startswith("http") and img not in product_images:
                            product_images.append(img)

                    data = extruct.extract(resp.text, base_url=base_url, syntaxes=["json-ld", "opengraph", "microdata"])
                    for item in data.get("json-ld", []):
                        img = item.get("image")
                        if isinstance(img, str) and img.startswith("http") and img not in product_images:
                            product_images.append(img)
                        elif isinstance(img, list):
                            for i in img:
                                if isinstance(i, str) and i.startswith("http") and i not in product_images:
                                    product_images.append(i)
                    for og in data.get("opengraph", []):
                        og_img = og.get("og:image")
                        if isinstance(og_img, str) and og_img.startswith("http") and og_img not in product_images:
                            product_images.append(og_img)
            except Exception as e:
                logger.warning("HTML/extruct extraction failed for %s: %s", target_url, e)

    ignore_terms = ["logo", "icon", "banner", "gls", "packeta", "visa", "mastercard", "paypal", "stripe", ".svg", "avatar", "badge", "trust", "hero"]
    filtered_images = [
        url for url in product_images
        if not any(b in url.lower() for b in ignore_terms)
    ]
    return list(dict.fromkeys(filtered_images))[:10]

def score(candidate: dict, campaign: dict, icp: dict, few_shot: list[dict]) -> dict:
    domain = candidate["domain"]

    # 1. Discover product paths via Firecrawl Map API
    product_paths = firecrawl_client._discover_product_paths(domain)
    
    # 2. Extract direct product images from shop / product listing page
    direct_product_images = extract_direct_product_images(domain, product_paths)
    
    # Fallback to take_screenshots if direct extraction yields nothing (e.g. in test mocks or JS-heavy SPA without crawler)
    base64_screenshots = []
    if not direct_product_images:
        base64_screenshots = take_screenshots(domain, product_paths)
    
    images_to_analyze = direct_product_images if direct_product_images else base64_screenshots
    
    # Fail fast on dead domains or sites with no images
    if not images_to_analyze:
        logger.warning("No product images found for %s. Marking as dead/no-product domain.", domain)
        return {
            "score": 0,
            "rationale": "Dead domain or no product images found on shop / product listing page.",
            "photo_quality": "irrelevant",
            "images_analyzed": [],
            "product_type": "other",
            "evidence_urls": [f"https://{domain}"],
            "evidence_data": {"business_activity": "inactive"},
            "model_used": "rules-engine",
            "provider": "local",
            "tokens_in": 0,
            "tokens_out": 0
        }

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

    logger.info("Sending %d product images of %s to Vision AI", len(images_to_analyze), domain)
    result, ti, to, model, provider = llm.chat_vision(
        prompt, images_to_analyze, temperature=0.0, response_model=ImageQualityResponse
    )

    if "_raw" in result:
        logger.warning("image_quality scorer got non-JSON response")
        return {
            "score": 50, "rationale": "LLM returned non-parseable response",
            "evidence_urls": [f"https://{domain}"],
            "evidence_data": {"raw_response": result["_raw"][:500], "images_found": len(images_to_analyze)},
            "model_used": model, "provider": provider,
            "tokens_in": ti, "tokens_out": to,
        }

    return {
        "score": max(0, min(100, result.get("score", 50) if isinstance(result, dict) else getattr(result, "score", result.get("score", 50)))),
        "rationale": result.get("rationale", "") if isinstance(result, dict) else getattr(result, "rationale", ""),
        "evidence_urls": [f"https://{domain}"] + ([f"https://{domain}{product_paths[0]}"] if product_paths else []),
        "evidence_data": {
            "photo_quality": result.get("photo_quality", "unknown") if isinstance(result, dict) else getattr(result, "photo_quality", "unknown"),
            "business_activity": result.get("business_activity", "unknown") if isinstance(result, dict) else getattr(result, "business_activity", "unknown"),
            "product_type": result.get("product_type", "unknown") if isinstance(result, dict) else getattr(result, "product_type", "unknown"),
            "product_count": result.get("product_count_estimate", 0) if isinstance(result, dict) else getattr(result, "product_count_estimate", 0),
            "products_url": f"https://{domain}{product_paths[0]}" if product_paths else f"https://{domain}",
            "issues_found": result.get("issues_found", []) if isinstance(result, dict) else getattr(result, "issues_found", []),
            "cold_email_hook": result.get("cold_email_hook", "") if isinstance(result, dict) else getattr(result, "cold_email_hook", ""),
            "images_analyzed": images_to_analyze,
            "product_images": direct_product_images,
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
