"""
services/evaluator/tests/test_performance_gap.py
Unit tests for the performance gap (Core Web Vitals) evaluator scorer.
"""
from unittest.mock import patch, MagicMock
from services.evaluator.scorers.performance_gap import score, _estimate_wasted_spend, _no_data_result


def test_estimate_wasted_spend():
    assert _estimate_wasted_spend(7000, 20) == 800.0  # Severe (40%)
    assert _estimate_wasted_spend(4500, 40) == 600.0  # Moderate (30%)
    assert _estimate_wasted_spend(3000, 60) == 400.0  # Mild (20%)
    assert _estimate_wasted_spend(1500, 85) == 0.0    # Pass (0%)


@patch("services.evaluator.scorers.performance_gap.requests.get")
def test_performance_gap_poor_performance(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.25}},
            "audits": {
                "largest-contentful-paint": {"numericValue": 6500},
                "cumulative-layout-shift": {"numericValue": 0.15},
                "total-blocking-time": {"numericValue": 450},
                "speed-index": {"numericValue": 5200},
            },
        }
    }
    mock_get.return_value = mock_resp

    candidate = {"domain": "slow-site.com"}
    res = score(candidate, {}, {}, [])

    # score = (100 - 25) + 10 (LCP > 4000 bonus) = 85
    assert res["score"] == 85
    assert "PSI mobile score: 25/100" in res["rationale"]
    assert res["evidence_data"]["estimated_wasted_ads_eur"] == 800.0
    assert "slow-site.com" in res["evidence_data"]["cold_email_hook"]
    assert res["model_used"] == "pagespeed-api-v5"


@patch("services.evaluator.scorers.performance_gap.requests.get")
def test_performance_gap_good_performance(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.95}},
            "audits": {
                "largest-contentful-paint": {"numericValue": 1200},
                "cumulative-layout-shift": {"numericValue": 0.01},
                "total-blocking-time": {"numericValue": 50},
                "speed-index": {"numericValue": 1100},
            },
        }
    }
    mock_get.return_value = mock_resp

    candidate = {"domain": "fast-site.com"}
    res = score(candidate, {}, {}, [])

    assert res["score"] == 5
    assert res["evidence_data"]["estimated_wasted_ads_eur"] == 0.0
    assert res["evidence_data"]["cold_email_hook"] == ""


@patch("services.evaluator.scorers.performance_gap.requests.get")
def test_performance_gap_http_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_get.return_value = mock_resp

    candidate = {"domain": "broken-api.com"}
    res = score(candidate, {}, {}, [])

    assert res["score"] == 0
    assert "PSI API HTTP 500" in res["rationale"]


@patch("services.evaluator.scorers.performance_gap.requests.get")
def test_performance_gap_exception(mock_get):
    mock_get.side_effect = Exception("Connection timeout")

    candidate = {"domain": "timeout-site.com"}
    res = score(candidate, {}, {}, [])

    assert res["score"] == 0
    assert "Connection timeout" in res["rationale"]
