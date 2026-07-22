"""
stage2.py — Stage 2: Target Finder.

Routes on campaigns.finder_type:
  - keyword_search  → Exa → Tavily → Serper/SerpAPI (site:*.hu) → Brave waterfall,
                      then Gemini dedup, then upsert into candidates.
  - code_signature_search → PublicWWW per malware_signatures row (WP-remediation).

Key constraints implemented here:
  - do_not_contact check (specific + global) before every insert
  - Upsert-with-WHERE for stale-reopen logic (exact SQL from §Part 2)
  - PublicWWW budget gate (checked before every batch)
  - api_call_log entry for every search provider call + every LLM call
"""
import json
import logging
import re
from typing import Optional
from urllib.parse import quote, urlparse

import requests
try:
    from exa_py import Exa
except ImportError:
    Exa = None

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

import config
import db
import cost_log
import llm

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> Optional[str]:
    """Extract apex domain from a URL. Returns None on failure."""
    try:
        parsed = urlparse(url if url.startswith("http") else "https://" + url)
        host = parsed.netloc or parsed.path
        # Strip www.
        host = re.sub(r"^www\.", "", host)
        # Remove port
        host = host.split(":")[0].strip()
        # Ensure it looks like a valid domain (no spaces, quotes, brackets, or HTML tags)
        if host and "." in host and not re.search(r"[<>\s\"'{}\(\)\[\]]", host):
            return host
        return None
    except Exception:
        return None


def _is_do_not_contact(conn, domain: str, campaign_id: int) -> bool:
    """Return True if domain is suppressed for this campaign or globally (NULL campaign_id)."""
    row = db.fetchone(
        conn,
        """
        SELECT 1 FROM do_not_contact
        WHERE (%s = domain OR %s LIKE '%%.' || domain)
          AND (campaign_id = %s OR campaign_id IS NULL)
        LIMIT 1
        """,
        (domain, domain, campaign_id),
    )
    return row is not None


import re as _re
_DOMAIN_RE = _re.compile(
    r'^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$'
)

def _upsert_candidate(
    conn,
    *,
    campaign_id: int,
    domain: str,
    company_name: Optional[str],
    source: str,
    query_used: str,
    evidence_data: dict,
) -> bool:
    """
    Attempt to upsert a candidate. Returns True if a new row was inserted
    or a stale row was re-opened; False if the row was left untouched
    (conflict with a non-stale/recent-stale existing row).

    Uses the exact SQL from §Part 2 — the WHERE clause on DO UPDATE is the mechanism.
    """
    # HARDENING: Validate domain shape before any DB write
    domain = domain.lower().strip()
    # Strip www. prefix if present
    if domain.startswith("www."):
        domain = domain[4:]
    # Reject paths, spaces, HTML artifacts, missing TLD
    if not _DOMAIN_RE.match(domain):
        logger.warning(
            "Rejecting invalid domain %r (failed regex) — source=%s campaign=%s",
            domain, source, campaign_id,
        )
        return False

    if _is_do_not_contact(conn, domain, campaign_id):
        logger.debug("Skipping %s — on do_not_contact list for campaign %s", domain, campaign_id)
        return False

    rows_affected = db.execute(
        conn,
        """
        INSERT INTO candidates
            (campaign_id, company_name, domain, source, query_used, evidence_data, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (campaign_id, domain) DO UPDATE SET
            last_seen_at  = now(),
            reopen_count  = candidates.reopen_count + 1,
            evidence_data = EXCLUDED.evidence_data
        WHERE candidates.status = 'stale'
          AND candidates.last_seen_at < now() - interval '%s days'
        """,
        (
            campaign_id,
            company_name,
            domain,
            source,
            query_used,
            json.dumps(evidence_data),
            config.STALE_REOPEN_DAYS,
        ),
    )
    return rows_affected > 0


# ── Search provider helpers ────────────────────────────────────────────────────

def _search_exa(query: str, conn, campaign_id: int) -> list[dict]:
    """Exa search. Returns list of {url, title, snippet} dicts."""
    if not config.EXA_API_KEY:
        return []
    try:
        exa = Exa(api_key=config.EXA_API_KEY)
        results = exa.search_and_contents(query, type="auto", use_autoprompt=False, num_results=10)
        cost_log.log_call(conn, "stage2", "exa", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.url, "title": getattr(r, "title", ""), "snippet": getattr(r, "text", "")[:300]}
            for r in results.results
        ]
    except Exception as exc:
        logger.warning("Exa search failed for query=%r: %s", query, exc)
        return []


def _search_tavily(query: str, conn, campaign_id: int) -> list[dict]:
    """Tavily search. Returns list of {url, title, snippet} dicts."""
    if not config.TAVILY_API_KEY:
        return []
    try:
        client = TavilyClient(api_key=config.TAVILY_API_KEY)
        resp = client.search(query, max_results=10)
        cost_log.log_call(conn, "stage2", "tavily", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("content", "")[:300]}
            for r in resp.get("results", [])
        ]
    except Exception as exc:
        logger.warning("Tavily search failed for query=%r: %s", query, exc)
        return []


def _search_serper(query: str, conn, campaign_id: int) -> list[dict]:
    """Serper (Google Search JSON) — raw HTTP."""
    if not config.SERPER_API_KEY:
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": 10},
            timeout=15,
        )
        resp.raise_for_status()
        cost_log.log_call(conn, "stage2", "serper", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")[:300]}
            for r in resp.json().get("organic", [])
        ]
    except Exception as exc:
        logger.warning("Serper search failed for query=%r: %s", query, exc)
        return []


def _search_serpapi(query: str, conn, campaign_id: int) -> list[dict]:
    """SerpAPI — raw HTTP (google-search-results SDK optional, raw is simpler)."""
    if not config.SERPAPI_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": config.SERPAPI_API_KEY, "engine": "google", "num": 10},
            timeout=15,
        )
        resp.raise_for_status()
        cost_log.log_call(conn, "stage2", "serpapi", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")[:300]}
            for r in resp.json().get("organic_results", [])
        ]
    except Exception as exc:
        logger.warning("SerpAPI search failed for query=%r: %s", query, exc)
        return []


def _search_brave(query: str, conn, campaign_id: int) -> list[dict]:
    """Brave Search — raw HTTP with Bearer token (as specified in §Part 2)."""
    if not config.BRAVE_SEARCH_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 10},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        cost_log.log_call(conn, "stage2", "brave", campaign_id=campaign_id, query_count=1)
        web = resp.json().get("web", {}).get("results", [])
        return [
            {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("description", "")[:300]}
            for r in web
        ]
    except Exception as exc:
        logger.warning("Brave search failed for query=%r: %s", query, exc)
        return []


# ── Keyword search waterfall ───────────────────────────────────────────────────

DEDUP_PROMPT = """
You are a ruthless B2B lead generation evaluator. Your ONLY job is to extract unique, independent B2B/B2C business domains from the provided search results.

CRITICAL DISQUALIFIERS - YOU MUST ABSOLUTELY EXCLUDE THESE:
1. ANY global e-commerce marketplace (Amazon, Walmart, eBay, Etsy, AliExpress, Target, Alza).
2. ANY directory, aggregator, or review site (Yelp, Trustpilot, TripAdvisor, Booking.com, Airbnb).
3. ANY social media platform or network (Facebook, Instagram, Twitter, X, LinkedIn, YouTube, Pinterest, Reddit, TikTok).
4. ANY informational wiki, news site, or blog (Wikipedia, Medium, WordPress).
5. ANY massive technology corporation (Google, Apple, Microsoft).

INCLUDE (positive signals):
- Real, independent B2B or local businesses with their own standalone domain.
- For Hungarian-language queries, prefer .hu TLD domains.

Each item must be a real company that could plausibly be a sales lead.

Return a JSON array where each element has:
  - "domain": apex domain only (e.g. "example.com"), no www prefix, no path
  - "company_name": company name if determinable from the title/snippet, else null

Results:
{results_json}

Return ONLY a valid JSON array. No prose, no markdown fences.
"""


def _llm_dedup(raw_results: list[dict], conn, campaign_id: int) -> list[dict]:
    """
    Use LLM to extract and deduplicate domain/company pairs from raw search hits.
    Returns list of {"domain": str, "company_name": str|None}.
    """
    if not raw_results:
        return []

    # Pre-deduplicate by exact URL to save tokens
    seen_urls = set()
    unique_raw = []
    for r in raw_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_raw.append(r)

    batch_size = 50
    final_parsed = []

    for i in range(0, len(unique_raw), batch_size):
        batch = unique_raw[i:i + batch_size]
        try:
            parsed, ti, to = llm.chat_json(
                DEDUP_PROMPT.format(results_json=json.dumps(batch, ensure_ascii=False)),
                temperature=0.1,
                model=config.STAGE2_DEDUP_MODEL,
            )
            cost_log.log_call(
                conn, "stage2", "gemini",
                campaign_id=campaign_id,
                model=config.STAGE2_DEDUP_MODEL,
                tokens_in=ti,
                tokens_out=to,
            )
            if isinstance(parsed, dict) and "_raw" in parsed:
                # HARDENING: LLM returned non-JSON; treat as batch failure
                logger.warning(
                    "LLM dedup batch %d returned non-JSON (_raw key present). "
                    "Falling back to raw domain extraction for this batch.",
                    i // batch_size,
                )
                for r in batch:
                    domain = _extract_domain(r.get("url", ""))
                    if domain:
                        final_parsed.append({"domain": domain, "company_name": None})
            elif isinstance(parsed, list):
                final_parsed.extend(parsed)
            else:
                logger.warning("LLM dedup returned unexpected type %s; skipping batch.", type(parsed))
        except Exception as exc:
            logger.warning("LLM dedup failed for batch: %s — falling back to raw domain extraction", exc)
            for r in batch:
                domain = _extract_domain(r.get("url", ""))
                if domain:
                    final_parsed.append({"domain": domain, "company_name": None})

    # Final deduplication by domain
    seen_domains = set()
    out = []
    for item in final_parsed:
        domain = item.get("domain")
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            out.append(item)
    return out


def _keyword_search(campaign_id: int, conn, cooldown_days: int = 30) -> dict:
    """
    Run the keyword_search finder for a campaign.
    Fetches the latest icp_config keywords, runs the waterfall, deduplicates,
    and upserts candidates.
    Skips any query that was already run within `cooldown_days` days.
    """
    # Load latest ICP
    icp = db.fetchone(
        conn,
        """
        SELECT keywords_hu, keywords_en, version
        FROM icp_config
        WHERE campaign_id = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (campaign_id,),
    )
    if not icp:
        raise ValueError(f"No icp_config found for campaign {campaign_id}. Run Stage 1 first.")

    all_raw: list[dict] = []
    queries_run: list[str] = []
    queries_skipped: list[str] = []

    def run_waterfall(query: str, is_hu_site: bool = False) -> bool:
        """Run one query through the provider waterfall, accumulating raw results. Returns True if stopped."""
        if db.check_stop_signal(campaign_id, "stage2"):
            logger.info("Stage 2 stopped via dashboard signal.")
            return True

        # ── Cooldown gate ──────────────────────────────────────────────────────
        already_run = db.fetchone(
            conn,
            """
            SELECT last_run_at FROM search_queries_log
            WHERE campaign_id = %s AND query = %s
              AND last_run_at > now() - %s::interval
            """,
            (campaign_id, query, f"{cooldown_days} days"),
        )
        if already_run:
            logger.info(
                "Skipping query %r — already run within the last %d days (last: %s)",
                query,
                cooldown_days,
                already_run["last_run_at"],
            )
            queries_skipped.append(query)
            return False  # H3: explicit False, not implicit None

        hits: list[dict] = []

        # 1. Exa
        exa_hits = _search_exa(query, conn, campaign_id)
        hits.extend(exa_hits)
        logger.info("Exa: %d hits for %r", len(exa_hits), query)

        # 2. Tavily (if under threshold)
        if len(exa_hits) < config.KEYWORD_MIN_HITS:
            if db.check_stop_signal(campaign_id, "stage2"):
                logger.info("Stage 2 stopped via dashboard signal.")
                return True
            tav_hits = _search_tavily(query, conn, campaign_id)
            hits.extend(tav_hits)
            logger.info("Tavily: %d hits for %r", len(tav_hits), query)

        # 3. Serper (always, for coverage; SerpAPI used for site:*.hu queries)
        serper_hits = _search_serper(query, conn, campaign_id)
        hits.extend(serper_hits)

        if is_hu_site:
            # SerpAPI with site:*.hu modifier
            site_query = f"{query} site:*.hu"
            serpapi_hits = _search_serpapi(site_query, conn, campaign_id)
            hits.extend(serpapi_hits)
            logger.info("SerpAPI site:*.hu: %d hits for %r", len(serpapi_hits), site_query)

        # 4. Brave (coverage)
        brave_hits = _search_brave(query, conn, campaign_id)
        hits.extend(brave_hits)

        all_raw.extend(hits)
        queries_run.append(query)

        # ── Log this query run ─────────────────────────────────────────────────
        db.execute(
            conn,
            """
            INSERT INTO search_queries_log (campaign_id, query)
            VALUES (%s, %s)
            ON CONFLICT (campaign_id, query) DO UPDATE SET last_run_at = now()
            """,
            (campaign_id, query),
        )

    # Run HU keywords
    for kw in (icp["keywords_hu"] or []):
        if run_waterfall(kw, is_hu_site=True):
            break

    # Run EN keywords
    if not db.check_stop_signal(campaign_id, "stage2"):
        for kw in (icp["keywords_en"] or []):
            if run_waterfall(kw, is_hu_site=False):
                break

    # ── Housekeeping: trim log entries older than 2× cooldown ─────────────────
    db.execute(
        conn,
        """
        DELETE FROM search_queries_log
        WHERE campaign_id = %s AND last_run_at < now() - interval '%s days'
        """,
        (campaign_id, cooldown_days * 2),
    )

    # LLM dedup
    candidates_data = _llm_dedup(all_raw, conn, campaign_id)
    logger.info(
        "After LLM dedup: %d unique domains from %d raw hits (%d queries skipped by cooldown)",
        len(candidates_data), len(all_raw), len(queries_skipped),
    )

    inserted = 0
    skipped_existing = 0

    for item in candidates_data:
        domain = item.get("domain")
        if not domain:
            continue
        company_name = item.get("company_name")

        evidence = {
            "search_queries": queries_run,
            "icp_version": icp["version"],
        }
        ok = _upsert_candidate(
            conn,
            campaign_id=campaign_id,
            domain=domain,
            company_name=company_name,
            source="keyword_search",
            query_used=", ".join(queries_run[:3]),  # truncate for readability
            evidence_data=evidence,
        )
        if ok:
            inserted += 1
        else:
            # skipped_existing covers both "already present" and DNC-suppressed cases
            # since _upsert_candidate handles the DNC check internally
            skipped_existing += 1

    return {
        "campaign_id": campaign_id,
        "finder_type": "keyword_search",
        "queries_run": len(queries_run),
        "queries_skipped": len(queries_skipped),
        "raw_hits": len(all_raw),
        "unique_domains": len(candidates_data),
        "inserted_or_reopened": inserted,
        "skipped_existing": skipped_existing,
    }


# ── Code-signature search (PublicWWW) ─────────────────────────────────────────

def _publicwww_search(snippet: str) -> list[str]:
    """
    Query PublicWWW for websites containing snippet.
    Returns list of domain strings.

    Uses pypublicwww which constructs the correct URL:
      https://publicwww.com/websites/{encoded_query}/?export=csvu&key={KEY}
    Note: 'csvu' and 'key=' are the correct params (not 'csv' + 'apikey=').
    Requires a paid PublicWWW plan — free plan returns 0 results.
    """
    if not config.PUBLICWWW_API_KEY:
        logger.warning("PUBLICWWW_API_KEY not set — skipping signature search")
        return []

    try:
        from pypublicwww import PyPublicWWW
        api = PyPublicWWW(apikey=config.PUBLICWWW_API_KEY, timeout=30)
        csv_text = api._search_websites(snippet, csv=True)

        # Guard: API returns a plain-text error on free/exhausted plans
        if not csv_text or "API available for paid" in csv_text or csv_text.startswith("<"):
            logger.warning(
                "PublicWWW returned no usable data for snippet=%r (plan limit or HTML page). "
                "Response preview: %r",
                snippet[:60],
                csv_text[:120] if csv_text else "",
            )
            return []

        # HARDENING: Validate that response looks like CSV, not HTML/JSON
        first_nonblank = csv_text.lstrip()
        if first_nonblank and first_nonblank[0] in ("<", "{", "["):
            logger.warning(
                "PublicWWW response starts with %r — likely HTML/JSON error page. "
                "Snippet: %r",
                first_nonblank[0],
                first_nonblank[:120],
            )
            return []

        domains = []
        for line in csv_text.strip().splitlines():
            if line.startswith("url,"):  # skip header row
                continue
            # HARDENING: csvu format uses semicolons as delimiter, not commas
            # Format: url;ranking (e.g. "https://example.com;1234")
            parts = line.split(";")
            if parts and parts[0]:
                domain = _extract_domain(parts[0].strip())
                if domain:
                    domains.append(domain)

        logger.info("PublicWWW returned %d domains for snippet=%r", len(domains), snippet[:60])
        return domains

    except Exception as exc:
        logger.error("PublicWWW query failed for snippet=%r: %s", snippet[:60], exc)
        return []


def _signature_search(campaign_id: int, conn) -> dict:
    """
    Run code_signature_search for a campaign.
    For each malware_signatures row, query PublicWWW (if budget allows),
    log the call, and upsert candidates with evidence_data.
    """
    if db.check_stop_signal(campaign_id, "stage2"):
        logger.info("Stage 2 stopped via dashboard signal.")
        return {
            "campaign_id": campaign_id,
            "finder_type": "code_signature_search",
            "signatures_checked": 0,
            "signatures_skipped_budget": 0,
            "inserted_or_reopened": 0,
        }

    signatures = db.fetchall(
        conn,
        "SELECT id, snippet, malware_family, confidence FROM malware_signatures WHERE campaign_id = %s",
        (campaign_id,),
    )
    if not signatures:
        return {"campaign_id": campaign_id, "finder_type": "code_signature_search", "signatures_checked": 0}

    total_inserted = 0
    total_skipped_budget = 0
    signatures_checked = 0

    for sig in signatures:
        # Budget gate — check before every signature query (§Part 2)
        if not cost_log.publicwww_budget_ok(conn, campaign_id=campaign_id):
            logger.warning(
                "PublicWWW budget exhausted — deferring remaining %d signature queries to next run",
                len(signatures) - signatures_checked,
            )
            total_skipped_budget = len(signatures) - signatures_checked
            break

        if db.check_stop_signal(campaign_id, "stage2"):
            logger.info("Stage 2 stopped via dashboard signal.")
            break

        logger.info("Querying PublicWWW for signature id=%s family=%s", sig["id"], sig["malware_family"])
        domains = _publicwww_search(sig["snippet"])

        # Log the query regardless of hit count
        cost_log.log_call(conn, "stage2", "publicwww", campaign_id=campaign_id, query_count=1)
        signatures_checked += 1

        for domain in domains:
            if _is_do_not_contact(conn, domain, campaign_id):
                continue

            evidence = {
                "matched_signatures": [
                    {
                        "signature_id": sig["id"],
                        "snippet": sig["snippet"][:200],
                        "malware_family": sig["malware_family"],
                        "confidence": sig["confidence"],
                    }
                ]
            }
            ok = _upsert_candidate(
                conn,
                campaign_id=campaign_id,
                domain=domain,
                company_name=None,
                source="code_signature_search",
                query_used=f"publicwww:sig:{sig['id']}",
                evidence_data=evidence,
            )
            if ok:
                total_inserted += 1

    return {
        "campaign_id": campaign_id,
        "finder_type": "code_signature_search",
        "signatures_checked": signatures_checked,
        "signatures_skipped_budget": total_skipped_budget,
        "inserted_or_reopened": total_inserted,
    }


# ── Public entry points ────────────────────────────────────────────────────────

def run(campaign_id: int) -> dict:
    """Run Stage 2 for a specific campaign. Routes on finder_type."""
    db.set_stage_status(campaign_id, "stage2", "running")
    try:
        with db.get_conn() as conn:
            campaign = db.fetchone(
                conn,
                "SELECT id, slug, status, finder_type, settings FROM campaigns WHERE id = %s",
                (campaign_id,),
            )
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")
            if campaign["status"] == "draft":
                raise ValueError(
                    f"Campaign '{campaign['slug']}' is status='draft'. "
                    "Stage 2 skipped — fill in business brief first."
                )

            finder_type = campaign["finder_type"]
            # Read campaign-level settings; fall back to config defaults
            settings = campaign.get("settings") or {}
            cooldown_days = int(settings.get("search_cooldown_days", config.SEARCH_COOLDOWN_DAYS))
            logger.info(
                "Stage 2: campaign=%s finder_type=%s cooldown_days=%d",
                campaign_id, finder_type, cooldown_days,
            )

            if finder_type == "keyword_search":
                return _keyword_search(campaign_id, conn, cooldown_days=cooldown_days)
            elif finder_type == "code_signature_search":
                return _signature_search(campaign_id, conn)
            else:
                raise ValueError(f"Unknown finder_type: {finder_type!r}")
    except Exception:
        db.set_stage_status(campaign_id, "stage2", "failed")
        raise
    else:
        db.set_stage_status(campaign_id, "stage2", "idle")


def run_all() -> list[dict]:
    """Run Stage 2 for all active campaigns (called by n8n cron)."""
    with db.get_conn() as conn:
        campaigns = db.fetchall(
            conn,
            "SELECT id, slug, finder_type FROM campaigns WHERE status = 'active'",
        )

    results = []
    for c in campaigns:
        try:
            result = run(c["id"])
            results.append(result)
        except Exception as exc:
            logger.error("Stage 2 failed for campaign %s: %s", c["id"], exc)
            results.append({"campaign_id": c["id"], "error": str(exc)})
    return results
