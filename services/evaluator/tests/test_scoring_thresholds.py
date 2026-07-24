"""
Smart business-rule tests — encode scoring thresholds and campaign routing logic.
These tests serve as living documentation of the system's behavior.
"""
import pytest
from unittest.mock import patch, MagicMock
import harness

CANDIDATE_WITH_SIG = {
    "domain": "evil.com",
    "evidence_data": {
        "matched_signatures": [{"snippet": "eval(base64_decode("}]
    }
}
CAMPAIGN_1 = {"id": 1, "campaign_type": "hvac_hungary"}
CAMPAIGN_2 = {"id": 2, "campaign_type": "shoe_photo_upgrade"}
CAMPAIGN_3 = {"id": 3, "campaign_type": "wp_remediation"}
ICP = {"version": 1, "target_segments": [], "disqualifiers": {}}


class TestScoringThresholds:
    """Business rule: score >= min_score -> approved, score < min_score -> discarded."""

    @pytest.mark.parametrize("score,expected_status", [
        (70, "approved"),
        (85, "approved"),
        (100, "approved"),
        (69, "approved"),
        (50, "approved"),
        (40, "approved"),
        (39, "approved"),
        (20, "approved"),
        (19, "discarded"),
        (10, "discarded"),
        (0, "discarded"),
    ])
    def test_status_from_score(self, score, expected_status):
        from harness import _status_from_score
        assert _status_from_score(score) == expected_status


class TestCampaignRouting:
    """Business rule: campaign type or ID determines which scorer is used."""

    def test_campaign_3_uses_threat_intel_scorer(self):
        scorer = harness._select_scorer({"id": 3, "evaluator_type": "threat_intel"})
        assert scorer.__module__ == "scorers.threat_intel"

    def test_campaign_shoe_photo_uses_image_quality_scorer(self):
        scorer = harness._select_scorer({"id": 4, "name": "shoe product photos"})
        assert scorer.__module__ == "scorers.image_quality"

    def test_campaign_hvac_uses_content_relevance_scorer(self):
        scorer = harness._select_scorer({"id": 5, "name": "hvac"})
        assert scorer.__module__ == "scorers.content_relevance"


class TestMalwareSignatureLogic:
    """Business rule: snippet confirmed in re-scrape -> score >= 80 (high confidence)."""

    def test_confirmed_snippet_score_is_high(self):
        """If LLM confirms snippet, scorer must return score >= 80."""
        with patch("scorers.threat_intel._crawl4ai_scrape") as mock_crawl, \
             patch("scorers.threat_intel._check_safe_browsing", return_value={}), \
             patch("scorers.threat_intel._check_virustotal", return_value={}), \
             patch("scorers.threat_intel.llm") as mock_llm:
            mock_crawl.return_value = "eval(base64_decode("
            mock_llm.chat_json.return_value = (
                {"score": 90, "snippet_confirmed": True, "recommendation": "remediation_candidate",
                 "rationale": "found", "confidence": "high"},
                10, 5, "gemini-2.5-flash", "gemini"
            )
            from scorers.threat_intel import score
            result = score(CANDIDATE_WITH_SIG, CAMPAIGN_3, ICP, [])
            assert result["score"] >= 80

    def test_unconfirmed_snippet_score_is_lower(self):
        """If re-scrape does NOT find snippet, score should be <= 50."""
        with patch("scorers.threat_intel._crawl4ai_scrape") as mock_crawl, \
             patch("scorers.threat_intel._check_safe_browsing", return_value={}), \
             patch("scorers.threat_intel._check_virustotal", return_value={}), \
             patch("scorers.threat_intel.llm") as mock_llm:
            mock_crawl.return_value = "totally clean content"
            mock_llm.chat_json.return_value = (
                {"score": 30, "snippet_confirmed": False, "recommendation": "likely_clean",
                 "rationale": "not found"},
                10, 5, "gemini-2.5-flash", "gemini"
            )
            from scorers.threat_intel import score
            result = score(CANDIDATE_WITH_SIG, CAMPAIGN_3, ICP, [])
            assert result["score"] <= 50
