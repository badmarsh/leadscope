"""
stage5.py — Stage 5: Enrichment.

Polls candidates with status 'pending_review' or 'approved', for each:
  1. Check do_not_contact — skip if suppressed
  2. Skip if lead already has enrichment_report (already enriched — do not repeat)
  3. Skip if enrichment_attempted_at < ENRICHMENT_RETRY_HOURS ago (avoid hammering Firecrawl)
  4. Increment enrichment_attempt_count + set enrichment_attempted_at BEFORE calling Firecrawl
  5. Firecrawl scrapes the domain's homepage and contact/impressum/kapcsolat pages
  6. LLM extracts email, contact info, company overview (in Slovak), and estimates
  7. On success: upsert into leads table — candidate status is NOT changed (user reviews manually)
  8. On failure:
       - attempt_count < MAX_ENRICHMENT_ATTEMPTS → leave status unchanged (retry next cycle)
       - attempt_count >= MAX_ENRICHMENT_ATTEMPTS → set 'enrichment_failed'
"""
import json
import logging
import re
import concurrent.futures
from typing import Optional

import requests

import config
import db
import cost_log
import llm

logger = logging.getLogger(__name__)

# ── Firecrawl helpers ──────────────────────────────────────────────────────────

CONTACT_PATHS = ["/kapcsolat", "/kontakt", "/contact", "/o-nas", "/impressum", "/about", "/kontakty", "/about-us", "/o-firme"]


def _firecrawl_scrape(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Call self-hosted Firecrawl to scrape a URL and return (markdown text, screenshot url).
    Returns (None, None) on any failure.
    """
    endpoint = f"{config.FIRECRAWL_ENDPOINT.rstrip('/')}/v1/scrape"
    try:
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": ["markdown", "screenshot"]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Firecrawl v1 returns {"success": true, "data": {"markdown": "...", "screenshot": "https://..."}}
        res_data = data.get("data", {})
        md = res_data.get("markdown") or data.get("markdown")
        ss = res_data.get("screenshot") or data.get("screenshot")
        return md, ss
    except Exception as exc:
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return None, None

def _screenshot_url(domain: str) -> str:
    """
    Return a high-quality screenshot URL for the given domain.
    Uses microlink.io which renders with a real headless browser (JS-enabled),
    producing much better quality than thumbnail services.
    Uses local /api/screenshot endpoint.
    """
    import urllib.parse
    encoded = urllib.parse.quote(f"https://{domain}", safe="")
    return f"/api/screenshot?url={encoded}"

def _scrape_domain(domain: str) -> tuple[Optional[str], str, Optional[str]]:
    """
    Try homepage + known contact paths. Returns (markdown_text, page_url_used, screenshot_url).
    Returns (None, "", None) if all attempts fail.
    """
    base = f"https://{domain}"
    # Try homepage first
    text, ss = _firecrawl_scrape(base)
    if text:
        return text, base, ss

    logger.warning("Firecrawl failed on homepage %s. Aborting subpaths to save time.", base)
    return None, "", None


# ── Ollama helpers ─────────────────────────────────────────────────────────────

EXTRACT_PROMPT = """
You are enriching a business lead from their website content.
Company: {company_name} ({domain})
Page content (markdown):
{page_text}

Extract the following:
1. "email": A business email address (if found).
2. "name": A contact person's name (if mentioned).
3. "phone": A contact phone number (if found).
4. "products_sold": A list of strings detailing products or services they sell in Slovak language (be specific, up to 5 items).
5. "estimated_size": Estimate company size (e.g., '1-10', '11-50', '51-200', '201+').
6. "estimated_revenue": Estimate revenue bracket (e.g., '< €1M', '€1M - €10M', '€10M+').
7. "estimated_traffic": Estimate web traffic volume (e.g., 'Low', 'Medium', 'High').
8. "report": A single short sentence (max 15 words) in Slovak language stating what the company does and if they fit the offer: {offer_summary}. Be extremely concise, direct, and concrete. No filler phrases.

Return ONLY valid JSON with keys: "email" (string or null), "name" (string or null), "phone" (string or null), "products_sold" (array of strings), "estimated_size" (string), "estimated_revenue" (string), "estimated_traffic" (string), "report" (string).
No prose outside the JSON.
CRITICAL: The "report" and "products_sold" fields MUST be written in Slovak language.
"""

def _enrich_info(domain: str, company_name: Optional[str], offer_summary: str, page_text: str) -> dict:
    """
    Use the shared Gemini proxy LLM to extract enrichment info from page text.
    Falls back gracefully to empty dict on failure.
    """
    prompt = EXTRACT_PROMPT.format(
        domain=domain,
        company_name=company_name or domain,
        offer_summary=offer_summary[:600],
        page_text=page_text[:4000]
    )
    try:
        result, _, _ = llm.chat_json(prompt, model=config.STAGE5_MODEL)
        return result if isinstance(result, dict) else {}
    except Exception as exc:
        logger.warning("LLM enrichment extraction failed for %s: %s", domain, exc)
        return {}

# ── Enrichment loop ────────────────────────────────────────────────────────────

def _get_offer_summary(business_brief: Optional[str]) -> str:
    """Extract a short offer summary from the business brief for the Ollama draft prompt."""
    if not business_brief:
        return "(offer not yet defined)"
    # First 300 chars is enough context for a cold-email opener
    return business_brief[:300]


def _enrich_candidate(candidate: dict, campaign: dict, conn, settings: dict | None = None) -> dict:
    """
    Attempt to enrich one candidate. Returns a status dict.
    All DB writes happen within the caller's transaction.
    """
    domain = candidate["domain"]
    campaign_id = candidate["campaign_id"]
    candidate_id = candidate["id"]

    # ── do_not_contact gate ────────────────────────────────────────────────────
    dnc = db.fetchone(
        conn,
        """
        SELECT 1 FROM do_not_contact
        WHERE (%s = domain OR %s LIKE '%%.' || domain)
          AND (campaign_id = %s OR campaign_id IS NULL)
        LIMIT 1
        """,
        (domain, domain, campaign_id),
    )
    if dnc:
        logger.info("Stage 5: skipping %s — on do_not_contact (campaign=%s)", domain, campaign_id)
        return {"candidate_id": candidate_id, "outcome": "skipped_dnc"}

    # ── Retry cooldown — read from campaign settings first (H5) ─────────────────
    effective_settings = settings or {}
    retry_hours = int(effective_settings.get("enrichment_retry_hours", config.ENRICHMENT_RETRY_HOURS))
    max_attempts = int(effective_settings.get("max_enrichment_attempts", config.MAX_ENRICHMENT_ATTEMPTS))

    if candidate["enrichment_attempted_at"] is not None:
        cooling = db.fetchone(
            conn,
            """
            SELECT enrichment_attempted_at < now() - interval '%s hours' AS past_cooldown
            FROM candidates WHERE id = %s
            """,
            (retry_hours, candidate_id),
        )
        if cooling and not cooling["past_cooldown"]:
            logger.info(
                "Stage 5: skipping %s — within %sh retry cooldown (attempt %s/%s)",
                domain, retry_hours,
                candidate["enrichment_attempt_count"], max_attempts,
            )
            return {"candidate_id": candidate_id, "outcome": "skipped_cooldown"}

    # ── Mark attempt BEFORE calling Firecrawl (spec requirement) ──────────────
    db.execute(
        conn,
        """
        UPDATE candidates
        SET enrichment_attempted_at  = now(),
            enrichment_attempt_count = enrichment_attempt_count + 1
        WHERE id = %s
        """,
        (candidate_id,),
    )
    new_attempt_count = (candidate["enrichment_attempt_count"] or 0) + 1

    # ── Firecrawl scrape ───────────────────────────────────────────────────────
    page_text = None
    page_url = None
    eval_evidence = candidate.get("eval_evidence") or {}
    cached_pages = eval_evidence.get("cached_pages", {})

    if cached_pages:
        # Prefer a contact page if cached, else just use the homepage/first
        for path in CONTACT_PATHS:
            for cached_url, text in cached_pages.items():
                if path in cached_url:
                    page_text = text
                    page_url = cached_url
                    break
            if page_text:
                break
        if not page_text and cached_pages:
            page_url, page_text = list(cached_pages.items())[0]

    if page_text:
        logger.info("Stage 5: Using cached Firecrawl scrape for %s", domain)
        screenshot_url = _screenshot_url(domain)
    else:
        page_text, page_url, fc_screenshot = _scrape_domain(domain)
        cost_log.log_call(conn, "stage5", "firecrawl", campaign_id=campaign_id, query_count=1)
        # Use Firecrawl screenshot if returned, otherwise fallback to microlink
        screenshot_url = fc_screenshot if fc_screenshot else (_screenshot_url(domain) if page_text else None)

    if not page_text:
        # Firecrawl failed
        if new_attempt_count >= max_attempts:
            db.execute(
                conn,
                "UPDATE candidates SET status = 'enrichment_failed' WHERE id = %s",
                (candidate_id,),
            )
            logger.warning(
                "Stage 5: %s → enrichment_failed after %d attempts", domain, new_attempt_count
            )
            return {"candidate_id": candidate_id, "outcome": "enrichment_failed", "attempts": new_attempt_count}
        else:
            logger.warning(
                "Stage 5: Firecrawl failed for %s (attempt %d/%d) — leaving approved for retry",
                domain, new_attempt_count, max_attempts,
            )
            return {"candidate_id": candidate_id, "outcome": "firecrawl_failed_retry", "attempts": new_attempt_count}

    # ── LLM: extract info via Gemini proxy ───────────────────────────────
    offer_summary = _get_offer_summary(campaign.get("business_brief"))
    info = _enrich_info(domain, candidate.get("company_name"), offer_summary, page_text)
    cost_log.log_call(conn, "stage5", "gemini", campaign_id=campaign_id, query_count=1)

    email = info.get("email")
    
    # ── Fallback: explicitly scrape contact paths if email is missing ──────
    if not email:
        logger.info("Stage 5: Email not found on main page for %s, trying contact paths...", domain)
        for path in CONTACT_PATHS[:3]:
            contact_url = f"https://{domain}{path}"
            contact_text, _ = _firecrawl_scrape(contact_url)
            cost_log.log_call(conn, "stage5", "firecrawl", campaign_id=campaign_id, query_count=1)
            
            if contact_text:
                contact_info = _enrich_info(domain, candidate.get("company_name"), offer_summary, contact_text)
                cost_log.log_call(conn, "stage5", "gemini", campaign_id=campaign_id, query_count=1)
                
                if contact_info.get("email") or contact_info.get("phone"):
                    info["email"] = contact_info.get("email") or info.get("email")
                    info["name"] = contact_info.get("name") or info.get("name")
                    info["phone"] = contact_info.get("phone") or info.get("phone")
                    
                    email = info.get("email")
                    logger.info("Stage 5: Found contact info (email: %s, phone: %s) on %s", email, info.get("phone"), path)
                    break

    contact_name = info.get("name")
    phone = info.get("phone")
    products_sold = info.get("products_sold") or []
    report = info.get("report")
    est_size = info.get("estimated_size")
    est_rev = info.get("estimated_revenue")
    est_traffic = info.get("estimated_traffic")

    # ── Insert into leads ─────────────────────────────────────────────────────
    db.execute(
        conn,
        """
        INSERT INTO leads (
            candidate_id, campaign_id, contact_email, contact_name, 
            contact_phone, screenshot_url, products_sold, enrichment_report,
            estimated_size, estimated_revenue, estimated_traffic
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (candidate_id) DO UPDATE SET
            contact_email     = COALESCE(EXCLUDED.contact_email,     leads.contact_email),
            contact_name      = COALESCE(EXCLUDED.contact_name,      leads.contact_name),
            contact_phone     = COALESCE(EXCLUDED.contact_phone,     leads.contact_phone),
            screenshot_url    = COALESCE(EXCLUDED.screenshot_url,    leads.screenshot_url),
            products_sold     = CASE WHEN cardinality(EXCLUDED.products_sold) > 0
                                     THEN EXCLUDED.products_sold ELSE leads.products_sold END,
            enrichment_report = COALESCE(EXCLUDED.enrichment_report, leads.enrichment_report),
            estimated_size    = COALESCE(EXCLUDED.estimated_size,    leads.estimated_size),
            estimated_revenue = COALESCE(EXCLUDED.estimated_revenue, leads.estimated_revenue),
            estimated_traffic = EXCLUDED.estimated_traffic,
            enriched_at   = now()
        """,
        (candidate_id, campaign_id, email, contact_name, phone, screenshot_url, products_sold, report, est_size, est_rev, est_traffic),
    )

    # ── Removed status update to 'enriched' per user request ────────────────

    logger.info(
        "Stage 5: enriched %s | email=%s contact=%s | campaign=%s",
        domain, email, contact_name, campaign_id,
    )
    return {
        "candidate_id": candidate_id,
        "domain": domain,
        "outcome": "enriched",
        "email": email,
        "contact_name": contact_name,
    }


def run() -> dict:
    """
    Poll all approved candidates and enrich them.
    Each candidate is processed in its own transaction so one failure
    doesn't roll back the others.
    """
    with db.get_conn() as conn:
        approved = db.fetchall(
            conn,
            """
            SELECT c.id, c.campaign_id, c.domain, c.company_name, c.status,
                   c.enrichment_attempt_count, c.enrichment_attempted_at,
                   camp.id as camp_id, camp.business_brief, camp.slug, camp.settings,
                   l.id as existing_lead_id,
                   l.enrichment_report as existing_enrichment_report,
                   (
                       SELECT evidence_data
                       FROM evaluations
                       WHERE candidate_id = c.id
                       ORDER BY created_at DESC
                       LIMIT 1
                   ) as eval_evidence
            FROM candidates c
            JOIN campaigns camp ON camp.id = c.campaign_id
            LEFT JOIN leads l ON l.candidate_id = c.id
            WHERE c.status IN ('pending_review', 'approved')
            ORDER BY c.created_at ASC
            """,
        )

    campaign_ids = {c["campaign_id"] for c in approved}
    logger.info("Stage 5: Fetched %d candidates", len(approved))
    for cid in campaign_ids:
        db.set_stage_status(cid, "stage5", "running")

    try:
        results = []
        def process_cand(candidate):
            if db.check_stop_signal(candidate["campaign_id"], "stage5"):
                logger.info("Stage 5 stopped via dashboard signal for campaign %s", candidate["campaign_id"])
                return None

            try:
                with db.get_conn() as conn:
                    # LOGIC-01: Skip if already fully enriched — avoids wasting Firecrawl/LLM credits
                    if candidate.get("existing_lead_id") and candidate.get("existing_enrichment_report"):
                        logger.debug(
                            "Stage 5: candidate %s (%s) already has enrichment data, skipping",
                            candidate["id"], candidate["domain"],
                        )
                        return {"candidate_id": candidate["id"], "outcome": "skipped_already_enriched"}

                    # BUG-02 fix: build a proper campaign dict (separate from candidate)
                    campaign = {
                        "id": candidate["camp_id"],
                        "business_brief": candidate.get("business_brief"),
                        "slug": candidate.get("slug"),
                        "settings": candidate.get("settings"),
                    }
                    campaign_settings = candidate.get("settings") or {}
                    return _enrich_candidate(candidate, campaign, conn, settings=campaign_settings)
            except Exception as exc:
                logger.error("Stage 5: unexpected error for candidate %s: %s", candidate["id"], exc)
                return {"candidate_id": candidate["id"], "outcome": "error", "error": str(exc)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for res in executor.map(process_cand, approved):
                if res is None:
                    break
                results.append(res)

        summary = {
            "total": len(results),
            "enriched": sum(1 for r in results if r.get("outcome") == "enriched"),
            "firecrawl_failed_retry": sum(1 for r in results if r.get("outcome") == "firecrawl_failed_retry"),
            "enrichment_failed": sum(1 for r in results if r.get("outcome") == "enrichment_failed"),
            "skipped_dnc": sum(1 for r in results if r.get("outcome") == "skipped_dnc"),
            "skipped_cooldown": sum(1 for r in results if r.get("outcome") == "skipped_cooldown"),
            "details": results,
        }
        logger.info("Stage 5 run complete: %s", summary)
        return summary
    finally:
        for cid in campaign_ids:
            db.set_stage_status(cid, "stage5", "idle")
