"""
scorers/gdpr_gap.py - Campaign 9: GDPR/Cookie Consent Compliance Gap Detector.

Target: EU-facing businesses (.eu, .de, .fr, .nl, .sk, .cz, .hu, .pl etc.)
Selling: GDPR compliance consulting, Cookiebot/OneTrust setup
Angle: "Your Google Analytics fires before consent - that's a GDPR violation."

Uses Playwright (via Browserless) to:
1. Intercept network requests on page load
2. Detect if tracking scripts fire BEFORE any consent click
3. Check for presence/absence of a cookie consent banner
4. Score based on severity of the violation

Note: Self-hosted Browserless at ws://browserless:3000
"""
import logging
import threading
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

_BROWSER_SEMAPHORE = threading.Semaphore(3)

TRACKING_PATTERNS = [
    "google-analytics.com",
    "googletagmanager.com",
    "facebook.net/en_US/fbevents",
    "connect.facebook.net",
    "hotjar.com",
    "clarity.ms",
    "cdn.heapanalytics.com",
    "segment.io",
    "mixpanel.com",
]

CONSENT_SELECTORS = [
    "#cookie-consent", "#cookieconsent", "#cookie-banner", "#gdpr",
    ".cookie-banner", ".cookie-notice", ".cookie-consent",
    "[class*='consent']", "[class*='cookie']", "[id*='consent']",
    "[aria-label*='cookie']", "[data-cookiebanner]",
    # Common CMPs
    "#onetrust-consent-sdk", ".cc-window", "#CybotCookiebotDialog",
    ".cookielawinfo-bar",
]


def score(candidate: dict, campaign: dict, icp: dict, few_shot: list) -> dict:
    domain = candidate["domain"]
    url = f"https://{domain}"

    tracking_before_consent = []
    has_banner = False
    error_msg = None

    try:
        with _BROWSER_SEMAPHORE:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp("ws://browserless:3000")
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    # Simulate EU visitor from Germany
                    locale="de-DE",
                    timezone_id="Europe/Berlin",
                )
                page = context.new_page()

                def on_request(request):
                    req_url = request.url.lower()
                    for pattern in TRACKING_PATTERNS:
                        if pattern in req_url:
                            tracking_before_consent.append(request.url)
                            break

                page.on("request", on_request)

                try:
                    resp = page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    if not resp or not resp.ok:
                        return _no_data_result(domain, f"HTTP {resp.status if resp else 'unknown'}")

                    # Wait a moment for trackers to fire
                    page.wait_for_timeout(3000)

                    # Check for consent banner
                    for sel in CONSENT_SELECTORS:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                has_banner = True
                                break
                        except Exception:
                            continue

                except Exception as nav_err:
                    error_msg = str(nav_err)
                    logger.warning("Navigation error for %s: %s", domain, nav_err)
                finally:
                    try:
                        context.close()
                        browser.close()
                    except Exception:
                        pass

    except Exception as exc:
        logger.error("GDPR gap check failed for %s: %s", domain, exc)
        return _no_data_result(domain, str(exc))

    if error_msg and not tracking_before_consent:
        return _no_data_result(domain, error_msg)

    # Score based on severity
    trackers_fired = len(tracking_before_consent)
    if trackers_fired > 0 and not has_banner:
        # Worst case: tracking fires with NO consent banner at all
        violation_score = 90
        severity = "critical"
        rationale = (
            f"{trackers_fired} tracker(s) fired on page load with NO cookie consent banner detected. "
            f"This is a clear GDPR/ePrivacy violation."
        )
    elif trackers_fired > 0 and has_banner:
        # Tracking fires before the user has a chance to consent
        violation_score = 70
        severity = "high"
        rationale = (
            f"Cookie banner present but {trackers_fired} tracker(s) already fired before any consent interaction. "
            f"This violates GDPR opt-in requirements."
        )
    elif not has_banner:
        # No trackers detected, but also no banner (may be using first-party only or missed detection)
        violation_score = 35
        severity = "medium"
        rationale = "No cookie consent banner detected. If the site uses any tracking, this is non-compliant."
    else:
        # Has banner, no trackers before consent - likely compliant
        violation_score = 10
        severity = "low"
        rationale = "Cookie consent banner present and no third-party trackers detected before consent."

    cold_email_hook = ""
    if violation_score >= 70:
        tracker_names = ", ".join(set(
            t.split("/")[2] for t in tracking_before_consent[:3]
            if "/" in t
        ))
        cold_email_hook = (
            f"I checked {domain} this morning from a German IP. "
            f"Your {tracker_names} tracking fires immediately on page load — "
            f"before any cookie consent. Under GDPR Art. 7, this is non-compliant "
            f"and EU DPAs have fined companies EUR 10K-500K for exactly this."
        )

    return {
        "score": violation_score,
        "rationale": rationale,
        "evidence_urls": [url],
        "evidence_data": {
            "has_consent_banner": has_banner,
            "trackers_before_consent": tracking_before_consent[:10],
            "tracker_count": trackers_fired,
            "severity": severity,
            "cold_email_hook": cold_email_hook,
        },
        "model_used": "playwright-network-intercept",
        "provider": "browserless",
        "tokens_in": 0,
        "tokens_out": 0,
    }


def _no_data_result(domain: str, reason: str) -> dict:
    return {
        "score": 0,
        "rationale": f"Could not check GDPR compliance: {reason}",
        "evidence_urls": [f"https://{domain}"],
        "evidence_data": {"error": reason},
        "model_used": "playwright-network-intercept",
        "provider": "browserless",
        "tokens_in": 0,
        "tokens_out": 0,
    }
