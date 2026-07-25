import os
import sys
import pytest
from unittest.mock import MagicMock, patch

EVALUATOR_DIR = os.path.join(os.path.dirname(__file__), "..")
if EVALUATOR_DIR not in sys.path:
    sys.path.insert(0, EVALUATOR_DIR)

from scorers.content_relevance import score


def test_score_valid_json():
    with patch("scorers.content_relevance.firecrawl_client.scrape_domain_pages", return_value={"http://example.com": "Test Content"}), \
         patch("scorers.content_relevance.firecrawl_client.extract_image_urls", return_value=[]), \
         patch("scorers.content_relevance.llm.chat_json", return_value=({
             "score": 85,
             "rationale": "Strong fit for Jenex.",
             "products_sold": ["Air ducts"],
             "matching_segments": ["HVAC installer"],
             "disqualifier_hits": [],
         }, 100, 50, "gemini-3.6-flash-high", "gemini")):

        candidate = {"domain": "example.com", "company_name": "Example HVAC"}
        campaign = {}
        icp = {
            "target_segments": ["HVAC installer"],
            "keywords_hu": ["légtechnika"],
            "keywords_en": ["HVAC"],
            "disqualifiers": {"no_b2c": True},
        }
        few_shot = []

        result = score(candidate, campaign, icp, few_shot)

        assert result["score"] == 85
        assert result["rationale"] == "Strong fit for Jenex."
        assert "evidence_urls" in result
        assert result["evidence_data"]["matching_segments"] == ["HVAC installer"]
        assert result["model_used"] == "gemini-3.6-flash-high"
        assert result["provider"] == "gemini"


def test_score_clamps_to_0_100():
    with patch("scorers.content_relevance.firecrawl_client.scrape_domain_pages", return_value={"http://example.com": "Content"}), \
         patch("scorers.content_relevance.firecrawl_client.extract_image_urls", return_value=[]), \
         patch("scorers.content_relevance.llm.chat_json", return_value=({"score": 150}, 10, 5, "model", "gemini")):

        result = score({"domain": "example.com"}, {}, {}, [])
        assert result["score"] == 100

    with patch("scorers.content_relevance.firecrawl_client.scrape_domain_pages", return_value={"http://example.com": "Content"}), \
         patch("scorers.content_relevance.firecrawl_client.extract_image_urls", return_value=[]), \
         patch("scorers.content_relevance.llm.chat_json", return_value=({"score": -20}, 10, 5, "model", "gemini")):

        result = score({"domain": "example.com"}, {}, {}, [])
        assert result["score"] == 0


def test_score_handles_non_json():
    with patch("scorers.content_relevance.firecrawl_client.scrape_domain_pages", return_value={"http://example.com": "Content"}), \
         patch("scorers.content_relevance.firecrawl_client.extract_image_urls", return_value=[]), \
         patch("scorers.content_relevance.llm.chat_json", return_value=({"_raw": "raw error"}, 10, 5, "model", "gemini")):

        result = score({"domain": "example.com"}, {}, {}, [])
        assert result["score"] == 50
        assert "raw_response" in result["evidence_data"]


def test_score_with_images_uses_chat_vision():
    with patch("scorers.content_relevance._crawler_scrape", return_value=("Content", [{"src": "http://example.com/img1.jpg"}])), \
         patch("scorers.content_relevance.firecrawl_client.scrape_domain_pages", return_value={"http://example.com": "Content"}), \
         patch("scorers.content_relevance.firecrawl_client.extract_image_urls", return_value=["http://example.com/img1.jpg"]), \
         patch("scorers.content_relevance.llm.chat_vision", return_value=({
             "score": 90, "rationale": "Good HVAC images."
         }, 50, 20, "vision-model", "gemini")) as mock_vision, \
         patch("scorers.content_relevance.llm.chat_json") as mock_json:

        result = score({"domain": "example.com"}, {}, {}, [])
        assert result["score"] == 90
        assert mock_vision.called
        assert not mock_json.called
