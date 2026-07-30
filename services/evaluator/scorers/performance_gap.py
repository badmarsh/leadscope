"""
scorers/performance_gap.py - Campaign 8: Core Web Vitals Red-Zone Detector.

Zero new infrastructure. Calls Google PageSpeed Insights API (free).
No LLM needed. Inverted score: worse performance = better lead.

You are a freelancer selling web performance optimization.
The cold email angle: "Google is penalizing your ads right now."
The proof: their own PSI score with LCP in seconds and a EUR waste estimate.
"""
import logging
import requests

logger = logging.getLogger(__name__)

PSI_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Cost model: Google Ads Quality Score penalty for LCP > 2.5s
# Approx: 20-40% higher CPC vs fast-loading competitors
# For a EUR 2000/month ad budget: 30% waste = EUR 600/month
EST_MONTHLY_AD_BUDGET_EUR = 2000
EST_PENALTY_RATE = 0.30


def _estimate_wasted_spend(lcp_ms: float, perf_score: float) -> float:
    """Rough EUR waste estimate based on how bad the site performs."""
    if lcp_ms > 6000 or perf_score < 30:
        penalty = 0.40  # Severe
    elif lcp_ms > 4000 or perf_score < 50:
        penalty = 0.30  # Moderate
    elif lcp_ms > 2500 or perf_score < 70:
        penalty = 0.20  # Mild
    else:
        penalty = 0.0   # Pass
    return round(EST_MONTHLY_AD_BUDGET_EUR * penalty, 0)


def score(candidate: dict, campaign: dict, icp: dict, few_shot: list) -> dict:
    domain = candidate["domain"]
    url = f"https://{domain}"

    try:
        resp = requests.get(
            PSI_API_URL,
            params={"url": url, "strategy": "mobile"},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("PSI API returned %s for %s", resp.status_code, domain)
            return _no_data_result(domain, f"PSI API HTTP {resp.status_code}")

        data = resp.json()
        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        audits = lighthouse.get("audits", {})

        perf_score = (categories.get("performance", {}).get("score") or 0) * 100
        lcp_ms = (audits.get("largest-contentful-paint", {}).get("numericValue") or 0)
        cls_val = (audits.get("cumulative-layout-shift", {}).get("numericValue") or 0)
        fid_ms = (audits.get("total-blocking-time", {}).get("numericValue") or 0)
        speed_index = (audits.get("speed-index", {}).get("numericValue") or 0)

        # Opportunity score: INVERTED performance score (worse site = better lead)
        # Add bonus for passing our threshold (LCP > 2.5s is a confirmed problem)
        opportunity_score = max(0, min(100, int(100 - perf_score)))
        if lcp_ms > 4000:
            opportunity_score = min(100, opportunity_score + 10)  # Severe LCP penalty bonus

        wasted_eur = _estimate_wasted_spend(lcp_ms, perf_score)

        rationale = (
            f"PSI mobile score: {perf_score:.0f}/100. "
            f"LCP: {lcp_ms/1000:.2f}s (target <2.5s). "
            f"CLS: {cls_val:.3f}. "
            f"Est. wasted Google Ads spend: EUR {wasted_eur:.0f}/month."
        )

        return {
            "score": opportunity_score,
            "rationale": rationale,
            "evidence_urls": [
                f"https://pagespeed.web.dev/analysis?url={url}",
            ],
            "evidence_data": {
                "psi_mobile_score": round(perf_score, 1),
                "lcp_ms": round(lcp_ms, 0),
                "lcp_seconds": round(lcp_ms / 1000, 2),
                "cls": round(cls_val, 3),
                "total_blocking_time_ms": round(fid_ms, 0),
                "speed_index_ms": round(speed_index, 0),
                "estimated_wasted_ads_eur": wasted_eur,
                # Cold email data — directly usable in outreach templates
                "cold_email_hook": (
                    f"I ran {domain} through Google PageSpeed this morning. "
                    f"Mobile score: {perf_score:.0f}/100, LCP: {lcp_ms/1000:.1f}s. "
                    f"Google penalises landing pages above 2.5s — on a typical ad budget, "
                    f"that costs roughly EUR {wasted_eur:.0f}/month in wasted clicks."
                ) if wasted_eur > 0 else "",
                "psi_report_url": f"https://pagespeed.web.dev/analysis?url={url}",
            },
            "model_used": "pagespeed-api-v5",
            "provider": "google",
            "tokens_in": 0,
            "tokens_out": 0,
        }

    except Exception as exc:
        logger.error("PSI API failed for %s: %s", domain, exc)
        return _no_data_result(domain, str(exc))


def _no_data_result(domain: str, reason: str) -> dict:
    return {
        "score": 0,
        "rationale": f"Could not fetch PSI data: {reason}",
        "evidence_urls": [f"https://{domain}"],
        "evidence_data": {"error": reason},
        "model_used": "pagespeed-api-v5",
        "provider": "google",
        "tokens_in": 0,
        "tokens_out": 0,
    }
