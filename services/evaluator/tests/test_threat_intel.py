"""
Unit tests for the threat_intel scorer.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Path setup — allow importing from services/evaluator without installing
EVALUATOR_DIR = os.path.join(os.path.dirname(__file__), "..")
if EVALUATOR_DIR not in sys.path:
    sys.path.insert(0, EVALUATOR_DIR)

from scorers.threat_intel import score, _check_snippet_present


class TestThreatIntelScorer(unittest.TestCase):

    @patch("scorers.threat_intel.firecrawl_client.scrape_domain_pages")
    @patch("scorers.threat_intel.llm.chat_json")
    def test_score_confirmed_snippet(self, mock_chat_json, mock_scrape):
        mock_scrape.return_value = {"http://example.com": "This site has eval(base64_decode) malware!"}
        mock_chat_json.return_value = (
            {
                "score": 90,
                "snippet_confirmed": True,
                "malware_family": "Generic.Backdoor",
                "confidence": "high",
                "recommendation": "remediation_candidate",
                "rationale": "Found active infection"
            },
            100, 50, "gemini-3.6-flash-high", "gemini"
        )

        candidate = {
            "domain": "example.com",
            "evidence_data": {
                "matched_signatures": [
                    {"snippet": "eval(base64_decode", "malware_family": "Generic.Backdoor"}
                ]
            }
        }

        result = score(candidate, {}, {}, [])

        self.assertEqual(result["score"], 90)
        self.assertTrue(result["evidence_data"]["snippet_confirmed"])
        self.assertEqual(result["evidence_data"]["malware_family"], "Generic.Backdoor")
        self.assertEqual(result["evidence_data"]["confidence"], "high")
        self.assertEqual(result["evidence_data"]["recommendation"], "remediation_candidate")
        self.assertIn("eval(base64_decode", result["evidence_data"]["found_in_fresh_scrape"])

    @patch("scorers.threat_intel.firecrawl_client.scrape_domain_pages")
    @patch("scorers.threat_intel.llm.chat_json")
    def test_score_snippet_not_in_fresh_scrape(self, mock_chat_json, mock_scrape):
        mock_scrape.return_value = {"http://example.com": "This site is completely clean."}
        # In this case, the deterministic _check_snippet_present will return False.
        # Let's mock the LLM returning snippet_confirmed=False as well.
        mock_chat_json.return_value = (
            {
                "score": 35,
                "snippet_confirmed": False,
                "malware_family": "Generic.Backdoor",
                "confidence": "low",
                "recommendation": "likely_clean",
                "rationale": "Snippet not found"
            },
            100, 50, "gemini-3.6-flash-high", "gemini"
        )

        candidate = {
            "domain": "example.com",
            "evidence_data": {
                "matched_signatures": [
                    {"snippet": "eval(base64_decode", "malware_family": "Generic.Backdoor"}
                ]
            }
        }

        result = score(candidate, {}, {}, [])

        self.assertFalse(result["evidence_data"]["snippet_confirmed"])
        self.assertEqual(result["evidence_data"]["found_in_fresh_scrape"], [])

    def test_check_snippet_present_exact_match(self):
        content = "Some prefix code php eval(base64_decode('xyz')) some suffix"
        snippets = ["eval(base64_decode"]
        confirmed, found = _check_snippet_present(content, snippets)
        self.assertTrue(confirmed)
        self.assertEqual(found, ["eval(base64_decode"])

    def test_check_snippet_present_no_match(self):
        content = "This is a clean page without any malware."
        snippets = ["eval(base64_decode"]
        confirmed, found = _check_snippet_present(content, snippets)
        self.assertFalse(confirmed)
        self.assertEqual(found, [])

    @patch("scorers.threat_intel.firecrawl_client.scrape_domain_pages")
    @patch("scorers.threat_intel.llm.chat_json")
    def test_score_conservative_default_on_non_json(self, mock_chat_json, mock_scrape):
        mock_scrape.return_value = {"http://example.com": "Clean content"}
        mock_chat_json.return_value = (
            {"_raw": "I am not JSON response!"},
            10, 5, "gemini-3.6-flash-high", "gemini"
        )

        candidate = {
            "domain": "example.com",
            "evidence_data": {
                "matched_signatures": [
                    {"snippet": "eval(base64_decode", "malware_family": "Generic.Backdoor"}
                ]
            }
        }

        result = score(candidate, {}, {}, [])

        self.assertEqual(result["score"], 30)
        self.assertFalse(result["evidence_data"]["snippet_confirmed"])
        self.assertEqual(result["evidence_data"]["raw_response"], "I am not JSON response!")

    @patch("scorers.threat_intel.firecrawl_client.scrape_domain_pages")
    @patch("scorers.threat_intel.llm.chat_json")
    def test_score_with_empty_evidence_data(self, mock_chat_json, mock_scrape):
        mock_scrape.return_value = {"http://example.com": "No signatures"}
        mock_chat_json.return_value = (
            {
                "score": 10,
                "snippet_confirmed": False,
                "malware_family": "unknown",
                "confidence": "low",
                "recommendation": "likely_clean",
                "rationale": "No threat found"
            },
            10, 5, "gemini-3.6-flash-high", "gemini"
        )

        candidate = {
            "domain": "example.com",
            "evidence_data": {}
        }

        # This should execute gracefully without raising any KeyError or other exceptions
        result = score(candidate, {}, {}, [])

        self.assertEqual(result["score"], 10)
        self.assertEqual(result["evidence_data"]["matched_signatures"], [])
