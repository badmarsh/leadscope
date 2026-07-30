import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scorers import gdpr_gap

@patch("scorers.gdpr_gap.sync_playwright")
def test_gdpr_gap_trackers_no_banner(mock_playwright):
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
    mock_page.goto.return_value = mock_resp

    def fake_on(event, callback):
        if event == "request":
            req1 = MagicMock()
            req1.url = "https://www.google-analytics.com/analytics.js"
            callback(req1)

    mock_page.on.side_effect = fake_on
    mock_page.query_selector.return_value = None

    candidate = {"domain": "violation-site.com"}
    res = gdpr_gap.score(candidate, {}, {}, [])

    assert res["score"] == 90
    assert res["evidence_data"]["severity"] == "critical"
    assert res["evidence_data"]["tracker_count"] == 1

@patch("scorers.gdpr_gap.sync_playwright")
def test_gdpr_gap_compliant_site(mock_playwright):
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
    mock_page.goto.return_value = mock_resp

    # Banner element found and visible
    mock_banner_element = MagicMock()
    mock_banner_element.is_visible.return_value = True
    mock_page.query_selector.return_value = mock_banner_element

    candidate = {"domain": "compliant-site.com"}
    res = gdpr_gap.score(candidate, {}, {}, [])

    assert res["score"] == 10
    assert res["evidence_data"]["severity"] == "low"
    assert res["evidence_data"]["has_consent_banner"] is True
