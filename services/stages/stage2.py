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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import requests
try:
    from exa_py import Exa
except ImportError:
    Exa = None

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

import services.common.config as config
import db
import cost_log
import services.common.llm as llm

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

# TLDs and domain patterns that are out-of-scope for the WP-remediation ICP.
# These are non-English-market or government TLDs unlikely to buy cleanup services.
_OUT_OF_SCOPE_TLDS = frozenset([
    "cn", "ru", "jp", "kr", "vn", "th", "id", "pk", "bd",
    "ir", "kz", "uz", "az", "ge", "am", "by", "md",
    "gov",  # generic govt TLD
])
_OUT_OF_SCOPE_SLD_PATTERNS = [
    ".gov.",   # gov.cn, gov.uk sub-domains, etc.
    ".edu.",   # edu.cn, edu.ru, etc.
    ".mil.",   # military domains
]

# TLDs for "Western" / high-wealth / English-fluent countries
_WESTERN_TLDS = frozenset([
    # 10 richest European countries + additions
    "lu", "ie", "ch", "no", "dk", "nl", "is", "at", "se", "de",
    "cz", "pl", "hu", "sk", "fi",
    # 10 richest/fluent English worldwide
    "us", "ca", "au", "nz", "sg", "hk", "ae", "il", "za", "uk",
    # Global/Generic TLDs
    "com", "org", "net", "co", "io", "eu", "info"
])

def _is_out_of_scope_domain(domain: str, western_tld_filter_enabled: bool = False) -> bool:
    """
    Returns True if the domain is outside the ICP geographic/institutional scope.
    Blocks .cn, .ru, .jp etc. and government/edu sub-domains.
    If western_tld_filter_enabled is True, it strictly whitelists _WESTERN_TLDS.
    """
    domain_lower = domain.lower()
    # Check country-code TLD (last label)
    tld = domain_lower.rsplit(".", 1)[-1]
    
    if western_tld_filter_enabled and tld not in _WESTERN_TLDS:
        return True

    if tld in _OUT_OF_SCOPE_TLDS:
        return True
    # Check second-level domain patterns (e.g. gov.cn, edu.br)
    for pattern in _OUT_OF_SCOPE_SLD_PATTERNS:
        if pattern in domain_lower:
            return True
    return False


def _extract_domain(url: str) -> Optional[str]:
    """Extract registered apex domain from a URL, stripping subdomains. Returns None on failure."""
    try:
        parsed = urlparse(url if url.startswith("http") else "https://" + url)
        host = (parsed.netloc or parsed.path).split(":")[0].strip()
        import tldextract
        ext = tldextract.extract(host)
        top_domain = getattr(ext, "top_domain_under_public_suffix", "") or getattr(ext, "registered_domain", "")
        if top_domain and not re.search(r"[<>\s\"'{}\(\)\[\]]", top_domain):
            return top_domain.lower()
        return None
    except Exception:
        return None


def _is_do_not_contact(conn, domain: str, campaign_id: int) -> bool:
    """Return True if domain is suppressed for this campaign or globally (NULL campaign_id)."""
    row = db.fetchone(
        conn,
        """
        SELECT 1 FROM do_not_contact
        WHERE (LOWER(%s) = LOWER(domain) OR %s LIKE '%%.' || domain)
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
    western_tld_filter_enabled: bool = False,
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

    # Filter out subdomains using tldextract (e.g. discard "sub.example.com", keep "example.com")
    import tldextract
    ext = tldextract.extract(domain)
    # The domain must just have domain and suffix. Subdomain must be empty or 'www'
    if ext.subdomain and ext.subdomain != 'www':
        logger.debug(
            "Skipping %s — is a subdomain (source=%s campaign=%s)",
            domain, source, campaign_id,
        )
        return False

    # ICP geo pre-filter — reject out-of-scope TLDs before any DB write
    if _is_out_of_scope_domain(domain, western_tld_filter_enabled):
        logger.debug(
            "Skipping %s — out-of-scope TLD/domain for ICP (source=%s campaign=%s)",
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
          AND candidates.last_seen_at < now() - make_interval(days => %s)
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

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
def _search_exa(query: str, conn, campaign_id: int) -> list[dict]:
    """Exa search. Returns list of {url, title, snippet} dicts."""
    if not config.EXA_API_KEY:
        return []
    try:
        exa = Exa(api_key=config.EXA_API_KEY)
        results = exa.search_and_contents(query, type="auto", num_results=10)
        cost_log.log_call(conn, "stage2", "exa", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.url, "title": getattr(r, "title", ""), "snippet": getattr(r, "text", "")[:300]}
            for r in results.results
        ]
    except Exception as exc:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status == 429 or "429" in str(exc) or "rate" in str(exc).lower():
            logger.error("Exa RATE LIMIT EXCEEDED for query=%r: %s", query, exc)
        else:
            logger.warning("Exa search failed for query=%r: %s", query, exc)
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
def _search_tavily(query: str, conn, campaign_id: int) -> list[dict]:
    """Tavily search. Returns list of {url, title, snippet} dicts."""
    if not config.TAVILY_API_KEY:
        return []
    try:
        client = TavilyClient(api_key=config.TAVILY_API_KEY)
        resp = client.search(query, max_results=10, timeout=15)
        cost_log.log_call(conn, "stage2", "tavily", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("content", "")[:300]}
            for r in resp.get("results", [])
        ]
    except Exception as exc:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status == 429 or "429" in str(exc) or "rate" in str(exc).lower():
            logger.error("Tavily RATE LIMIT EXCEEDED for query=%r: %s", query, exc)
        else:
            logger.warning("Tavily search failed for query=%r: %s", query, exc)
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
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
        if resp.status_code == 429:
            logger.error("Serper RATE LIMIT EXCEEDED (429) for query=%r", query)
            return []
        resp.raise_for_status()
        cost_log.log_call(conn, "stage2", "serper", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")[:300]}
            for r in resp.json().get("organic", [])
        ]
    except Exception as exc:
        logger.warning("Serper search failed for query=%r: %s", query, exc)
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
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
        if resp.status_code == 429:
            logger.error("SerpAPI RATE LIMIT EXCEEDED (429) for query=%r", query)
            return []
        resp.raise_for_status()
        cost_log.log_call(conn, "stage2", "serpapi", campaign_id=campaign_id, query_count=1)
        return [
            {"url": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")[:300]}
            for r in resp.json().get("organic_results", [])
        ]
    except Exception as exc:
        logger.warning("SerpAPI search failed for query=%r: %s", query, exc)
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception), reraise=False)
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
        if resp.status_code == 429 or resp.headers.get("x-ratelimit-remaining") == "0":
            logger.error("Brave RATE LIMIT EXCEEDED (429/quota) for query=%r", query)
            return []
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
            parsed, ti, to, _, _ = llm.chat_json(
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


def _keyword_search(campaign_id: int, conn, cooldown_days: int = 30, western_tld_filter_enabled: bool = False) -> dict:
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
        if len(hits) > 0:
            db.execute(
                conn,
                """
                INSERT INTO search_queries_log (campaign_id, query, query_yield_count)
                VALUES (%s, %s, %s)
                ON CONFLICT (campaign_id, query) DO UPDATE SET last_run_at = now(), query_yield_count = EXCLUDED.query_yield_count
                """,
                (campaign_id, query, len(hits)),
            )
        else:
            logger.warning("Query %r yielded 0 hits (likely rate limited). Not logging to cooldown.", query)

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
        WHERE campaign_id = %s AND last_run_at < now() - make_interval(days => %s)
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
            western_tld_filter_enabled=western_tld_filter_enabled,
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


# ── Code-signature search (PublicWWW & Fallback) ────────────────────────────────

FALLBACK_FILTER_PROMPT = """
You are a cybersecurity intelligence filter. Your job is to review search engine results for a malware signature query and filter out security blogs, news sites, malware analysis reports, and GitHub repositories discussing the malware.
Your ONLY output should be a JSON array of domains that belong to ACTUAL INFECTED WEBSITES.

CRITICAL DISQUALIFIERS - EXCLUDE THESE:
1. ANY security vendor blog (Wordfence, Sucuri, Malwarebytes, Kaspersky, etc.)
2. ANY news/tech reporting site (BleepingComputer, The Hacker News)
3. ANY code repository or forum (GitHub, StackOverflow, Reddit)
4. ANY site that looks like it is writing an article *about* the malware.

INCLUDE:
- Regular businesses (e-commerce, local businesses, non-tech companies) that appear to have accidentally exposed the malware snippet in their search snippet or URL.

Results:
{results_json}

Return ONLY a valid JSON array of apex domains. No prose.
Example: ["infected-bakery.com", "hacked-plumber.hu"]
"""

def _llm_filter_security_blogs(raw_results: list[dict], conn, campaign_id: int) -> list[str]:
    if not raw_results:
        return []
    
    unique_raw = []
    seen_urls = set()
    for r in raw_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_raw.append(r)
            
    batch_size = 50
    final_domains = []
    
    for i in range(0, len(unique_raw), batch_size):
        batch = unique_raw[i:i + batch_size]
        try:
            parsed, ti, to, _, _ = llm.chat_json(
                FALLBACK_FILTER_PROMPT.format(results_json=json.dumps(batch, ensure_ascii=False)),
                temperature=0.1,
                model=config.STAGE2_DEDUP_MODEL,
            )
            cost_log.log_call(conn, "stage2", "gemini", campaign_id=campaign_id, model=config.STAGE2_DEDUP_MODEL, tokens_in=ti, tokens_out=to)
            if isinstance(parsed, list):
                final_domains.extend(parsed)
        except Exception as exc:
            logger.warning("LLM fallback filter failed: %s", exc)
            
    out = []
    for d in final_domains:
        if isinstance(d, str):
            clean = _extract_domain(d)
            if clean and clean not in out:
                out.append(clean)
    return out

def _fallback_signature_search(snippet: str, conn, campaign_id: int) -> list[str]:
    clean_snippet = snippet.replace('\n', ' ').replace('\r', '').strip()
    query = f'"{clean_snippet[:50]}"'
    
    hits = []
    hits.extend(_search_exa(query, conn, campaign_id))
    hits.extend(_search_tavily(query, conn, campaign_id))
    hits.extend(_search_serper(query, conn, campaign_id))
    hits.extend(_search_brave(query, conn, campaign_id))
    
    domains = _llm_filter_security_blogs(hits, conn, campaign_id)
    logger.info("Fallback search returned %d domains after filtering for snippet=%r", len(domains), clean_snippet[:50])
    return domains


def _publicwww_search(snippet: str) -> list[str]:
    """
    Query PublicWWW for websites containing snippet.
    Returns list of domain strings.

    ALWAYS wraps snippet in double-quotes for exact phrase matching.
    Unquoted searches return orders-of-magnitude more false positives.

    Uses pypublicwww which constructs the correct URL:
      https://publicwww.com/websites/{encoded_query}/?export=csvu&key={KEY}
    Note: 'csvu' and 'key=' are the correct params (not 'csv' + 'apikey=').
    Requires a paid PublicWWW plan — free plan returns 0 results.
    """
    if not config.PUBLICWWW_API_KEY:
        logger.warning("PUBLICWWW_API_KEY not set — skipping signature search")
        return []

    # SIGNAL QUALITY: Always use exact-phrase (quoted) search.
    # Raw unquoted searches match substrings across token boundaries, causing
    # massive false positives (e.g. every WP site matching a generic JS pattern).
    quoted_snippet = f'"{snippet}"' if not snippet.startswith('"') else snippet

    try:
        from pypublicwww import PyPublicWWW
        api = PyPublicWWW(apikey=config.PUBLICWWW_API_KEY, timeout=30)
        csv_text = api._search_websites(quoted_snippet, csv=True)

        # Guard: API returns a plain-text error on free/exhausted plans
        if not csv_text or "API available for paid" in csv_text or csv_text.startswith("<"):
            logger.warning(
                "PublicWWW returned no usable data for snippet=%r (plan limit or HTML page). "
                "Response preview: %r",
                quoted_snippet[:60],
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

        raw_count = len(domains)
        logger.info(
            "PublicWWW returned %d raw domains for quoted snippet=%r",
            raw_count, quoted_snippet[:70],
        )
        if raw_count > 2000:
            logger.warning(
                "PublicWWW returned %d results for %r — snippet may be too broad. "
                "Consider narrowing it in malware_signatures.",
                raw_count, quoted_snippet[:70],
            )
        return domains

    except Exception as exc:
        logger.error("PublicWWW query failed for snippet=%r: %s", quoted_snippet[:60], exc)
        return []


def _signature_search(campaign_id: int, conn, western_tld_filter_enabled: bool = False) -> dict:
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
        "SELECT id, snippet, malware_family, confidence, source_url FROM malware_signatures WHERE campaign_id = %s AND status = 'approved'",
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

        logger.info("Querying for signature id=%s family=%s", sig["id"], sig["malware_family"])
        domains = []
        if config.PUBLICWWW_API_KEY:
            domains = _publicwww_search(sig["snippet"])
            cost_log.log_call(conn, "stage2", "publicwww", campaign_id=campaign_id, query_count=1)

        # Fallback to browser scraper if API returned 0 results (or if no API key is set)
        if not domains:
            logger.info("API returned 0 domains (or no API key), falling back to browser scraper for %s", sig["snippet"][:60])
            try:
                import publicwww_scraper
                markdown = publicwww_scraper.crawl_publicwww(sig["snippet"], page=1, use_quotes=True)
                if markdown:
                    domains = publicwww_scraper.parse_domains_from_markdown(markdown)
                    logger.info("Scraper returned %d domains", len(domains))
            except Exception as e:
                logger.error("Scraper fallback failed: %s", e)
            
            if not domains:
                domains = _fallback_signature_search(sig["snippet"], conn, campaign_id)

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
                        "source_url": sig.get("source_url"),
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
                western_tld_filter_enabled=western_tld_filter_enabled,
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
    if not db.acquire_stage_lock(campaign_id, "stage2"):
        logger.info("Stage 2 is already running for campaign %s", campaign_id)
        return {"status": "skipped", "reason": "already running"}
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
            western_tld_filter_enabled = int(settings.get("western_tld_filter_enabled", 1)) == 1
            
            logger.info(
                "Stage 2: campaign=%s finder_type=%s cooldown_days=%d western_filter=%s",
                campaign_id, finder_type, cooldown_days, western_tld_filter_enabled
            )

            if finder_type == "keyword_search":
                result = _keyword_search(campaign_id, conn, cooldown_days=cooldown_days, western_tld_filter_enabled=western_tld_filter_enabled)
            elif finder_type == "code_signature_search":
                result = _signature_search(campaign_id, conn, western_tld_filter_enabled=western_tld_filter_enabled)
            else:
                raise ValueError(f"Unknown finder_type: {finder_type!r}")

            # D7: Garbage collect stale unreviewed candidates (TTL: 14 days)
            rows_discarded = db.execute(
                conn,
                """
                UPDATE candidates
                SET status = 'discarded'
                WHERE status = 'pending_review'
                  AND created_at < now() - interval '14 days'
                """
            )
            if rows_discarded > 0:
                logger.info("Stage 2: Auto-discarded %d stale 'pending_review' candidates", rows_discarded)

        db.set_stage_status(campaign_id, "stage2", "idle")
        return result
    except Exception:
        db.set_stage_status(campaign_id, "stage2", "failed")
        raise


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
