import os
import sys
import pytest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Path setup — allow importing evaluator modules without package installation
# ---------------------------------------------------------------------------
EVALUATOR_DIR = os.path.join(os.path.dirname(__file__), "..")
if EVALUATOR_DIR not in sys.path:
    sys.path.insert(0, EVALUATOR_DIR)

from scorers.content_relevance import score


def test_score_valid_json(mocker):
    # Mock firecrawl_client
    mocker.patch(
        "scorers.content_relevance.firecrawl_client.scrape_domain_pages",
        return_value={"http://example.com": "Test Content"},
    )

    # Mock llm.chat_json on the imported reference
    valid_response = {
        "score": 85,
        "rationale": "Strong fit for Jenex.",
        "products_sold": ["Air ducts"],
        "matching_segments": ["HVAC installer"],
        "disqualifier_hits": [],
    }
    mocker.patch(
        "scorers.content_relevance.llm.chat_json",
        return_value=(valid_response, 100, 50, "gemini-3.6-flash-high", "gemini"),
    )

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
