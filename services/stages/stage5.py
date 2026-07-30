"""
stage5.py — Stage 5: Enrichment.

Polls candidates with status 'pending_review' or 'approved', for each:
  1. Check do_not_contact — skip if suppressed
  2. Skip if lead already has enrichment_report (already enriched — do not repeat)
  3. Skip if enrichment_attempted_at < ENRICHMENT_RETRY_HOURS ago (avoid hammering crawler)
  4. Increment enrichment_attempt_count + set enrichment_attempted_at BEFORE crawling
  5. Crawl4AI scrapes the domain's homepage (JS-rendered, returns markdown + images)
  6. extruct extracts JSON-LD/Schema.org metadata deterministically (avoids LLM tokens)
  7. LLM fills remaining gaps: company overview in Slovak, estimates, buying signals
  8. On success: upsert into leads table — candidate status is NOT changed (user reviews manually)
  9. On failure:
       - attempt_count < MAX_ENRICHMENT_ATTEMPTS → leave status unchanged (retry next cycle)
       - attempt_count >= MAX_ENRICHMENT_ATTEMPTS → set 'enrichment_failed'

Key improvement over v1 (Firecrawl):
  - Self-hosted Crawl4AI correctly renders JS/React storefronts (Firecrawl returned 20 chars; Crawl4AI returned 95k chars + 682 images for the same page)
  - extruct pre-extraction reduces LLM token cost by 30-50% on structured B2B sites
  - phonenumbers normalizes all extracted phone numbers to E.164 format
"""
import json
import logging
import requests
import concurrent.futures
import secrets
from typing import Optional

try:
    import phonenumbers
except ImportError:
    phonenumbers = None

import services.common.config as config
import db
import cost_log
import services.common.llm as llm
# STABILIZATION FIX: Extracted shared crawler client to break circular dependencies
import email_validator
import crawler_client
from crawler_client import crawler_scrape as _crawler_scrape, CONTACT_PATHS

logger = logging.getLogger(__name__)



def _screenshot_url(domain: str) -> str:
    """Return a screenshot URL via the local API proxy."""
    import urllib.parse
    encoded = urllib.parse.quote(f"https://{domain}", safe="")
    return f"/api/screenshot?url={encoded}"


CF_PATTERNS = [
    "just a moment", "checking your browser", "ddos-guard", "enable javascript", "attention required!",
    "moment strpenia", "skontrolujte váš prehliadač", "zkontrolujte svůj prohlížeč",
    "cloudflare", "ray id:", "security check"
]

def _is_bot_challenge(text: Optional[str]) -> bool:
    if not text:
        return False
    lower_text = text.lower()[:500]
    return any(p in lower_text for p in CF_PATTERNS)


def _has_valid_mx(domain: Optional[str]) -> Optional[bool]:
    """Check if the domain has valid MX DNS records."""
    if not domain:
        return None
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX')
        return bool(answers)
    except Exception:
        return False


def _scrape_domain(domain: str) -> tuple[Optional[str], str, Optional[list]]:
    """
    Try homepage with Crawl4AI. Returns (markdown_text, page_url, images_list).
    Returns (None, '', None) if crawl fails.
    """
    base = f"https://{domain}"
    # The crawler service handles trafilatura fast-path and automatically falls back 
    # to Playwright if the text is too short or if it's a SPA.
    text, images = _crawler_scrape(base, force_playwright=False)
    
    if text and len(text) > 200 and not _is_bot_challenge(text):
        return text, base, images

    logger.warning("Crawler failed on homepage %s or returned bot challenge. Aborting subpaths to save time.", base)
    return None, "", None


# ── extruct: Deterministic JSON-LD / Schema.org extraction ───────────────────

def _extract_structured_data(domain: str) -> dict:
    """
    Fetch the raw HTML and use extruct to pull Schema.org JSON-LD metadata.
    Returns a dict with any of: email, phone, address, name, description.
    No LLM tokens used — pure deterministic extraction.
    """
    try:
        import extruct
        from w3lib.html import get_base_url

        url = f"https://{domain}"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return {}

        base_url = get_base_url(resp.text, resp.url)
        data = extruct.extract(resp.text, base_url=base_url, syntaxes=["json-ld", "microdata", "opengraph"])

        result = {}

        # Scan JSON-LD for Organization / LocalBusiness schema
        for item in data.get("json-ld", []):
            schema_type = item.get("@type", "")
            if isinstance(schema_type, list):
                schema_type = " ".join(schema_type)
            if any(t in schema_type for t in ["Organization", "LocalBusiness", "Corporation", "Store"]):
                if item.get("email") and not result.get("email"):
                    result["email"] = item["email"].replace("mailto:", "").strip()
                if item.get("telephone") and not result.get("phone"):
                    result["phone"] = item["telephone"]
                if item.get("name") and not result.get("name"):
                    result["name"] = item["name"]
                if item.get("description") and not result.get("description"):
                    result["description"] = item["description"]
                addr = item.get("address") or {}
                if addr and not result.get("address"):
                    result["address"] = addr

        # OpenGraph fallback for name/description
        og = data.get("opengraph", [{}])
        if og and not result.get("name"):
            result["name"] = og[0].get("og:site_name") or og[0].get("og:title")
        if og and not result.get("description"):
            result["description"] = og[0].get("og:description")

        logger.info("extruct found for %s: %s", domain, list(result.keys()))
        return result

    except ImportError:
        logger.warning("extruct not installed — skipping structured data extraction")
        return {}
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        logger.warning("extruct network failed for %s: %s (domain is dead or unreachable)", domain, exc)
        return {"_network_error": True}
    except Exception as exc:
        logger.warning("extruct failed for %s: %s", domain, exc)
        return {}


# ── phonenumbers: E.164 normalization ────────────────────────────────────────

def _normalize_phone(raw_phone: Optional[str], default_region: str = "SK") -> Optional[str]:
    """
    Parse and normalize a phone number to E.164 format.
    Returns normalized string (e.g. '+421901234567') or original if parsing fails.
    """
    if not raw_phone or not phonenumbers:
        return raw_phone
    try:
        parsed = phonenumbers.parse(raw_phone, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return raw_phone
    except Exception:
        return raw_phone


# ── LLM extraction ─────────────────────────────────────────────────────────────

EXTRACT_PROMPT = """
You are enriching a business lead from their website content.

=== BEGIN SYSTEM INSTRUCTIONS ===
Company: {company_name} ({domain})

The following data was ALREADY extracted deterministically — do NOT override it unless you have stronger evidence:
Pre-extracted: {pre_extracted}

Extract the following (fill in gaps not already covered by pre-extracted data):
1. "email": A business email address (if found and not already in pre-extracted).
2. "name": A contact person's name (if mentioned).
3. "phone": A contact phone number (if not already in pre-extracted).
4. "products_sold": A list of strings detailing products or services they sell in Slovak language (be specific, up to 5 items).
5. "estimated_size": Estimate company size (e.g., '1-10', '11-50', '51-200', '201+').
6. "estimated_revenue": Estimate revenue bracket (e.g., '<€1M', '€1M - €10M', '€10M+').
7. "estimated_traffic": Estimate web traffic volume (e.g., 'Low', 'Medium', 'High').
8. "report": A single short sentence (max 15 words) in Slovak language stating what the company does and if they fit the offer: {offer_summary}. Be extremely concise, direct, and concrete. No filler phrases.
9. "firmographics": A JSON object containing specific firmographic data (e.g., "headquarters": "city", "year_founded": "YYYY").
10. "buying_power_signals": An array of strings describing signals like "public procurement", "multiple warehouses", etc.
11. "tech_stack": An array of strings with any technologies or e-commerce platforms mentioned.

Return ONLY valid JSON with keys: "email", "name", "phone", "products_sold", "estimated_size", "estimated_revenue", "estimated_traffic", "report", "firmographics", "buying_power_signals", "tech_stack".
No prose outside the JSON.
CRITICAL: "report" and "products_sold" MUST be written in Slovak language.
=== END SYSTEM INSTRUCTIONS ===

=== BEGIN USER DATA ===
{page_text}
=== END USER DATA ===
"""


def _enrich_info(domain: str, company_name: Optional[str], offer_summary: str, page_text: str, pre_extracted: dict) -> tuple[dict, int, int]:
    """Use the LLM to fill enrichment gaps not covered by extruct. Returns (result, tokens_in, tokens_out)."""
    prompt = EXTRACT_PROMPT.format(
        domain=domain,
        company_name=company_name or domain,
        offer_summary=offer_summary[:600],
        page_text=page_text[:4000],
        pre_extracted=json.dumps(pre_extracted, ensure_ascii=False),
    )
    try:
        result, ti, to, _, _ = llm.chat_json(prompt, model=config.STAGE5_MODEL)
        if isinstance(result, dict) and "_raw" not in result:
            return result, ti, to
        # HARDENING: LLM returned non-JSON or parse failure
        logger.warning(
            "LLM enrichment returned non-JSON for %s. Returning empty dict.", domain
        )
        return {}, ti, to
    except Exception as exc:
        logger.warning("LLM enrichment extraction failed for %s: %s", domain, exc)
        return {}, 0, 0


# ── Enrichment loop ────────────────────────────────────────────────────────────

def _get_offer_summary(business_brief: Optional[str]) -> str:
    if not business_brief:
        return "(offer not yet defined)"
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

    # ── Retry cooldown ─────────────────────────────────────────────────────────
    effective_settings = settings or {}
    retry_hours = int(effective_settings.get("enrichment_retry_hours", config.ENRICHMENT_RETRY_HOURS))
    max_attempts = int(effective_settings.get("max_enrichment_attempts", config.MAX_ENRICHMENT_ATTEMPTS))

    if candidate.get("enrichment_attempted_at") is not None:
        cooling = db.fetchone(
            conn,
            """
            SELECT enrichment_attempted_at < now() - make_interval(hours => %s) AS past_cooldown
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

    # ── Step 1: extruct — deterministic structured data extraction ────────────
    pre_extracted = _extract_structured_data(domain)
    cost_log.log_call(conn, "stage5", "crawler", campaign_id=campaign_id, query_count=1)

    if pre_extracted.pop("_network_error", False):
        logger.warning("Stage 5: %s is unreachable (network error), skipping crawler entirely.", domain)
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
        if new_attempt_count >= max_attempts:
            db.execute(conn, "UPDATE candidates SET status = 'enrichment_failed' WHERE id = %s", (candidate_id,))
            return {"candidate_id": candidate_id, "outcome": "enrichment_failed", "attempts": new_attempt_count}
        return {"candidate_id": candidate_id, "outcome": "network_error_retry", "attempts": new_attempt_count}

    # ── Step 2: Crawl page (use cache from eval if available) ─────────────────
    page_text = None
    page_url = None
    crawl_images = []
    eval_evidence = candidate.get("eval_evidence") or {}
    cached_pages = eval_evidence.get("cached_pages", {})

    if cached_pages:
        for path in CONTACT_PATHS:
            for cached_url, text in cached_pages.items():
                if cached_url.rstrip('/').endswith(path.rstrip('/')):
                    page_text = text
                    page_url = cached_url
                    break
            if page_text:
                break
        if not page_text and cached_pages:
            first_url = next(iter(cached_pages))
            page_text = cached_pages[first_url]
            page_url = first_url

    if not page_text:
        page_text, page_url, crawl_images = _scrape_domain(domain)
        cost_log.log_call(conn, "stage5", "crawler", campaign_id=campaign_id, query_count=1)
        screenshot_url = _screenshot_url(domain)
    else:
        logger.info("Stage 5: Using cached page scrape for %s", domain)
        screenshot_url = _screenshot_url(domain)

    if not page_text:
        # STABILIZATION FIX (BUG-009): Increment attempt count ONLY on legitimate crawl failure, not before crawling
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

        # Crawler failed
        if new_attempt_count >= max_attempts:
            db.execute(
                conn,
                "UPDATE candidates SET status = 'enrichment_failed' WHERE id = %s",
                (candidate_id,),
            )
            logger.warning("Stage 5: %s → enrichment_failed after %d attempts", domain, new_attempt_count)
            return {"candidate_id": candidate_id, "outcome": "enrichment_failed", "attempts": new_attempt_count}
        else:
            logger.warning(
                "Stage 5: Crawler failed for %s (attempt %d/%d) — leaving for retry",
                domain, new_attempt_count, max_attempts,
            )
            return {"candidate_id": candidate_id, "outcome": "crawler_failed_retry", "attempts": new_attempt_count}

    # ── Step 3: LLM — fill gaps not covered by extruct ───────────────────────
    offer_summary = _get_offer_summary(campaign.get("business_brief"))
    info, ti, to = _enrich_info(domain, candidate.get("company_name"), offer_summary, page_text, pre_extracted)
    cost_log.log_call(conn, "stage5", "gemini", campaign_id=campaign_id, tokens_in=ti, tokens_out=to)

    # Merge: prefer extruct values for contact fields, LLM for semantic fields
    email = pre_extracted.get("email") or info.get("email")
    phone_raw = pre_extracted.get("phone") or info.get("phone")
    phone = _normalize_phone(phone_raw)
    contact_name = info.get("name") or pre_extracted.get("name")

    # ── Step 4: Fallback contact path scraping if still no email ─────────────
    if not email:
        logger.info("Stage 5: Email not found for %s, trying contact paths...", domain)
        for path in CONTACT_PATHS[:3]:
            contact_url = f"https://{domain}{path}"
            contact_text, _ = _crawler_scrape(contact_url, force_playwright=False)
            cost_log.log_call(conn, "stage5", "crawler", campaign_id=campaign_id, query_count=1)

            if contact_text:
                contact_info, contact_ti, contact_to = _enrich_info(domain, candidate.get("company_name"), offer_summary, contact_text, {})
                cost_log.log_call(conn, "stage5", "gemini", campaign_id=campaign_id, tokens_in=contact_ti, tokens_out=contact_to)

                if contact_info.get("email") or contact_info.get("phone"):
                    email = contact_info.get("email") or email
                    phone = _normalize_phone(contact_info.get("phone")) or phone
                    contact_name = contact_info.get("name") or contact_name
                    logger.info("Stage 5: Found contact info on %s: email=%s phone=%s", path, email, phone)
                    break

    products_sold = info.get("products_sold") or []
    report = info.get("report")
    est_size = info.get("estimated_size")
    est_rev = info.get("estimated_revenue")
    est_traffic = info.get("estimated_traffic")

    # HARDENING: Zero-data guard — do not insert empty lead records that lock candidates out of retries
    if not email and not phone and not report and not products_sold:
        logger.warning("Stage 5: zero enrichment data extracted for %s — skipping lead insert to allow retry", domain)
        return {"candidate_id": candidate_id, "outcome": "zero_data_retry"}

    # ── Merge tech stack from evaluation evidence ─────────────────────────────
    firmographics = info.get("firmographics") or {}
    buying_power_signals = info.get("buying_power_signals") or []
    eval_tech_stack = eval_evidence.get("tech_stack") or []
    llm_tech_stack = info.get("tech_stack") or []
    combined_tech_stack = list(set(eval_tech_stack + llm_tech_stack))
    cold_email_hook = eval_evidence.get("cold_email_hook")

    # Merge crawled product images into evidence for dashboard display
    existing_evidence_images = eval_evidence.get("images_analyzed") or []
    merged_images = list(dict.fromkeys(existing_evidence_images + (crawl_images or [])))[:20]

    email_quality = email_validator.classify_email(email) if email else None
    email_domain = email.split("@")[-1] if email and "@" in email else None
    mx_valid = _has_valid_mx(email_domain) if email_domain else None

    # ── Insert into leads ─────────────────────────────────────────────────────
    db.execute(
        conn,
        """
        INSERT INTO leads (
            candidate_id, campaign_id, contact_email, contact_name,
            contact_phone, screenshot_url, products_sold, enrichment_report,
            estimated_size, estimated_revenue, estimated_traffic,
            firmographics, buying_power_signals, tech_stack, cold_email_hook, email_quality, mx_valid
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            firmographics     = COALESCE(EXCLUDED.firmographics,     leads.firmographics),
            buying_power_signals = CASE WHEN cardinality(EXCLUDED.buying_power_signals) > 0
                                        THEN EXCLUDED.buying_power_signals ELSE leads.buying_power_signals END,
            tech_stack        = CASE WHEN cardinality(EXCLUDED.tech_stack) > 0
                                     THEN EXCLUDED.tech_stack ELSE leads.tech_stack END,
            cold_email_hook   = COALESCE(EXCLUDED.cold_email_hook,   leads.cold_email_hook),
            email_quality     = COALESCE(EXCLUDED.email_quality,     leads.email_quality),
            mx_valid          = COALESCE(EXCLUDED.mx_valid,          leads.mx_valid),
            enriched_at       = now()
        """,
        (candidate_id, campaign_id, email, contact_name, phone, screenshot_url, products_sold, report,
         est_size, est_rev, est_traffic, json.dumps(firmographics), buying_power_signals, combined_tech_stack, cold_email_hook, email_quality, mx_valid),
    )

    # Update evaluations evidence with merged product images for dashboard display
    if crawl_images:
        db.execute(
            conn,
            """
            UPDATE evaluations SET evidence_data = jsonb_set(
                COALESCE(evidence_data, '{}'),
                '{images_analyzed}',
                %s::jsonb,
                true
            )
            WHERE id = (
                SELECT id FROM evaluations
                WHERE candidate_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            )
            """,
            (json.dumps(merged_images), candidate_id),
        )


    # Generate Phase X audit_token
    audit_token = secrets.token_hex(32)

    # STABILIZATION FIX (BUG-009): Update enrichment_attempted_at timestamp on candidate post-success
    db.execute(
        conn,
        """
        UPDATE candidates SET 
            enrichment_attempted_at = now(),
            audit_token = COALESCE(audit_token, %s),
            audit_token_created = COALESCE(audit_token_created, now())
        WHERE id = %s
        """,
        (audit_token, candidate_id),
    )

    logger.info(
        "Stage 5: enriched %s | email=%s contact=%s phone=%s images=%d | campaign=%s",
        domain, email, contact_name, phone, len(crawl_images or []), campaign_id,
    )
    return {
        "candidate_id": candidate_id,
        "domain": domain,
        "outcome": "enriched",
        "email": email,
        "contact_name": contact_name,
        "phone": phone,
        "images_found": len(crawl_images or []),
    }


# ── Crash recovery ─────────────────────────────────────────────────────────────

def _recover_stuck_enrichments(conn):
    """
    On service startup or run start, decrement attempt count for candidates that were
    'started but never finished' due to a crash (enrichment_attempted_at set
    but still no enrichment_report).
    Only recovers candidates for campaigns that are NOT currently 'running' to
    avoid clobbering live work.
    """
    count = db.execute(
        conn,
        """
        UPDATE candidates
        SET enrichment_attempt_count = GREATEST(0, enrichment_attempt_count - 1),
            enrichment_attempted_at  = NULL
        WHERE enrichment_attempted_at IS NOT NULL
          AND id NOT IN (SELECT candidate_id FROM leads WHERE enrichment_report IS NOT NULL)
          AND status IN ('evaluated', 'pending_review', 'approved')
          AND campaign_id IN (
              SELECT id FROM campaigns WHERE stage5_status != 'running'
          )
        """,
    )
    if count > 0:
        logger.warning("Stage 5 crash recovery: reset %d stuck enrichment attempts.", count)


# ── Main run loop ──────────────────────────────────────────────────────────────

def run(campaign_id: Optional[int] = None) -> dict:
    """
    Poll all approved candidates and enrich them.
    Each candidate is processed in its own transaction so one failure
    doesn't roll back the others.
    """
    # Crash recovery on every run start
    with db.get_conn() as conn:
        _recover_stuck_enrichments(conn)

    with db.get_conn() as conn:
        if campaign_id:
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
                WHERE c.status IN ('evaluated', 'pending_review', 'approved')
                  AND c.campaign_id = %s
                ORDER BY c.created_at ASC
                """,
                (campaign_id,)
            )
        else:
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
            WHERE c.status IN ('evaluated', 'pending_review', 'approved')
            ORDER BY c.created_at ASC
            """,
        )

    campaign_ids = {c["campaign_id"] for c in approved}
    locked_campaign_ids = set()
    logger.info("Stage 5: Fetched %d candidates across %d campaigns", len(approved), len(campaign_ids))
    for cid in campaign_ids:
        if not db.acquire_stage_lock(cid, "stage5"):
            logger.info("Stage 5 already running for campaign %s", cid)
            continue
        locked_campaign_ids.add(cid)

    # Only process candidates belonging to campaigns we successfully locked
    approved = [c for c in approved if c["campaign_id"] in locked_campaign_ids]

    try:
        results = []

        def process_cand(candidate):
            if db.check_stop_signal(candidate["campaign_id"], "stage5"):
                logger.info("Stage 5 stopped via dashboard signal for campaign %s", candidate["campaign_id"])
                return None
            try:
                with db.get_conn(autocommit=False) as conn:
                    if candidate.get("existing_lead_id") and candidate.get("existing_enrichment_report"):
                        logger.debug(
                            "Stage 5: candidate %s (%s) already enriched, skipping",
                            candidate["id"], candidate["domain"],
                        )
                        return {"candidate_id": candidate["id"], "outcome": "skipped_already_enriched"}

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

        # NOTE (S9): Use submit+cancel pattern to stop queued tasks. 
        # WARNING: f.cancel() only prevents unstarted futures from running. 
        # In-flight enrichment threads (up to 3) will run to completion. True interruption would require passing a cancellation token down.
        futures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            for candidate in approved:
                futures.append(executor.submit(process_cand, candidate))

            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res is None:
                    # Stop signal received — cancel all pending futures
                    for f in futures:
                        f.cancel()
                    break
                results.append(res)

        summary = {
            "total": len(results),
            "enriched": sum(1 for r in results if r.get("outcome") == "enriched"),
            "crawler_failed_retry": sum(1 for r in results if r.get("outcome") == "crawler_failed_retry"),
            "enrichment_failed": sum(1 for r in results if r.get("outcome") == "enrichment_failed"),
            "skipped_dnc": sum(1 for r in results if r.get("outcome") == "skipped_dnc"),
            "skipped_cooldown": sum(1 for r in results if r.get("outcome") == "skipped_cooldown"),
            "skipped_already_enriched": sum(1 for r in results if r.get("outcome") == "skipped_already_enriched"),
            "details": results,
        }
        logger.info("Stage 5 run complete: %s", summary)
        return summary
    finally:
        for cid in locked_campaign_ids:
            db.set_stage_status(cid, "stage5", "idle")
