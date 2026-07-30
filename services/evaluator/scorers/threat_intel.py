"""
scorers/threat_intel.py — Scorer C: WP-remediation (threat_intel).

Re-verification scorer: Stage 2 detected a PublicWWW hit against a known
malware signature. This scorer's job is FRESH RE-VERIFICATION — confirm
the snippet is STILL PRESENT on the live site via Crawl4AI, then score.

Verification flow:
  1. Crawl homepage + /wp-content/ + /wp-includes/ via self-hosted Crawl4AI
     (Playwright, JS-rendered) — malware is often injected into React/SPA wrappers
  2. Check each known snippet against fresh scraped content (exact + partial match)
  3. Query Google Safe Browsing API (optional, if SAFE_BROWSING_API_KEY set)
  4. Query VirusTotal URL scan (optional, if VIRUSTOTAL_API_KEY set)
  5. LLM turns re-verified evidence into a structured score + rationale

A high score means "confirmed active compromise, strong remediation lead".
A mistaken "you're hacked" call is costlier than any other false positive.
Err on the side of lower scores when evidence is ambiguous.
"""
import json
import logging
import re
from typing import Optional
from pydantic import BaseModel, Field

import requests

import services.common.config as config
import services.common.llm as llm
from scorers.proof_engine import generate_proof
from scorers.exposure_scanner import scan_exposures

logger = logging.getLogger(__name__)

def calculate_wealth_index(domain: str, candidate: dict = None) -> int:
    """Assigns firmographic value based on target config."""
    if candidate and "campaign_config" in candidate:
        try:
            cfg = json.loads(candidate.get("campaign_config", "{}"))
            return cfg.get("tld_wealth_bonus", 0)
        except:
            pass
    return 0

# ── WordPress paths to scan on suspected infected sites ───────────────────────
WP_PATHS = ["", "/wp-content/", "/wp-includes/"]

SCORING_PROMPT = """
You are a WordPress security analyst evaluating a website for active malware
infection. A previous automated scan (PublicWWW) detected suspicious code
signatures on this site. Your job is to RE-VERIFY whether the infection is
still active based on fresh evidence provided below.

## Malware signatures detected in Stage 2
{signatures_json}

## Fresh Playwright scrape of the site (re-verification via Crawl4AI)
The scraped content is provided below in the USER DATA section.

## Re-verification result
Snippet still present in fresh Playwright scrape: {snippet_confirmed}
Found snippets: {found_snippets}

## Reputation API results
Google Safe Browsing: {safe_browsing_result}
URLhaus: {urlhaus_result}
Wayback Machine (recency): {wayback_result}

A site where snippet_confirmed=False BUT wayback shows a recent snapshot
(last_snapshot_date within last 14 days) suggests the owner recently cleaned up
— this is a WARM LEAD. Score 50-65 with recommendation="warm_lead_cleanup_in_progress".

WordPress version (from RSS feed): {wp_version_result}

If cve_risk is "critical" or "high" AND snippet_confirmed=True, upgrade the
rationale to explicitly mention unpatched CVEs. This changes the pitch from
"you're infected" to "your site has known exploitable vulnerabilities AND active malware."

## Past feedback (few-shot)
{few_shot_examples}

## Instructions
Score 0-100 where:
- 90-100: Confirmed active infection — signature found in fresh scrape, strong remediation lead
- 70-89: Likely infected — partial match or obfuscated variant, OR reputation API flags present
- 50-69: Inconclusive — signature not found in this fetch (may be intermittent or gated behind JS)
- 30-49: Unlikely — site appears clean in fresh scrape, no reputation flags
- 0-29: Confirmed clean, site is down, or not WordPress

CRITICAL: A mistaken "you're hacked" call to a clean site destroys trust and is
costlier than any other false positive in this system. Only score 70+ if the
snippet or strong corroborating evidence is clearly present. When in doubt, score lower.

Return JSON with:
- "score": integer 0-100
- "rationale": 2-3 sentences — which malware family, which signature,
  confirmed present as of when, what reputation APIs said. Be specific.
- "snippet_confirmed": boolean — was the exact or partial snippet found?
- "malware_family": string — the malware family name (e.g. "SocGholish", "Balada Injector")
- "confidence": "high" | "medium" | "low"
- "recommendation": "remediation_candidate" | "needs_manual_check" | "likely_clean" | "warm_lead_cleanup_in_progress"
=== END SYSTEM INSTRUCTIONS ===

=== BEGIN USER DATA ===
{scraped_content}
=== END USER DATA ===
"""


def _crawl4ai_scrape(url: str, force_playwright: bool = True) -> Optional[str]:
    """
    Scrape a URL via self-hosted Crawl4AI service using Playwright (JS-rendered).
    Uses Playwright by default since malware is often injected into JS-rendered DOM.
    Returns markdown text or None on failure.
    """
    endpoint = f"{config.CRAWLER_ENDPOINT.rstrip('/')}/crawl"
    try:
        resp = requests.post(
            endpoint,
            json={
                "url": url,
                "force_playwright": force_playwright,
                "bypass_cache": False,
                "timeout_ms": 90000,
            },
            timeout=95,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            return data.get("html") or data.get("markdown") or ""
        logger.warning("Crawl4AI returned success=False for %s: %s", url, data.get("error"))
    except Exception as exc:
        logger.warning("Crawl4AI failed for %s: %s", url, exc)
        
    logger.info("Falling back to requests.get for %s", url)
    try:
        fallback_resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        )
        if fallback_resp.status_code == 200:
            return fallback_resp.text
    except Exception as exc2:
        logger.warning("Fallback requests.get failed for %s: %s", url, exc2)
        
    return None


def _scrape_wp_site(domain: str) -> dict[str, str]:
    """
    Scrape homepage + /wp-content/ + /wp-includes/ from a suspected infected WP site.
    Returns {url: markdown_text} for pages that returned content.
    Aborts early if homepage returns nothing (site is likely down or blocking crawlers).
    """
    results = {}
    base = f"https://{domain}"
    for i, path in enumerate(WP_PATHS):
        url = base + path
        text = _crawl4ai_scrape(url, force_playwright=True)
        if text and len(text) > 100:
            results[url] = text
            logger.info("Crawl4AI scraped %s: %d chars", url, len(text))
        elif i == 0:
            # Homepage returned nothing — site is likely down; abort subpaths
            logger.warning("Crawl4AI got no content from homepage %s — aborting subpath scan", url)
            break
    return results


def _check_snippet_present(scraped_content: str, snippets: list[str]) -> tuple[bool, list[str]]:
    """
    Check if any malware snippets are still present in the scraped content.
    Three-pass strategy:
      1. Exact match (case-insensitive)
      2. Partial match (first 30 chars) for obfuscated inline variants
      3. Base64 decode pass — extract all base64 blobs from the page,
         decode each, and check if the decoded string contains any known
         snippet fragment (catches re-encoded Balada/SocGholish variants)
    Returns (any_found: bool, list_of_found_snippets: list[str]).
    """
    import base64 as _b64
    import re as _re

    found = []
    content_lower = scraped_content.lower()

    # Pass 1 + 2: exact and partial
    for snippet in snippets:
        snippet_clean = snippet.strip().lower()
        if not snippet_clean:
            continue
        if snippet_clean in content_lower:
            found.append(snippet)
        elif len(snippet_clean) > 30 and snippet_clean[:30] in content_lower:
            found.append(snippet + " (partial match — possible obfuscated variant)")

    # Pass 3: base64 decode
    # Extract all candidate base64 strings (length >= 40, only valid b64 chars)
    # Pass 3: base64 decode
    # Extract all candidate base64 strings (length >= 40, only valid b64 chars)
    if not found:
        b64_candidates = _re.findall(r'[A-Za-z0-9+/]{40,}={0,2}', scraped_content)
        decoded_blobs = []
        for b64_str in b64_candidates[:200]:  # cap at 200 to avoid DoS on large pages
            try:
                padded = b64_str + "=" * ((-len(b64_str)) % 4)
                decoded = _b64.b64decode(padded).decode("utf-8", errors="ignore").lower()
                if decoded:
                    decoded_blobs.append(decoded)
            except Exception:
                continue

        if decoded_blobs:
            decoded_corpus = " ".join(decoded_blobs)
            for snippet in snippets:
                snippet_clean = snippet.strip().lower()
                if not snippet_clean or len(snippet_clean) < 10:
                    continue
                # (Full length verification to mitigate false-positives)
                fragment = snippet_clean
                if fragment in decoded_corpus:
                    label = snippet + " (found via base64 decode — re-encoded variant)"
                    if label not in found:
                        found.append(label)
                        logger.info(
                            "Base64 decode match for snippet fragment '%s'", fragment
                        )

    return len(found) > 0, found


# ── Reputation API helpers ────────────────────────────────────────────────────

def _check_safe_browsing(url: str) -> dict:
    """
    Query Google Safe Browsing API v4 for threat data.
    Returns {"flagged": bool, "threat_types": list[str]} or {"error": str}.
    Silently skips if SAFE_BROWSING_API_KEY is not configured.
    """
    if not config.SAFE_BROWSING_API_KEY:
        return {"flagged": False, "note": "API key not configured"}
    try:
        resp = requests.post(
            "https://safebrowsing.googleapis.com/v4/threatMatches:find",
            headers={"X-Goog-Api-Key": config.SAFE_BROWSING_API_KEY},
            json={
                "client": {"clientId": "jenex-threat-intel", "clientVersion": "1.0"},
                "threatInfo": {
                    "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": url}],
                },
            },
            timeout=10,
        )
        resp.raise_for_status()
        matches = resp.json().get("matches", [])
        result = {
            "flagged": len(matches) > 0,
            "threat_types": [m.get("threatType") for m in matches],
        }
        logger.info("Safe Browsing for %s: flagged=%s types=%s", url, result["flagged"], result["threat_types"])
        return result
    except Exception as exc:
        logger.warning("Safe Browsing API failed for %s: %s", url, exc)
        return {"error": str(exc)}





def _check_urlhaus(domain: str) -> dict:
    """
    Query URLhaus API to check if the domain is currently serving malware.
    Uses no API key. Returns {"is_listed": bool, "threat_tags": list[str]}
    """
    try:
        headers = {}
        if config.URLHAUS_AUTH_KEY:
            headers["Auth-Key"] = config.URLHAUS_AUTH_KEY

        resp = requests.post(
            "https://urlhaus-api.abuse.ch/v1/host/",
            data={"host": domain},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        
        is_listed = data.get("query_status") == "ok" and bool(data.get("urls"))
        tags = []
        if is_listed:
            for url_entry in data.get("urls", []):
                if url_entry.get("tags"):
                    tags.extend(url_entry["tags"])
            tags = list(set(tags)) # dedup
            
        result = {
            "is_listed": is_listed,
            "threat_tags": tags
        }
        logger.info("URLhaus for %s: listed=%s tags=%s", domain, is_listed, tags)
        return result
    except Exception as exc:
        logger.warning("URLhaus API failed for %s: %s", domain, exc)
        return {"error": str(exc)}


def _check_wayback_recency(domain: str) -> dict:
    """
    Query the Wayback Machine CDX API for the 3 most recent snapshots of the domain.
    Returns {
        "last_snapshot_date": "YYYYMMDDHHMMSS" | None,
        "snapshot_count_last_30d": int,
        "status": "active_archiving" | "rarely_archived" | "no_snapshots" | "error"
    }
    Uses no API key. Timeout set low (5s) — this is a non-blocking enrichment signal.
    """
    try:
        resp = requests.get(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": domain,
                "output": "json",
                "limit": "5",
                "fl": "timestamp,statuscode",
                "filter": "statuscode:200",
                "collapse": "timestamp:8",  # deduplicate to 1 per day
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"status": "error", "last_snapshot_date": None, "snapshot_count_last_30d": 0}

        rows = resp.json()
        if not rows or len(rows) < 2:  # first row is header
            return {"status": "no_snapshots", "last_snapshot_date": None, "snapshot_count_last_30d": 0}

        data_rows = rows[1:]  # skip header row ["timestamp","statuscode"]
        timestamps = [r[0] for r in data_rows if r[0]]

        last_ts = timestamps[0] if timestamps else None

        # Count snapshots within last 30 days
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=30)).strftime("%Y%m%d%H%M%S")
        recent = [t for t in timestamps if t >= cutoff]

        status = "active_archiving" if len(recent) >= 2 else "rarely_archived"
        logger.info(
            "Wayback CDX for %s: last_snapshot=%s recent_30d=%d",
            domain, last_ts, len(recent),
        )
        return {
            "last_snapshot_date": last_ts,
            "snapshot_count_last_30d": len(recent),
            "status": status,
        }
    except Exception as exc:
        logger.warning("Wayback CDX failed for %s: %s", domain, exc)
        return {"status": "error", "last_snapshot_date": None, "snapshot_count_last_30d": 0}


def _detect_wp_version(domain: str) -> dict:
    """
    Detect WordPress version from the RSS feed generator tag.
    /?feed=rss2 exposes <generator>https://wordpress.org/?v=X.Y.Z</generator>
    without any authentication. Returns {"version": "6.7.1", "cve_risk": "low"|"medium"|"high"|"unknown"}.
    Times out fast (6s) since this is a non-blocking enrichment signal.
    """
    import re
    try:
        resp = requests.get(
            f"https://{domain}/?feed=rss2",
            timeout=6,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return {"version": None, "cve_risk": "unknown"}

        match = re.search(
            r"<generator>https://wordpress\.org/\?v=([\d.]+)</generator>",
            resp.text,
        )
        if not match:
            return {"version": None, "cve_risk": "unknown"}

        version_str = match.group(1)
        parts = version_str.split(".")
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0

        # WP < 5.8 = critical unpatched RCE; 5.8–6.3 = high; 6.4–6.6 = medium; 6.7+ = low
        if major < 5 or (major == 5 and minor < 8):
            cve_risk = "critical"
        elif major == 5 or (major == 6 and minor < 4):
            cve_risk = "high"
        elif major == 6 and minor < 7:
            cve_risk = "medium"
        else:
            cve_risk = "low"

        logger.info("WP version for %s: %s (cve_risk=%s)", domain, version_str, cve_risk)
        return {"version": version_str, "cve_risk": cve_risk}

    except Exception as exc:
        logger.warning("WP version detection failed for %s: %s", domain, exc)
        return {"version": None, "cve_risk": "unknown"}


# ── Main scorer ───────────────────────────────────────────────────────────────

def score(candidate: dict, campaign: dict, icp: dict, few_shot: list[dict]) -> dict:
    """
    Score a candidate using the threat_intel (re-verification) strategy.

    Flow:
      1. Extract matched signatures from evidence_data (populated by Stage 2 / PublicWWW).
      2. Crawl homepage + WP paths via self-hosted Crawl4AI (Playwright, JS-rendered).
      3. Check each snippet against fresh content (exact + partial obfuscation match).
      4. Query Google Safe Browsing + VirusTotal for reputation corroboration.
      5. LLM synthesises all evidence into a structured score + rationale.
    """
    domain = candidate["domain"]
    evidence = candidate.get("evidence_data", {})
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except json.JSONDecodeError:
            evidence = {}

    # ── 1. Extract signatures from Stage 2 evidence ───────────────────────────
    matched_sigs = evidence.get("matched_signatures", [])
    
    # If no signatures were passed (e.g., from a keyword_search or manual import),
    # fetch all active signatures for this campaign to scan the source code locally.
    if not matched_sigs:
        import db
        with db.get_conn() as conn:
            all_sigs = db.fetchall(
                conn,
                "SELECT id as signature_id, snippet, malware_family, confidence, source_url FROM malware_signatures WHERE campaign_id = %s AND status = 'approved'",
                (campaign["id"],)
            )
            matched_sigs = all_sigs

    snippets = [s.get("snippet", "") for s in matched_sigs if s.get("snippet")]
    logger.info(
        "threat_intel: scoring domain=%s — %d known signatures, re-verifying via Crawl4AI",
        domain, len(snippets),
    )

    # ── 2. Fresh Crawl4AI re-verification (Playwright) ────────────────────────
    pages = _scrape_wp_site(domain)
    scraped = "\n\n".join(
        f"### {url}\n{text[:3000]}" for url, text in list(pages.items())[:3]
    )
    if not scraped:
        scraped = "(No content could be scraped — site may be down or blocking crawlers)"

    # ── 3. Snippet presence check ─────────────────────────────────────────────
    snippet_confirmed, found_snippets = _check_snippet_present(scraped, snippets)
    logger.info(
        "threat_intel: domain=%s snippet_confirmed=%s found=%s",
        domain, snippet_confirmed, found_snippets,
    )

    # ── 4. Reputation + recency checks ────────────────────────────────────────
    homepage_url = f"https://{domain}"
    safe_browsing = _check_safe_browsing(homepage_url)
    urlhaus = _check_urlhaus(domain)
    wayback = _check_wayback_recency(domain)
    wp_version_info = _detect_wp_version(domain)

    # ── 5. Few-shot examples ────────────────────────────────────────────────────────────────────────────
    few_shot_str = "(No prior feedback available)"
    if few_shot:
        approved_ex = [fb for fb in few_shot if fb.get('decision') == 'approved']
        rejected_ex = [fb for fb in few_shot if fb.get('decision') == 'rejected']
        parts = []
        if approved_ex:
            parts.append("APPROVED — score HIGH for similar sites:")
            for fb in approved_ex[:5]:
                parts.append(f"  ✓ {fb.get('domain', '?')}: {fb.get('note', 'N/A')}")
        if rejected_ex:
            parts.append("REJECTED — score LOW for similar sites:")
            for fb in rejected_ex[:5]:
                parts.append(f"  ✗ {fb.get('domain', '?')}: {fb.get('note', 'N/A')}")
        few_shot_str = "\n".join(parts) if parts else "(No prior feedback available)"

    # ── 6. LLM scoring ───────────────────────────────────────────────────────
    def _sanitize_scraped(text: str) -> str:
        """Strip === BLOCK === markers and system instruction override attempts from scraped content."""
        # Remove all === SECTION === delimiters that could escape the user data boundary
        text = re.sub(r'={3,}\s*[A-Z][A-Z\s]+={3,}', '[BLOCK_STRIPPED]', text)
        # Strip common prompt injection patterns
        text = re.sub(
            r'(?i)(ignore\s+(all\s+)?(previous|prior|above)\s+instructions?|'
            r'you\s+are\s+(now|a|an)\s+|system\s*:\s*|assistant\s*:\s*)',
            '[STRIPPED]', text
        )
        return text

    prompt = SCORING_PROMPT.format(
        signatures_json=json.dumps(matched_sigs, indent=2, ensure_ascii=False)[:2000],
        scraped_content=_sanitize_scraped(scraped[:5000]),
        snippet_confirmed="YES" if snippet_confirmed else "NO — not found in fresh Playwright scrape",
        found_snippets=str(found_snippets)[:500] if found_snippets else "none",
        safe_browsing_result=json.dumps(safe_browsing),
        urlhaus_result=json.dumps(urlhaus),
        wayback_result=json.dumps(wayback),
        wp_version_result=json.dumps(wp_version_info),
        few_shot_examples=few_shot_str,
    )

    class ThreatIntelResponse(BaseModel):
        score: int
        rationale: str
        confidence: int
        snippet_confirmed: bool
        recommendation: str

    result, ti, to, model, provider = llm.chat_json(
        prompt,
        temperature=0.1,
        response_model=ThreatIntelResponse
    )

    if "_raw" in result:
        logger.warning("threat_intel scorer: LLM returned non-JSON response for domain=%s", domain)
        return {
            "score": 30,  # Conservative default — err on lower score for safety
            "rationale": "LLM returned non-parseable response; defaulting to low score for safety",
            "evidence_urls": list(pages.keys()),
            "evidence_data": {
                "snippet_confirmed": snippet_confirmed,
                "safe_browsing": safe_browsing,
                "wayback": wayback,
                "wp_version": wp_version_info,
                "raw_response": result.get("_raw", "")[:500],
            },
            "model_used": model,
            "provider": provider,
            "tokens_in": ti,
            "tokens_out": to,
        }
    # ── Phase X: Compound Lead Score Calculation ─────────────────────────────
    campaign_settings = candidate.get("_campaign_settings", {})
    skip_phase_x = campaign_settings.get("skip_phase_x", False)

    if not skip_phase_x:
        proof_data = generate_proof(domain, matched_sigs)
        exposure_data = scan_exposures(domain)
    else:
        proof_data = None
        exposure_data = {}
    
    proof_bonus = 0
    if proof_data:
        proof_bonus += 20
        logger.info(f"Phase X: Proof generated for {domain}: {proof_data['proof_type']}")
    if exposure_data.get("critical_found"):
        proof_bonus += 15
        logger.info(f"Phase X: Critical exposure found for {domain}")

    wealth_override = campaign_settings.get("wealth_index_override")
    if wealth_override is not None:
        firmographic_score = int(wealth_override)
    else:
        firmographic_score = calculate_wealth_index(domain, candidate)
    
    max_sneakiness_bonus = 0
    for sig in matched_sigs:
        tier = sig.get("sneakiness_tier", "C")
        if tier == "S":
            max_sneakiness_bonus = max(max_sneakiness_bonus, 20)
        elif tier == "A":
            max_sneakiness_bonus = max(max_sneakiness_bonus, 15)

    base_score = max(0, min(100, result.get("score", 30) if isinstance(result, dict) else getattr(result, "score", 30)))
    # If the LLM thinks it's clean (score < 50) but we have hard proof, override it
    if proof_data and base_score < 50:
        base_score = 60
        
    final_score = base_score + firmographic_score + max_sneakiness_bonus + proof_bonus

    # Generate enhanced rationale
    rationale = result.get("rationale", "") if isinstance(result, dict) else getattr(result, "rationale", "")
    if proof_data:
        rationale += f" | PROOF: {proof_data.get('evidence_text')}"
    if exposure_data.get("critical_found"):
        rationale += " | EXPOSURE: Critical sensitive files (.env/config) exposed."

    # Derive source post URL/title from the first matched signature that has a source_url
    source_url = next(
        (s.get("source_url") for s in matched_sigs if s.get("source_url")),
        None,
    )
    source_title = next(
        (
            f"{s.get('malware_family', 'Security intelligence')} — source post"
            for s in matched_sigs if s.get("source_url")
        ),
        None,
    )

    return {
        "score": max(0, min(100, final_score)),
        "rationale": rationale,
        "evidence_urls": list(pages.keys()),
        "evidence_data": {
            "snippet_confirmed": snippet_confirmed,
            "crawl_success": len(pages) > 0,
            "malware_family": result.get("malware_family", "unknown"),
            "confidence": result.get("confidence", "low"),
            "recommendation": result.get("recommendation", "needs_manual_check"),
            "matched_signatures": matched_sigs,
            "found_in_fresh_scrape": found_snippets,
            "pages_scraped": list(pages.keys()),
            "cached_pages": pages,
            "safe_browsing": safe_browsing,
            "urlhaus": urlhaus,
            "wayback": wayback,
            "wp_version": wp_version_info,
            "proof_data": proof_data,
            "exposure_scan": exposure_data,
            "firmographic_score": firmographic_score,
            "wealth_index_tld": domain.split('.')[-1].lower(),
            "source_post_url": source_url,
            "source_post_title": source_title,
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
