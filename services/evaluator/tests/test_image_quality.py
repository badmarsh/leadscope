import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import patch, MagicMock

from scorers.image_quality import score

@patch('scorers.image_quality._crawler_scrape')
@patch('scorers.image_quality.firecrawl_client')
@patch('scorers.image_quality.llm')
def test_score_with_images(mock_llm, mock_firecrawl, mock_crawler):
    mock_firecrawl._discover_product_paths.return_value = ["/products"]
    mock_firecrawl.extract_product_grid_images.return_value = ["http://example.com/img1.jpg", "http://example.com/img2.jpg", "http://example.com/img3.jpg"]
    mock_crawler.return_value = ("some content", "<html>some html</html>")
    mock_llm.chat_vision.return_value = ({"score": 70, "photo_quality": "poor", "business_activity": "active", "product_count_estimate": 50, "issues_found": ["low resolution"]}, 10, 5, "gemini-2.5-flash", "gemini")

    candidate = {"domain": "example.com"}
    campaign = {"id": 1, "business_brief": "test"}
    icp = {"version": 1}

    result = score(candidate, campaign, icp, [])

    assert result["score"] == 70
    assert "photo_quality" in result["evidence_data"]
    assert len(result["evidence_data"]["images_analyzed"]) == 3
    assert result["model_used"] == "gemini-2.5-flash"

@patch('scorers.image_quality._crawler_scrape')
@patch('scorers.image_quality.firecrawl_client')
@patch('scorers.image_quality.llm')
def test_score_without_images_falls_back_to_text(mock_llm, mock_firecrawl, mock_crawler):
    mock_firecrawl._discover_product_paths.return_value = ["/"]
    mock_firecrawl.extract_product_grid_images.return_value = []
    mock_crawler.return_value = ("some content", "<html>some html</html>")
    mock_llm.chat_json.return_value = ({"score": 60, "rationale": "no images"}, 10, 5, "gemini-2.5-flash", "gemini")

    candidate = {"domain": "example.com"}
    campaign = {"id": 1, "business_brief": "test"}
    icp = {"version": 1}

    result = score(candidate, campaign, icp, [])
    
    assert mock_llm.chat_json.called
    assert not mock_llm.chat_vision.called

@patch('scorers.image_quality._crawler_scrape')
@patch('scorers.image_quality.firecrawl_client')
@patch('scorers.image_quality.llm')
def test_score_clamps_above_100(mock_llm, mock_firecrawl, mock_crawler):
    mock_firecrawl._discover_product_paths.return_value = ["/"]
    mock_firecrawl.extract_product_grid_images.return_value = ["http://example.com/img.jpg"]
    mock_crawler.return_value = ("some content", "<html>some html</html>")
    mock_llm.chat_vision.return_value = ({"score": 150}, 10, 5, "model", "gemini")

    candidate = {"domain": "example.com"}
    campaign = {"id": 1}
    icp = {"version": 1}

    result = score(candidate, campaign, icp, [])
    assert result["score"] == 100

@patch('scorers.image_quality._crawler_scrape')
@patch('scorers.image_quality.firecrawl_client')
@patch('scorers.image_quality.llm')
def test_score_clamps_below_0(mock_llm, mock_firecrawl, mock_crawler):
    mock_firecrawl._discover_product_paths.return_value = ["/"]
    mock_firecrawl.extract_product_grid_images.return_value = ["http://example.com/img.jpg"]
    mock_crawler.return_value = ("some content", "<html>some html</html>")
    mock_llm.chat_vision.return_value = ({"score": -10}, 10, 5, "model", "gemini")

    candidate = {"domain": "example.com"}
    campaign = {"id": 1}
    icp = {"version": 1}

    result = score(candidate, campaign, icp, [])
    assert result["score"] == 0

@patch('scorers.image_quality._crawler_scrape')
@patch('scorers.image_quality.firecrawl_client')
@patch('scorers.image_quality.llm')
def test_score_handles_non_json_response(mock_llm, mock_firecrawl, mock_crawler):
    mock_firecrawl._discover_product_paths.return_value = ["/"]
    mock_firecrawl.extract_product_grid_images.return_value = ["http://example.com/img.jpg"]
    mock_crawler.return_value = ("some content", "<html>some html</html>")
    mock_llm.chat_vision.return_value = ({"_raw": "I cannot analyze..."}, 10, 5, "model", "gemini")

    candidate = {"domain": "example.com"}
    campaign = {"id": 1}
    icp = {"version": 1}

    result = score(candidate, campaign, icp, [])
    assert result["score"] == 50

@patch('scorers.image_quality._crawler_scrape')
@patch('scorers.image_quality.firecrawl_client')
@patch('scorers.image_quality.llm')
def test_score_early_exit_dead_site(mock_llm, mock_firecrawl, mock_crawler):
    # No social media, copyright 2020 -> older than 2 years -> dead
    mock_firecrawl._discover_product_paths.return_value = ["/"]
    mock_firecrawl.extract_product_grid_images.return_value = []
    mock_crawler.return_value = ("Welcome. Copyright 2020.", "<html>some html</html>")
    mock_firecrawl.detect_tech_stack.return_value = []
    
    candidate = {"domain": "example.com"}
    campaign = {"id": 1}
    icp = {"version": 1}

    result = score(candidate, campaign, icp, [])
    assert result["score"] == 0
    assert result["evidence_data"]["business_activity"] == "inactive"
    assert not mock_llm.chat_vision.called
    assert not mock_llm.chat_json.called
