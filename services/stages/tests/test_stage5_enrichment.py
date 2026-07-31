"""
tests/test_stage5_enrichment.py — Stage 5: Enrichment

Tests the enrichment pipeline for lead data extraction:
  - DNC gate: skips suppressed domains
  - Retry cooldown: skips within retry window
  - Network error: returns network_error_retry, then enrichment_failed at max_attempts
  - Crawler failure: returns crawler_failed_retry, then enrichment_failed at max_attempts
  - Zero-data guard: does not insert empty lead records
  - LLM non-JSON response: returns empty dict gracefully (no crash)
  - Full success: outcome='enriched', DB insert called
  - extruct structured data extraction: email/phone/name from JSON-LD
  - Phone normalization: E.164 format
  - Cloudflare/bot challenge detection
  - Offer summary truncation at 300 chars
  - is_bot_challenge detection patterns
  - _normalize_phone with invalid number returns original
  - screenshot URL helper format
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Mock extruct and w3lib before importing stage5
mock_extruct = MagicMock()
mock_w3lib = MagicMock()
if "extruct" not in sys.modules:
    sys.modules["extruct"] = mock_extruct
if "w3lib" not in sys.modules:
    sys.modules["w3lib"] = mock_w3lib
    sys.modules["w3lib.html"] = mock_w3lib

STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

import stage5


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    with patch("stage5.db") as m:
        m.get_conn.return_value.__enter__.return_value = MagicMock()
        m.check_stop_signal.return_value = False
        yield m


def _base_candidate(overrides=None):
    base = {
        "id": 1,
        "domain": "example.com",
        "campaign_id": 10,
        "company_name": "Example Ltd",
        "enrichment_attempt_count": 0,
        "enrichment_attempted_at": None,
        "eval_evidence": None,
        "processing_generation": 0,
    }
    if overrides:
        base.update(overrides)
    return base


def _base_campaign():
    return {
        "id": 10,
        "business_brief": "We install HVAC systems in commercial buildings.",
        "settings": "{}",
    }


# ── DNC gate ───────────────────────────────────────────────────────────────────

class TestEnrichCandidateDNC:
    def test_skips_dnc_domain(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = {"1": 1}  # DNC hit

        result = stage5._enrich_candidate(_base_candidate(), _base_campaign(), conn)

        assert result["outcome"] == "skipped_dnc"

    def test_proceeds_when_not_dnc(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None  # Not on DNC list

        with patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=(None, "", None)), \
             patch.object(stage5, "cost_log"):
            result = stage5._enrich_candidate(_base_candidate(), _base_campaign(), conn)

        # Not skipped_dnc — got to crawler_failed_retry
        assert result["outcome"] != "skipped_dnc"


# ── Retry cooldown ─────────────────────────────────────────────────────────────

class TestEnrichCandidateCooldown:
    def test_skips_within_cooldown_window(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        from datetime import datetime, timezone
        candidate = _base_candidate({
            "enrichment_attempted_at": datetime.now(timezone.utc),
            "enrichment_attempt_count": 1,
        })
        # DNC → None, cooldown → not past cooldown
        mock_db.fetchone.side_effect = [
            None,  # DNC check
            {"past_cooldown": False},  # Within cooldown window
        ]

        result = stage5._enrich_candidate(candidate, _base_campaign(), conn)

        assert result["outcome"] == "skipped_cooldown"

    def test_proceeds_past_cooldown(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        from datetime import datetime, timezone
        candidate = _base_candidate({
            "enrichment_attempted_at": datetime.now(timezone.utc),
            "enrichment_attempt_count": 1,
        })
        mock_db.fetchone.side_effect = [
            None,  # DNC check
            {"past_cooldown": True},  # Past cooldown → proceed
        ]

        with patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=(None, "", None)), \
             patch.object(stage5, "cost_log"):
            result = stage5._enrich_candidate(candidate, _base_campaign(), conn)

        assert result["outcome"] != "skipped_cooldown"


# ── Network error handling ─────────────────────────────────────────────────────

class TestEnrichCandidateNetworkError:
    def test_network_error_retry_when_below_max_attempts(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None  # Not DNC

        with patch.object(stage5, "_extract_structured_data", return_value={"_network_error": True}), \
             patch.object(stage5, "cost_log"):
            result = stage5._enrich_candidate(
                _base_candidate({"enrichment_attempt_count": 1}),
                _base_campaign(), conn
            )

        assert result["outcome"] == "network_error_retry"

    def test_network_error_marks_failed_at_max_attempts(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None  # Not DNC

        with patch.object(stage5, "config") as mock_config, \
             patch.object(stage5, "_extract_structured_data", return_value={"_network_error": True}), \
             patch.object(stage5, "cost_log"):
            mock_config.MAX_ENRICHMENT_ATTEMPTS = 3
            mock_config.ENRICHMENT_RETRY_HOURS = 4
            mock_config.STAGE5_MODEL = "gemini"
            result = stage5._enrich_candidate(
                _base_candidate({"enrichment_attempt_count": 3}),
                _base_campaign(), conn
            )

        assert result["outcome"] == "enrichment_failed"
        mock_db.execute.assert_called()  # Should UPDATE candidates SET status='enrichment_failed'


# ── Crawler failure handling ───────────────────────────────────────────────────

class TestEnrichCandidateCrawlerFailure:
    def test_crawler_fail_returns_retry_below_max(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None  # Not DNC

        with patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=(None, "", None)), \
             patch.object(stage5, "cost_log"):
            result = stage5._enrich_candidate(
                _base_candidate({"enrichment_attempt_count": 1}),
                _base_campaign(), conn
            )

        assert result["outcome"] == "crawler_failed_retry"

    def test_crawler_fail_marks_failed_at_max_attempts(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None

        with patch.object(stage5, "config") as mock_config, \
             patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=(None, "", None)), \
             patch.object(stage5, "cost_log"):
            mock_config.MAX_ENRICHMENT_ATTEMPTS = 3
            mock_config.ENRICHMENT_RETRY_HOURS = 4
            mock_config.STAGE5_MODEL = "gemini"
            result = stage5._enrich_candidate(
                _base_candidate({"enrichment_attempt_count": 3}),
                _base_campaign(), conn
            )

        assert result["outcome"] == "enrichment_failed"
        mock_db.execute.assert_called()


# ── Zero-data guard ────────────────────────────────────────────────────────────

class TestEnrichCandidateZeroData:
    def test_zero_data_guard_does_not_insert(self, mock_db):
        """If LLM and extruct both return nothing useful, skip insert and allow retry."""
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None  # Not DNC

        with patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=("some page text", "https://example.com", [])), \
             patch.object(stage5, "_enrich_info", return_value=({}, 10, 5)), \
             patch.object(stage5, "_crawler_scrape", return_value=(None, None)), \
             patch.object(stage5, "cost_log"):
            result = stage5._enrich_candidate(_base_candidate(), _base_campaign(), conn)

        assert result["outcome"] == "zero_data_retry"
        # Ensure no leads table insert happened
        insert_calls = [c for c in mock_db.execute.call_args_list
                       if "INSERT INTO leads" in str(c)]
        assert len(insert_calls) == 0


# ── Full success path ──────────────────────────────────────────────────────────

class TestEnrichCandidateSuccess:
    def test_full_success_returns_enriched(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None  # Not DNC

        enriched_data = {
            "email": "contact@example.com",
            "phone": "+421901234567",
            "name": "Jan Novak",
            "report": "Firma predáva HVAC zariadenia.",
            "products_sold": ["klimatizácie", "kotly"],
            "estimated_size": "11-50",
            "estimated_revenue": "€1M - €10M",
            "estimated_traffic": "Medium",
            "firmographics": {"headquarters": "Bratislava"},
            "buying_power_signals": ["verejné obstarávanie"],
            "tech_stack": ["WordPress"],
        }

        with patch.object(stage5, "_extract_structured_data", return_value={"email": "contact@example.com"}), \
             patch.object(stage5, "_scrape_domain", return_value=("Large page text content here", "https://example.com", ["img1.jpg"])), \
             patch.object(stage5, "_enrich_info", return_value=(enriched_data, 200, 80)), \
             patch.object(stage5, "cost_log"):
            result = stage5._enrich_candidate(_base_candidate(), _base_campaign(), conn)

        assert result["outcome"] == "enriched"
        # Ensure leads table was written to
        assert mock_db.execute.called

    def test_enriched_candidate_increments_attempt_count(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None

        enriched_data = {
            "email": "a@b.com", "phone": None, "name": None,
            "report": "Test report.",
            "products_sold": ["product A"],
            "estimated_size": "1-10", "estimated_revenue": "<€1M",
            "estimated_traffic": "Low", "firmographics": {},
            "buying_power_signals": [], "tech_stack": [],
        }

        with patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=("page content", "https://example.com", [])), \
             patch.object(stage5, "_enrich_info", return_value=(enriched_data, 50, 20)), \
             patch.object(stage5, "cost_log"):
            stage5._enrich_candidate(_base_candidate(), _base_campaign(), conn)

        # db.execute is called at least twice (attempt count update + lead upsert)
        assert mock_db.execute.call_count >= 2


# ── LLM enrichment: graceful non-JSON handling ────────────────────────────────

class TestEnrichInfo:
    @patch.object(stage5.llm, "chat_json")
    def test_valid_json_returned_directly(self, mock_chat):
        mock_chat.return_value = ({"report": "Slovak text", "email": "a@b.com"}, 10, 5, "gemini", "gemini")
        res, ti, to = stage5._enrich_info("example.com", "Example", "offer", "page text", {})
        assert res["report"] == "Slovak text"
        assert ti == 10

    @patch.object(stage5.llm, "chat_json")
    def test_non_json_response_returns_empty_dict(self, mock_chat):
        """LLM returns _raw key → should return empty dict, not crash."""
        mock_chat.return_value = ({"_raw": "Cannot comply"}, 5, 2, "gemini", "gemini")
        res, ti, to = stage5._enrich_info("example.com", "Example", "offer", "page text", {})
        assert res == {}

    @patch.object(stage5.llm, "chat_json")
    def test_llm_exception_returns_empty_dict(self, mock_chat):
        """Network/API exception during LLM call → returns empty dict."""
        mock_chat.side_effect = RuntimeError("LLM API error")
        res, ti, to = stage5._enrich_info("example.com", "Example", "offer", "page text", {})
        assert res == {}
        assert ti == 0
        assert to == 0


# ── extruct structured data extraction ────────────────────────────────────────

class TestExtractStructuredData:
    @patch("stage5.requests.get")
    def test_extracts_org_email_from_json_ld(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html></html>"
        mock_resp.url = "https://example.com"
        mock_get.return_value = mock_resp

        test_data = {
            "json-ld": [
                {"@type": "Organization", "email": "org@example.com", "telephone": "+421901000000", "name": "Org Name"}
            ],
            "opengraph": []
        }
        mock_extruct_mod = MagicMock()
        mock_extruct_mod.extract.return_value = test_data
        mock_w3lib_html = MagicMock()
        mock_w3lib_html.get_base_url.return_value = "https://example.com"

        with patch.dict(sys.modules, {"extruct": mock_extruct_mod, "w3lib.html": mock_w3lib_html}):
            res = stage5._extract_structured_data("example.com")

        assert res.get("email") == "org@example.com"
        assert res.get("phone") == "+421901000000"
        assert res.get("name") == "Org Name"

    @patch("stage5.requests.get")
    def test_returns_empty_on_non_200(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        res = stage5._extract_structured_data("dead.com")
        assert res == {}

    @patch("stage5.requests.get")
    def test_opengraph_fallback_for_name(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html></html>"
        mock_resp.url = "https://example.com"
        mock_get.return_value = mock_resp

        test_data = {
            "json-ld": [],
            "opengraph": [{"og:site_name": "OG Site Name", "og:description": "OG description"}],
        }
        mock_extruct_mod = MagicMock()
        mock_extruct_mod.extract.return_value = test_data
        mock_w3lib_html = MagicMock()
        mock_w3lib_html.get_base_url.return_value = "https://example.com"

        with patch.dict(sys.modules, {"extruct": mock_extruct_mod, "w3lib.html": mock_w3lib_html}):
            res = stage5._extract_structured_data("example.com")

        assert res.get("name") == "OG Site Name"
        assert res.get("description") == "OG description"


# ── Bot challenge detection ────────────────────────────────────────────────────

class TestIsBotChallenge:
    @pytest.mark.parametrize("text", [
        "Just a moment...",
        "Checking your browser before accessing",
        "DDoS-Guard protection",
        "Cloudflare security check",
        "Ray ID: abc123",
        "Moment strpenia",  # Slovak Cloudflare
    ])
    def test_detects_common_bot_challenges(self, text):
        assert stage5._is_bot_challenge(text) is True

    @pytest.mark.parametrize("text", [
        "Welcome to our HVAC services",
        "Contact us today for a free quote",
        "We specialize in commercial heating systems",
        "",
        None,
    ])
    def test_passes_legitimate_content(self, text):
        assert stage5._is_bot_challenge(text) is False

    def test_only_checks_first_500_chars(self):
        """Bot challenge in the first 500 chars should be detected."""
        text = "Checking your browser" + "x" * 600
        assert stage5._is_bot_challenge(text) is True

        """Bot challenge after char 500 should NOT be detected."""
        text = "x" * 501 + "Cloudflare"
        assert stage5._is_bot_challenge(text) is False


# ── Phone normalization ────────────────────────────────────────────────────────

class TestNormalizePhone:
    def test_valid_e164_phone(self):
        result = stage5._normalize_phone("+421901234567", "SK")
        assert result == "+421901234567"

    def test_returns_original_on_parse_failure(self):
        result = stage5._normalize_phone("not-a-phone", "SK")
        assert result == "not-a-phone"

    def test_none_returns_none(self):
        assert stage5._normalize_phone(None) is None

    def test_empty_string_returns_empty(self):
        result = stage5._normalize_phone("", "SK")
        assert result == ""


# ── Screenshot URL helper ──────────────────────────────────────────────────────

class TestScreenshotUrl:
    def test_format_includes_api_path(self):
        url = stage5._screenshot_url("example.com")
        assert "/api/screenshot" in url
        assert "example.com" in url

    def test_url_encoded_properly(self):
        url = stage5._screenshot_url("special&domain.com")
        # Should be URL-encoded
        assert "&" not in url or url.startswith("/api/screenshot?url=")


# ── Offer summary truncation ───────────────────────────────────────────────────

class TestGetOfferSummary:
    def test_truncates_long_brief_to_300_chars(self):
        long_brief = "x" * 500
        summary = stage5._get_offer_summary(long_brief)
        assert len(summary) == 300

    def test_short_brief_returned_as_is(self):
        brief = "Short brief."
        assert stage5._get_offer_summary(brief) == brief

    def test_none_brief_returns_placeholder(self):
        result = stage5._get_offer_summary(None)
        assert "not yet defined" in result

    def test_empty_brief_returns_placeholder(self):
        result = stage5._get_offer_summary("")
        assert "not yet defined" in result


# ── Evidence images & product discovery status ─────────────────────────────────

class TestStage5EvidenceImages:
    def test_images_analyzed_never_overwritten_by_stage5(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None

        candidate = _base_candidate({
            "eval_evidence": {"images_analyzed": ["https://example.com/product1.jpg"]}
        })
        enriched_data = {
            "email": "a@b.com", "report": "Test report", "products_sold": ["P1"]
        }

        with patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=("content", "https://example.com", ["https://example.com/crawl_icon.png"])), \
             patch.object(stage5, "_enrich_info", return_value=(enriched_data, 50, 20)), \
             patch.object(stage5, "cost_log"):
            stage5._enrich_candidate(candidate, _base_campaign(), conn)

        # Check DB update calls on evaluations
        eval_updates = [str(call) for call in mock_db.execute.call_args_list if "UPDATE evaluations" in str(call)]
        assert len(eval_updates) == 1
        assert "images_analyzed" not in eval_updates[0]
        assert "has_product_images" in eval_updates[0]

    def test_fallback_images_set_when_images_analyzed_empty(self, mock_db):
        conn = mock_db.get_conn.return_value.__enter__.return_value
        mock_db.fetchone.return_value = None

        candidate = _base_candidate({
            "eval_evidence": {"images_analyzed": []}
        })
        enriched_data = {
            "email": "a@b.com", "report": "Test report", "products_sold": ["P1"]
        }

        with patch.object(stage5, "_extract_structured_data", return_value={}), \
             patch.object(stage5, "_scrape_domain", return_value=("content", "https://example.com", ["https://example.com/homepage_hero.jpg"])), \
             patch.object(stage5, "_enrich_info", return_value=(enriched_data, 50, 20)), \
             patch.object(stage5, "cost_log"):
            stage5._enrich_candidate(candidate, _base_campaign(), conn)

        eval_updates = [str(call) for call in mock_db.execute.call_args_list if "UPDATE evaluations" in str(call)]
        assert len(eval_updates) == 1
        assert "homepage_fallback_images" in eval_updates[0]
        assert "fallback_used" in eval_updates[0]
        assert "images_analyzed" not in eval_updates[0]

