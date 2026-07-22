import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scorers.threat_intel import score, _check_snippet_present

CANDIDATE_WITH_SIG = {
    "domain": "evil-wp.com",
    "evidence_data": {
        "matched_signatures": [
            {"snippet": "eval(base64_decode(", "malware_family": "Generic.Backdoor", "confidence": "high"}
        ]
    }
}
CANDIDATE_NO_SIG = {"domain": "clean-site.com", "evidence_data": {}}
CAMPAIGN = {"id": 3}
ICP = {"version": 1}


# ── _check_snippet_present ────────────────────────────────────────────────────

def test_snippet_present_exact_match():
    present, found = _check_snippet_present(
        "<script>eval(base64_decode('abc'));</script>", ["eval(base64_decode("]
    )
    assert present is True
    assert "eval(base64_decode(" in found

def test_snippet_present_case_insensitive():
    present, found = _check_snippet_present(
        "EVAL(BASE64_DECODE('abc'));", ["eval(base64_decode("]
    )
    assert present is True

def test_snippet_not_present():
    present, found = _check_snippet_present("<html>clean</html>", ["eval(base64_decode("])
    assert present is False
    assert found == []

def test_snippet_present_multiple_patterns():
    """Multiple snippets — finds the first match."""
    present, found = _check_snippet_present(
        "document.write(unescape('%3Cscript%3E'));",
        ["eval(base64_decode(", "document.write(unescape("]
    )
    assert present is True
    assert len(found) == 1


# ── score() — Crawl4AI path ───────────────────────────────────────────────────

@patch("scorers.threat_intel._check_virustotal", return_value={})
@patch("scorers.threat_intel._check_safe_browsing", return_value={})
@patch("scorers.threat_intel._crawl4ai_scrape")
@patch("scorers.threat_intel.llm")
def test_score_snippet_confirmed_in_fresh_scrape(mock_llm, mock_crawl, mock_sb, mock_vt):
    """Snippet found in live scrape -> LLM should be called with snippet_confirmed=True evidence."""
    mock_crawl.return_value = "some malicious eval(base64_decode('QWxhZGRpbg==')) code"
    mock_llm.chat_json.return_value = (
        {"score": 90, "snippet_confirmed": True, "malware_family": "Generic.Backdoor",
         "confidence": "high", "recommendation": "remediation_candidate", "rationale": "Found it."},
        10, 5, "gemini-2.5-flash", "gemini"
    )
    result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
    assert result["score"] == 90
    assert result["evidence_data"]["snippet_confirmed"] is True
    assert result["evidence_data"]["recommendation"] == "remediation_candidate"
    assert "pages_scraped" in result["evidence_data"]
    mock_llm.chat_json.assert_called_once()

@patch("scorers.threat_intel._check_virustotal", return_value={})
@patch("scorers.threat_intel._check_safe_browsing", return_value={})
@patch("scorers.threat_intel._crawl4ai_scrape")
@patch("scorers.threat_intel.llm")
def test_score_snippet_not_confirmed_in_fresh_scrape(mock_llm, mock_crawl, mock_sb, mock_vt):
    """Snippet NOT found in re-scrape -> score should reflect unconfirmed state."""
    mock_crawl.return_value = "clean content here"
    mock_llm.chat_json.return_value = (
        {"score": 30, "snippet_confirmed": False, "recommendation": "likely_clean", "rationale": "Clean."},
        10, 5, "gemini-2.5-flash", "gemini"
    )
    result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
    assert result["evidence_data"]["snippet_confirmed"] is False
    assert result["score"] == 30

@patch("scorers.threat_intel._check_virustotal", return_value={})
@patch("scorers.threat_intel._check_safe_browsing", return_value={})
@patch("scorers.threat_intel._crawl4ai_scrape", return_value=None)
@patch("scorers.threat_intel.llm")
def test_score_crawl_returns_empty_still_calls_llm(mock_llm, mock_crawl, mock_sb, mock_vt):
    """Even if Crawl4AI returns no content, LLM is still called for a final verdict."""
    mock_llm.chat_json.return_value = (
        {"score": 30, "recommendation": "needs_manual_check", "rationale": "No content."},
        5, 3, "gemini-2.5-flash", "gemini"
    )
    result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
    mock_llm.chat_json.assert_called_once()
    assert result["score"] == 30

@patch("scorers.threat_intel._check_virustotal", return_value={})
@patch("scorers.threat_intel._check_safe_browsing", return_value={})
@patch("scorers.threat_intel._crawl4ai_scrape")
@patch("scorers.threat_intel.llm")
def test_score_conservative_default_on_non_json_llm(mock_llm, mock_crawl, mock_sb, mock_vt):
    """If LLM returns garbage, scorer must return a safe default score (30) not crash."""
    mock_crawl.return_value = "some content"
    mock_llm.chat_json.return_value = ({"_raw": "I cannot answer."}, 5, 3, "gemini-2.5-flash", "gemini")
    result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
    assert result["score"] == 30

@patch("scorers.threat_intel._check_virustotal", return_value={})
@patch("scorers.threat_intel._check_safe_browsing", return_value={})
@patch("scorers.threat_intel._crawl4ai_scrape")
@patch("scorers.threat_intel.llm")
def test_score_no_signatures_skips_scrape_and_calls_llm(mock_llm, mock_crawl, mock_sb, mock_vt):
    """Candidate with no matched_signatures should still go through LLM for final verdict."""
    mock_llm.chat_json.return_value = (
        {"score": 10, "recommendation": "confirmed_clean", "rationale": "No signals."},
        5, 3, "gemini-2.5-flash", "gemini"
    )
    result = score(CANDIDATE_NO_SIG, CAMPAIGN, ICP, [])
    assert result["score"] == 10

@patch("scorers.threat_intel._check_virustotal", return_value={})
@patch("scorers.threat_intel._check_safe_browsing", return_value={})
@patch("scorers.threat_intel._crawl4ai_scrape")
@patch("scorers.threat_intel.llm")
def test_score_result_always_contains_required_keys(mock_llm, mock_crawl, mock_sb, mock_vt):
    """Score result must always have score, evidence_data, model_used, provider, rationale."""
    mock_crawl.return_value = "content"
    mock_llm.chat_json.return_value = (
        {"score": 50, "rationale": "ok", "recommendation": "needs_manual_check"},
        5, 3, "gemini-2.5-flash", "gemini"
    )
    result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
    for key in ("score", "evidence_data", "model_used", "provider", "rationale"):
        assert key in result, f"Missing key: {key}"

@patch("requests.get", side_effect=Exception("VT timeout"))
@patch("requests.post", side_effect=Exception("SB timeout"))
@patch("scorers.threat_intel._crawl4ai_scrape")
@patch("scorers.threat_intel.llm")
def test_score_reputation_api_failure_does_not_crash(mock_llm, mock_crawl, mock_sb_post, mock_vt_get):
    """If reputation APIs fail (timeout/network), scoring must not crash."""
    mock_crawl.return_value = "eval(base64_decode("
    mock_llm.chat_json.return_value = (
        {"score": 80, "recommendation": "remediation_candidate", "rationale": "Found."},
        10, 5, "gemini-2.5-flash", "gemini"
    )
    result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
    assert isinstance(result["score"], int)

def test_score_clamps_to_0_100():
    """LLM returning score outside 0-100 must be clamped."""
    with patch("scorers.threat_intel._crawl4ai_scrape", return_value="content"), \
         patch("scorers.threat_intel._check_safe_browsing", return_value={}), \
         patch("scorers.threat_intel._check_virustotal", return_value={}), \
         patch("scorers.threat_intel.llm") as mock_llm:
        mock_llm.chat_json.return_value = ({"score": 9999}, 5, 3, "gemini-2.5-flash", "gemini")
        result = score(CANDIDATE_WITH_SIG, CAMPAIGN, ICP, [])
        assert 0 <= result["score"] <= 100
