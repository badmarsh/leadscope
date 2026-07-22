"""
Unit tests for the image_quality scorer.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Path setup — allow importing from services/evaluator without installing
EVALUATOR_DIR = os.path.join(os.path.dirname(__file__), "..")
if EVALUATOR_DIR not in sys.path:
    sys.path.insert(0, EVALUATOR_DIR)

from scorers.image_quality import score


class TestImageQualityScorer(unittest.TestCase):

    @patch("scorers.image_quality.firecrawl_client.scrape_domain_pages")
    @patch("scorers.image_quality.firecrawl_client.extract_image_urls")
    @patch("scorers.image_quality.llm.chat_vision")
    def test_score_with_images(self, mock_chat_vision, mock_extract, mock_scrape):
        # Setup mocks
        mock_scrape.return_value = {"http://example.com/shop": "A page with image markdown ![alt](img.jpg)"}
        mock_extract.return_value = ["http://example.com/img1.jpg", "http://example.com/img2.jpg", "http://example.com/img3.jpg"]

        mock_chat_vision.return_value = (
            {
                "score": 70,
                "photo_quality": "poor",
                "business_activity": "active",
                "product_count_estimate": 50,
                "issues_found": ["low resolution"]
            },
            100, 50, "gemini-3.1-flash-image", "gemini"
        )

        candidate = {"domain": "example.com", "company_name": "Example Shop"}
        campaign = {}
        icp = {}
        few_shot = []

        result = score(candidate, campaign, icp, few_shot)

        # Assertions
        self.assertEqual(result["score"], 70)
        self.assertEqual(result["evidence_data"]["photo_quality"], "poor")
        self.assertEqual(result["evidence_data"]["business_activity"], "active")
        self.assertEqual(result["evidence_data"]["product_count_estimate"], 50)
        self.assertEqual(result["evidence_data"]["issues_found"], ["low resolution"])
        self.assertEqual(len(result["evidence_data"]["images_analyzed"]), 3)
        self.assertEqual(result["model_used"], "gemini-3.1-flash-image")
        self.assertEqual(result["provider"], "gemini")

        mock_chat_vision.assert_called_once()

    @patch("scorers.image_quality.firecrawl_client.scrape_domain_pages")
    @patch("scorers.image_quality.firecrawl_client.extract_image_urls")
    @patch("scorers.image_quality.llm.chat_json")
    @patch("scorers.image_quality.llm.chat_vision")
    def test_score_without_images_falls_back_to_text(self, mock_chat_vision, mock_chat_json, mock_extract, mock_scrape):
        mock_scrape.return_value = {"http://example.com/shop": "No images here"}
        mock_extract.return_value = []

        mock_chat_json.return_value = (
            {
                "score": 40,
                "photo_quality": "unknown",
                "business_activity": "low",
                "product_count_estimate": 0,
                "issues_found": []
            },
            80, 40, "gemini-3.1-flash-image", "gemini"
        )

        candidate = {"domain": "example.com"}
        result = score(candidate, {}, {}, [])

        self.assertEqual(result["score"], 40)
        self.assertEqual(result["evidence_data"]["images_analyzed"], [])
        mock_chat_json.assert_called_once()
        mock_chat_vision.assert_not_called()

    @patch("scorers.image_quality.firecrawl_client.scrape_domain_pages")
    @patch("scorers.image_quality.firecrawl_client.extract_image_urls")
    @patch("scorers.image_quality.llm.chat_vision")
    def test_score_clamps_above_100(self, mock_chat_vision, mock_extract, mock_scrape):
        mock_scrape.return_value = {"http://example.com/shop": "Images here"}
        mock_extract.return_value = ["img1.jpg"]
        mock_chat_vision.return_value = (
            {"score": 150, "photo_quality": "poor"},
            10, 5, "model", "gemini"
        )

        candidate = {"domain": "example.com"}
        result = score(candidate, {}, {}, [])

        self.assertEqual(result["score"], 100)

    @patch("scorers.image_quality.firecrawl_client.scrape_domain_pages")
    @patch("scorers.image_quality.firecrawl_client.extract_image_urls")
    @patch("scorers.image_quality.llm.chat_vision")
    def test_score_clamps_below_0(self, mock_chat_vision, mock_extract, mock_scrape):
        mock_scrape.return_value = {"http://example.com/shop": "Images here"}
        mock_extract.return_value = ["img1.jpg"]
        mock_chat_vision.return_value = (
            {"score": -10, "photo_quality": "good"},
            10, 5, "model", "gemini"
        )

        candidate = {"domain": "example.com"}
        result = score(candidate, {}, {}, [])

        self.assertEqual(result["score"], 0)

    @patch("scorers.image_quality.firecrawl_client.scrape_domain_pages")
    @patch("scorers.image_quality.firecrawl_client.extract_image_urls")
    @patch("scorers.image_quality.llm.chat_vision")
    def test_score_handles_non_json_response(self, mock_chat_vision, mock_extract, mock_scrape):
        mock_scrape.return_value = {"http://example.com/shop": "Images here"}
        mock_extract.return_value = ["img1.jpg"]
        mock_chat_vision.return_value = (
            {"_raw": "I cannot analyze..."},
            10, 5, "model", "gemini"
        )

        candidate = {"domain": "example.com"}
        result = score(candidate, {}, {}, [])

        self.assertEqual(result["score"], 50)
        self.assertEqual(result["evidence_data"]["images_found"], 1)
        self.assertIn("raw_response", result["evidence_data"])
        self.assertEqual(result["evidence_data"]["raw_response"], "I cannot analyze...")
