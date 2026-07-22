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
from typing import Optional

import requests

import config
import llm

logger = logging.getLogger(__name__)

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
{scraped_content}

## Re-verification result
Snippet still present in fresh Playwright scrape: {snippet_confirmed}
Found snippets: {found_snippets}

## Reputation API results
Google Safe Browsing: {safe_browsing_result}
VirusTotal: {virustotal_result}

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
- "recommendation": "remediation_candidate" | "needs_manual_check" | "likely_clean"
"""


# ── Crawl4AI re-verification helpers ─────────────────────────────────────────

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
                "bypass_cache": True,
                "timeout_ms": 30000,
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            return data.get("markdown") or ""
        logger.warning("Crawl4AI returned success=False for %s: %s", url, data.get("error"))
        return None
    except Exception as exc:
        logger.warning("Crawl4AI failed for %s: %s", url, exc)
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
    Checks exact match first, then partial match (first 30 chars) for obfuscated variants.
    Returns (any_found: bool, list_of_found_snippets: list[str]).
    """
    found = []
    content_lower = scraped_content.lower()
    for snippet in snippets:
        snippet_clean = snippet.strip().lower()
        if not snippet_clean:
            continue
        if snippet_clean in content_lower:
            found.append(snippet)
        elif len(snippet_clean) > 30 and snippet_clean[:30] in content_lower:
            found.append(snippet + " (partial match — possible obfuscated variant)")
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
            f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={config.SAFE_BROWSING_API_KEY}",
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


def _check_virustotal(domain: str) -> dict:
    """
    Query VirusTotal domain report (v3 API).
    Returns {"malicious_count": int, "suspicious_count": int, "community_score": int}
    or {"error": str}. Silently skips if VIRUSTOTAL_API_KEY is not configured.
    """
    if not config.VIRUSTOTAL_API_KEY:
        return {"note": "API key not configured"}
    try:
        resp = requests.get(
            f"https://www.virustotal.com/api/v3/domains/{domain}",
            headers={"x-apikey": config.VIRUSTOTAL_API_KEY},
            timeout=15,
        )
        if resp.status_code == 404:
            return {"note": "Domain not in VirusTotal database"}
        resp.raise_for_status()
        attrs = resp.json().get("data", {}).get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})
        result = {
            "malicious_count": stats.get("malicious", 0),
            "suspicious_count": stats.get("suspicious", 0),
            "community_score": attrs.get("reputation", 0),
        }
        logger.info(
            "VirusTotal for %s: malicious=%d suspicious=%d community_score=%d",
            domain, result["malicious_count"], result["suspicious_count"], result["community_score"],
        )
        return result
    except Exception as exc:
        logger.warning("VirusTotal API failed for %s: %s", domain, exc)
        return {"error": str(exc)}


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

    # ── 4. Reputation API checks (optional secondary corroboration) ───────────
    homepage_url = f"https://{domain}"
    safe_browsing = _check_safe_browsing(homepage_url)
    virustotal = _check_virustotal(domain)

    # ── 5. Few-shot examples ──────────────────────────────────────────────────
    few_shot_str = "(No prior feedback available)"
    if few_shot:
        examples = [
            f"- Domain: {fb.get('domain', '?')} | Decision: {fb['decision']} | Note: {fb.get('note', 'N/A')}"
            for fb in few_shot
        ]
        few_shot_str = "\n".join(examples)

    # ── 6. LLM scoring ───────────────────────────────────────────────────────
    prompt = SCORING_PROMPT.format(
        signatures_json=json.dumps(matched_sigs, indent=2, ensure_ascii=False)[:2000],
        scraped_content=scraped[:5000],
        snippet_confirmed="YES" if snippet_confirmed else "NO — not found in fresh Playwright scrape",
        found_snippets=str(found_snippets)[:500] if found_snippets else "none",
        safe_browsing_result=json.dumps(safe_browsing),
        virustotal_result=json.dumps(virustotal),
        few_shot_examples=few_shot_str,
    )

    result, ti, to, model, provider = llm.chat_json(prompt, temperature=0.1)

    if "_raw" in result:
        logger.warning("threat_intel scorer: LLM returned non-JSON response for domain=%s", domain)
        return {
            "score": 30,  # Conservative default — err on lower score for safety
            "rationale": "LLM returned non-parseable response; defaulting to low score for safety",
            "evidence_urls": list(pages.keys()),
            "evidence_data": {
                "snippet_confirmed": snippet_confirmed,
                "safe_browsing": safe_browsing,
                "virustotal": virustotal,
                "raw_response": result.get("_raw", "")[:500],
            },
            "model_used": model,
            "provider": provider,
            "tokens_in": ti,
            "tokens_out": to,
        }

    return {
        "score": max(0, min(100, int(result.get("score", 30)))),
        "rationale": result.get("rationale", ""),
        "evidence_urls": list(pages.keys()),
        "evidence_data": {
            "snippet_confirmed": result.get("snippet_confirmed", snippet_confirmed),
            "malware_family": result.get("malware_family", "unknown"),
            "confidence": result.get("confidence", "low"),
            "recommendation": result.get("recommendation", "needs_manual_check"),
            "matched_signatures": matched_sigs,
            "found_in_fresh_scrape": found_snippets,
            "pages_scraped": list(pages.keys()),
            "safe_browsing": safe_browsing,
            "virustotal": virustotal,
        },
        "model_used": model,
        "provider": provider,
        "tokens_in": ti,
        "tokens_out": to,
    }
