"""
main.py — Jenex Crawl4AI Service.

Architecture:
  - ONE persistent AsyncWebCrawler (Chromium) initialized at startup via FastAPI lifespan.
    All requests reuse this single browser — eliminates 2-3s Chromium startup per request.
  - Hybrid routing: trafilatura (fast, no browser) for simple HTML pages;
    Crawl4AI (full Playwright) for JS-heavy SPAs.
  - URL validated as http/https only via Pydantic HttpUrl.
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

import trafilatura
from crawl4ai import AsyncWebCrawler
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, Field
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_PROXY_ENDPOINT = os.environ.get("GEMINI_PROXY_ENDPOINT", "http://host.docker.internal:8045").rstrip("/")

# ── Persistent browser instance (reused across all requests) ──────────────────

_crawler: Optional[AsyncWebCrawler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Chromium once at boot; tear it down cleanly on shutdown."""
    global _crawler
    logger.info("Starting persistent AsyncWebCrawler (Chromium)...")
    _crawler = AsyncWebCrawler(verbose=False)
    await _crawler.start()
    logger.info("AsyncWebCrawler ready.")
    yield
    logger.info("Shutting down AsyncWebCrawler...")
    await _crawler.close()
    logger.info("AsyncWebCrawler closed.")


app = FastAPI(title="Jenex Crawl4AI Service", lifespan=lifespan)

# ── Request model ─────────────────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    url: HttpUrl                          # enforces http/https — no ftp/file paths
    css_selector: Optional[str] = None
    bypass_cache: bool = False
    force_playwright: bool = False        # set True to skip trafilatura fast-path
    timeout_ms: int = 30000              # cap at 30s per page
    extract_images: bool = False

class ProductImagesSchema(BaseModel):
    urls: list[str] = Field(description="Exactly 4 URLs of product images from the product grid. Do not include logos or UI elements.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_spa_likely(html: str) -> bool:
    """Heuristic: if page has very little visible text but lots of <script> tags, it's probably SPA."""
    if not html:
        return True
    script_count = html.lower().count("<script")
    text_density = len(html.replace(" ", "").replace("\n", "")) / max(len(html), 1)
    # If >10 scripts and text density suggests placeholder content, treat as SPA
    return script_count > 8 and len(html) < 15_000


def _trafilatura_scrape(url: str) -> Optional[str]:
    """
    Fast text extraction using trafilatura (no browser, no JavaScript).
    Returns markdown-like text or None if page requires JS rendering.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        if _is_spa_likely(downloaded):
            logger.info("Trafilatura detected SPA for %s — routing to Playwright", url)
            return None
        text = trafilatura.extract(downloaded, include_links=True, include_images=True, output_format="markdown")
        return text
    except Exception as exc:
        logger.warning("Trafilatura failed for %s: %s", url, exc)
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Liveness probe — returns ok if the crawler service is running."""
    return {"status": "ok", "browser_ready": _crawler is not None}


@app.post("/crawl")
async def crawl(req: CrawlRequest):
    """
    Scrape a URL and return markdown + media.
    Uses trafilatura for simple HTML pages (fast, no browser overhead).
    Falls back to Crawl4AI/Playwright for JS-rendered SPAs.
    """
    url_str = str(req.url)
    logger.info("Crawl request: %s (force_playwright=%s, extract_images=%s)", url_str, req.force_playwright, req.extract_images)

    # ── Fast path: trafilatura for non-SPA pages ──────────────────────────────
    if not req.force_playwright and not req.extract_images:
        fast_text = _trafilatura_scrape(url_str)
        if fast_text and len(fast_text) > 500:
            logger.info("Trafilatura succeeded for %s (%d chars)", url_str, len(fast_text))
            return {
                "success": True,
                "markdown": fast_text,
                "media": {"images": []},
                "links": {"internal": [], "external": []},
                "renderer": "trafilatura",
            }

    # ── Full path: Playwright via persistent Crawl4AI browser ────────────────
    if _crawler is None:
        raise HTTPException(status_code=503, detail="Browser not initialized yet. Try again in a few seconds.")

    try:
        kwargs = {
            "bypass_cache": req.bypass_cache,
            "page_timeout": req.timeout_ms,
        }
        if req.css_selector:
            kwargs["css_selector"] = req.css_selector

        result = await _crawler.arun(url=url_str, **kwargs)

        extracted_data = None
        if req.extract_images and result.success and result.markdown:
            import httpx
            import json
            try:
                system_prompt = "You are an AI that extracts product images from e-commerce product grids. Extract exactly 4 high-quality product image URLs from markdown image tags (![alt](url)). Return ONLY actual physical products. Do not extract site logos, UI layout elements, shipping partner logos (like GLS, Packeta), payment icons, or blog banners. Ensure the URLs point directly to image files (e.g., .jpg, .png, .webp) and not to HTML pages. Return ONLY valid JSON in this format: {\"urls\": [\"url1\", \"url2\", \"url3\", \"url4\"]}"
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{GEMINI_PROXY_ENDPOINT}/v1/chat/completions",
                        json={
                            "model": "gemini-3.6-flash-high",
                            "response_format": {"type": "json_object"},
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": "Extract images from the following markdown content:\n\n" + result.markdown[:30000]}
                            ]
                        },
                        timeout=30.0
                    )
                    resp.raise_for_status()
                    llm_content = resp.json()["choices"][0]["message"]["content"]
                    # Sometimes the model wraps it in ```json ... ```
                    if llm_content.startswith("```json"):
                        llm_content = llm_content[7:-3].strip()
                    extracted_data = json.loads(llm_content)
            except Exception as e:
                logger.error("Manual LLM extraction failed: %s", e)

        if not result.success:
            logger.error("Crawl4AI failed for %s: %s", url_str, result.error_message)
            return {"success": False, "error": result.error_message, "renderer": "playwright"}

        logger.info(
            "Crawl4AI succeeded for %s (%d chars, %d images)",
            url_str,
            len(result.markdown or ""),
            len((result.media or {}).get("images", [])),
        )
        
        return {
            "success": True,
            "html": getattr(result, "html", ""),
            "markdown": result.markdown,
            "media": result.media,
            "links": result.links,
            "extracted_data": extracted_data,
            "renderer": "playwright",
        }

    except Exception as exc:
        logger.exception("Unexpected error crawling %s", url_str)
        raise HTTPException(status_code=500, detail=str(exc))
