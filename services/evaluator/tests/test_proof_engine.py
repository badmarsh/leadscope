"""
services/evaluator/tests/test_proof_engine.py
Unit tests for the proof engine malware evidence generator module.
"""
from unittest.mock import patch, MagicMock
from services.evaluator.scorers.proof_engine import (
    confirm_google_serp_spam,
    trigger_cloaked_redirect,
    check_wp_admin_exposure,
    check_malicious_file_scan,
    generate_proof,
)


def test_confirm_google_serp_spam_no_key():
    with patch("services.evaluator.scorers.proof_engine._SERPER_API_KEY", ""):
        assert confirm_google_serp_spam("example.com") is None


@patch("services.evaluator.scorers.proof_engine.requests.post")
def test_confirm_google_serp_spam_found(mock_post):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "organic": [
            {
                "link": "https://target-domain.com/buy-cheap-viagra",
                "title": "Buy Viagra Online",
                "snippet": "Cheap pharmacy discounts",
            }
        ]
    }
    mock_post.return_value = mock_resp

    with patch("services.evaluator.scorers.proof_engine._SERPER_API_KEY", "test-key"):
        res = confirm_google_serp_spam("target-domain.com")
        assert res is not None
        assert res["proof_type"] == "google_serp_spam"
        assert res["indexed_spam_pages"] == 1
        assert "Buy Viagra Online" in res["example_title"]


@patch("services.evaluator.scorers.proof_engine.requests.get")
def test_trigger_cloaked_redirect(mock_get):
    hist_resp = MagicMock()
    hist_resp.url = "https://target.com"
    final_resp = MagicMock()
    final_resp.url = "https://malicious-casino-spam.xyz/land"
    final_resp.history = [hist_resp]

    mock_get.return_value = final_resp

    res = trigger_cloaked_redirect("target.com")
    assert res is not None
    assert res["proof_type"] == "cloaked_redirect"
    assert res["redirect_destination"] == "https://malicious-casino-spam.xyz/land"


@patch("services.evaluator.scorers.proof_engine.requests.get")
def test_check_wp_admin_exposure(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '<html><input name="user_login" id="user_login" /></html>'
    mock_get.return_value = mock_resp

    res = check_wp_admin_exposure("wp-site.com")
    assert res is not None
    assert res["proof_type"] == "wp_admin_check"
    assert "wp-login.php" in res["exposed_url"]


@patch("services.evaluator.scorers.proof_engine.requests.head")
def test_check_malicious_file_scan(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    res = check_malicious_file_scan("site.com")
    assert res is not None
    assert res["proof_type"] == "file_scan"


@patch("services.evaluator.scorers.proof_engine.trigger_cloaked_redirect")
def test_generate_proof_fallback_tier_s(mock_redirect):
    mock_redirect.return_value = {"proof_type": "cloaked_redirect"}
    res = generate_proof("site.com", [{"sneakiness_tier": "S"}])
    assert res is not None
    assert res["proof_type"] == "cloaked_redirect"
