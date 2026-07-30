"""
tests/unit/test_stage5_retry_logic.py — Regression test for BUG-009.

BUG-009: enrichment_attempt_count was being incremented BEFORE the crawl
attempt (pre-increment), and AGAIN on failure (post-increment), causing
candidates to be marked 'enrichment_failed' after half the expected retries.

The fix: increment ONLY inside the `if not page_text:` failure branch.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

# Common env overrides for all tests (no real DB or proxy needed)
_BASE_ENV = {
    "DATABASE_URL": "postgresql://x:x@localhost/x",
    "GEMINI_PROXY_API_KEY": "sk-test",
    "GEMINI_PROXY_ENDPOINT": "http://localhost:8045",
    "OPENROUTER_API_KEY": "",
}


def _make_candidate(attempt_count: int = 0) -> dict:
    return {
        "id": 42,
        "campaign_id": 1,
        "domain": "example.com",
        "company_name": "Example Corp",
        "status": "approved",
        "enrichment_attempt_count": attempt_count,
        "enrichment_attempted_at": None,
        "enrichment_report": None,
        "eval_evidence": None,
    }


def _make_campaign() -> dict:
    return {
        "id": 1,
        "business_brief": "We sell security services",
        "evaluator_type": "threat_intel",
        "icp": "{}",
    }


# ---------------------------------------------------------------------------
# BUG-009 regression: count must NOT be incremented on success
# ---------------------------------------------------------------------------

class TestEnrichmentAttemptCountOnSuccess:
    """
    When crawling succeeds (page_text is non-empty), enrichment_attempt_count
    must NOT be incremented by _enrich_candidate().
    """

    def test_count_not_incremented_on_successful_scrape(self):
        """BUG-009: successful scrape must leave attempt count unchanged."""
        candidate = _make_candidate(attempt_count=0)
        campaign = _make_campaign()

        increment_calls = []

        def fake_db_execute(conn, sql, params=None):
            stripped = sql.strip()
            if "enrichment_attempt_count = enrichment_attempt_count + 1" in stripped:
                increment_calls.append(stripped)
            return 1  # rowcount

        import stage5

        with patch.dict(os.environ, _BASE_ENV, clear=False):
            # Patch db.fetchone to simulate no DNC and no cooldown check needed
            with patch("stage5.db.fetchone", return_value=None), \
                 patch("stage5.db.execute", side_effect=fake_db_execute), \
                 patch("stage5._crawler_scrape", return_value=("Rich page content for a great website that has lots of detail and many words. " * 10, [])), \
                 patch("stage5._extract_structured_data", return_value={}), \
                 patch("stage5._enrich_info", return_value=({
                     "company_overview_sk": "Test firma",
                     "email": "test@example.com",
                     "phone": None,
                     "company_size_estimate": "11-50",
                     "buying_signals": [],
                     "products_sold": [],
                     "estimated_revenue": None,
                     "estimated_traffic": None,
                     "firmographics": {},
                     "buying_power_signals": [],
                     "tech_stack": [],
                     "cold_email_hook": None,
                     "contact_name": None,
                 }, 10, 5)), \
                 patch("stage5.cost_log.log_call"):

                conn = MagicMock()
                stage5._enrich_candidate(candidate, campaign, conn)

        assert len(increment_calls) == 0, (
            f"BUG-009 REGRESSION: attempt_count was incremented during a successful scrape. "
            f"INCREMENT SQL calls seen: {increment_calls}"
        )


# ---------------------------------------------------------------------------
# BUG-009 regression: count MUST be incremented exactly once on failure
# ---------------------------------------------------------------------------

class TestEnrichmentAttemptCountOnFailure:
    """
    When crawling fails (page_text is None), enrichment_attempt_count must be
    incremented exactly once — not twice (the pre+post double-count bug).
    """

    def test_count_incremented_exactly_once_on_crawl_failure(self, mock_env, mock_db_conn):
        """BUG-009: failed scrape must increment attempt_count exactly once."""
        candidate = _make_candidate(attempt_count=0)
        campaign = _make_campaign()

        increment_calls = []

        def fake_db_execute(conn, sql, params=None):
            stripped = sql.strip()
            if "enrichment_attempt_count = enrichment_attempt_count + 1" in stripped:
                increment_calls.append(stripped)
            return 1

        with patch("stage5.db.fetchone", return_value=None), \
             patch("stage5.db.execute", side_effect=fake_db_execute), \
             patch("stage5._extract_structured_data", return_value={}), \
             patch("stage5._scrape_domain", return_value=(None, "", None)), \
             patch("stage5.cost_log.log_call"):
            import stage5

            result = stage5._enrich_candidate(candidate, campaign, mock_db_conn)

        assert len(increment_calls) == 1, (
            f"BUG-009 REGRESSION: expected exactly 1 increment on crawl failure, "
            f"got {len(increment_calls)}. SQL calls: {increment_calls}"
        )
        assert result["outcome"] in ("crawler_failed_retry", "enrichment_failed"), (
            f"Expected a failure outcome, got: {result}"
        )

    def test_enrichment_failed_status_set_after_max_attempts(self, mock_env, mock_db_conn):
        """After max_attempts failures, status must become 'enrichment_failed'."""
        # Use attempt_count = MAX_ENRICHMENT_ATTEMPTS - 1 so the next failure tips it over
        import stage5
        max_att = stage5.config.MAX_ENRICHMENT_ATTEMPTS
        candidate = _make_candidate(attempt_count=max_att - 1)
        campaign = _make_campaign()

        status_updates = []

        def fake_db_execute(conn, sql, params=None):
            stripped = sql.strip()
            if "enrichment_failed" in stripped:
                status_updates.append(stripped)
            return 1

        with patch.dict(os.environ, _BASE_ENV, clear=False):
            with patch("stage5.db.fetchone", return_value=None), \
                 patch("stage5.db.execute", side_effect=fake_db_execute), \
                 patch("stage5._extract_structured_data", return_value={}), \
                 patch("stage5._scrape_domain", return_value=(None, "", None)), \
                 patch("stage5.cost_log.log_call"):
                conn = MagicMock()
                result = stage5._enrich_candidate(candidate, campaign, conn)

        assert result["outcome"] == "enrichment_failed", (
            f"Expected 'enrichment_failed' on final attempt, got: {result['outcome']}"
        )
        assert len(status_updates) >= 1, (
            "Expected at least one UPDATE setting status='enrichment_failed'"
        )

    def test_retry_left_when_below_max_attempts(self, mock_env, mock_db_conn):
        """Below max_attempts, outcome must be 'crawler_failed_retry'."""
        candidate = _make_candidate(attempt_count=0)
        campaign = _make_campaign()

        with patch.dict(os.environ, _BASE_ENV, clear=False):
            with patch("stage5.db.fetchone", return_value=None), \
                 patch("stage5.db.execute"), \
                 patch("stage5._extract_structured_data", return_value={}), \
                 patch("stage5._scrape_domain", return_value=(None, "", None)), \
                 patch("stage5.cost_log.log_call"):
                import stage5

                # Ensure max is > 1 so attempt 1 still has retries left
                assert stage5.config.MAX_ENRICHMENT_ATTEMPTS > 1

                conn = MagicMock()
                result = stage5._enrich_candidate(candidate, campaign, conn)

        assert result["outcome"] == "crawler_failed_retry", (
            f"Expected 'crawler_failed_retry' on first failure (retries remain), "
            f"got: {result['outcome']}"
        )
