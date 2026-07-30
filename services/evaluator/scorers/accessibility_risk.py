"""
scorers/accessibility_risk.py - Campaign 1: ADA/WCAG Accessibility Violation Detector.

Target: SMB e-commerce and local businesses (especially US market - ADA Title III)
Selling: Web accessibility remediation services
Angle: "ADA lawsuits increased 12% in 2024. We found X violations on your site."

Uses axe-core (injected via Playwright into Browserless) to detect WCAG A/AA violations.
Score = (critical_violations * 15) + (serious_violations * 8) capped at 100.

No LLM needed - pure automated compliance check.
"""
import logging
import threading
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

_BROWSER_SEMAPHORE = threading.Semaphore(3)

# axe-core CDN - pinned to stable 4.10 (MIT license, free)
AXE_CORE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.0/axe.min.js"


def score(candidate: dict, campaign: dict, icp: dict, few_shot: list) -> dict:
    domain = candidate["domain"]
    url = f"https://{domain}"

    try:
        with _BROWSER_SEMAPHORE:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp("ws://browserless:3000")
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                page = context.new_page()

                try:
                    resp = page.goto(url, timeout=30000, wait_until="networkidle")
                    if not resp or not resp.ok:
                        return _no_data_result(domain, f"HTTP {resp.status if resp else 'unknown'}")

                    page.wait_for_timeout(2000)

                    # Inject axe-core from CDN
                    page.add_script_tag(url=AXE_CORE_URL)
                    page.wait_for_timeout(1000)  # Let axe-core initialise

                    # Run axe analysis
                    axe_results = page.evaluate("""
                        () => axe.run(document, {
                            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] }
                        }).then(results => ({
                            violations: results.violations.map(v => ({
                                id: v.id,
                                impact: v.impact,
                                description: v.description,
                                nodes_count: v.nodes.length
                            })),
                            passes: results.passes.length
                        }))
                    """)

                    violations = axe_results.get("violations", [])
                    passes = axe_results.get("passes", 0)

                finally:
                    try:
                        context.close()
                        browser.close()
                    except Exception:
                        pass

        critical = [v for v in violations if v.get("impact") == "critical"]
        serious = [v for v in violations if v.get("impact") == "serious"]
        moderate = [v for v in violations if v.get("impact") == "moderate"]

        # Score: how much opportunity for an accessibility remediation consultant
        opportunity_score = min(100, len(critical) * 20 + len(serious) * 10 + len(moderate) * 3)

        total_violations = len(violations)
        total_nodes = sum(v.get("nodes_count", 1) for v in violations)

        rationale = (
            f"axe-core found {total_violations} WCAG A/AA violations "
            f"({len(critical)} critical, {len(serious)} serious, {len(moderate)} moderate) "
            f"affecting ~{total_nodes} page elements. {passes} checks passed."
        )

        cold_email_hook = ""
        if total_violations >= 3:
            top_issues = ", ".join(v["id"] for v in (critical + serious)[:3])
            cold_email_hook = (
                f"I ran an automated accessibility scan on {domain} this morning. "
                f"Found {total_violations} WCAG violations including {top_issues}. "
                f"ADA Title III lawsuits hit record highs in 2024 - "
                f"e-commerce sites are prime targets. We can fix this in 2-3 weeks."
            )

        return {
            "score": opportunity_score,
            "rationale": rationale,
            "evidence_urls": [url],
            "evidence_data": {
                "total_violations": total_violations,
                "critical_count": len(critical),
                "serious_count": len(serious),
                "moderate_count": len(moderate),
                "passes_count": passes,
                "critical_violations": [{"id": v["id"], "nodes": v.get("nodes_count", 0)} for v in critical[:5]],
                "serious_violations": [{"id": v["id"], "nodes": v.get("nodes_count", 0)} for v in serious[:5]],
                "cold_email_hook": cold_email_hook,
            },
            "model_used": "axe-core-4.10",
            "provider": "browserless",
            "tokens_in": 0,
            "tokens_out": 0,
        }

    except Exception as exc:
        logger.error("Accessibility check failed for %s: %s", domain, exc)
        return _no_data_result(domain, str(exc))


def _no_data_result(domain: str, reason: str) -> dict:
    return {
        "score": 0,
        "rationale": f"Could not run accessibility check: {reason}",
        "evidence_urls": [f"https://{domain}"],
        "evidence_data": {"error": reason},
        "model_used": "axe-core-4.10",
        "provider": "browserless",
        "tokens_in": 0,
        "tokens_out": 0,
    }
