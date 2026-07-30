import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scorers import accessibility_risk

@patch("scorers.accessibility_risk.sync_playwright")
def test_accessibility_risk_scoring_success(mock_playwright):
    mock_p = MagicMock()
    mock_playwright.return_value.__enter__.return_value = mock_p
    mock_browser = MagicMock()
    mock_p.chromium.connect_over_cdp.return_value = mock_browser
    mock_context = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_page = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status = 200
    mock_page.goto.return_value = mock_resp

    mock_page.evaluate.return_value = {
        "violations": [
            {"id": "color-contrast", "impact": "critical", "description": "Contrast issue", "nodes_count": 2},
            {"id": "image-alt", "impact": "serious", "description": "Missing alt text", "nodes_count": 5},
            {"id": "link-name", "impact": "moderate", "description": "Link missing text", "nodes_count": 1}
        ],
        "passes": 15
    }

    candidate = {"domain": "test-shop.com"}
    res = accessibility_risk.score(candidate, {}, {}, [])

    # Score formula: 1 * 20 (critical) + 1 * 10 (serious) + 1 * 3 (moderate) = 33
    assert res["score"] == 33
    assert res["evidence_data"]["total_violations"] == 3
    assert res["evidence_data"]["critical_count"] == 1
    assert res["evidence_data"]["serious_count"] == 1
    assert res["evidence_data"]["passes_count"] == 15

@patch("scorers.accessibility_risk.sync_playwright")
def test_accessibility_risk_http_error(mock_playwright):
    mock_p = MagicMock()
    mock_playwright.return_value.__enter__.return_value = mock_p
    mock_browser = MagicMock()
    mock_p.chromium.connect_over_cdp.return_value = mock_browser
    mock_context = MagicMock()
    mock_browser.new_context.return_value = mock_context
    mock_page = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status = 404
    mock_page.goto.return_value = mock_resp

    candidate = {"domain": "nonexistent.com"}
    res = accessibility_risk.score(candidate, {}, {}, [])

    assert res["score"] == 0
    assert "Could not run accessibility check" in res["rationale"]
