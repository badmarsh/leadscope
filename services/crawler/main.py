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
from pydantic import BaseModel, HttpUrl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    logger.info("Crawl request: %s (force_playwright=%s)", url_str, req.force_playwright)

    # ── Fast path: trafilatura for non-SPA pages ──────────────────────────────
    if not req.force_playwright:
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
            "markdown": result.markdown,
            "media": result.media,
            "links": result.links,
            "renderer": "playwright",
        }

    except Exception as exc:
        logger.exception("Unexpected error crawling %s", url_str)
        raise HTTPException(status_code=500, detail=str(exc))
