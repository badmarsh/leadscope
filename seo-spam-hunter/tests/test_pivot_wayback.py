import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from seo_spam_hunter.pivot_wayback import (
    fetch_cdx_data,
    analyze_cdx_anomalies,
    pivot_wayback_domain,
    pivot_wayback_campaign,
)

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_wayback.httpx.AsyncClient.get")
async def test_fetch_cdx_data_success(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = [
        ["timestamp", "original", "mimetype", "statuscode"],
        ["20230101120000", "http://test.com/", "text/html", "200"],
    ]
    mock_get.return_value = mock_res
    
    res = await fetch_cdx_data("test.com", match_mime="text/html")
    assert len(res) == 1
    assert res[0][0] == "20230101120000"

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_wayback.asyncio.sleep", new_callable=AsyncMock)
@patch("seo_spam_hunter.pivot_wayback.httpx.AsyncClient.get")
async def test_fetch_cdx_data_429(mock_get, mock_sleep):
    mock_429 = MagicMock()
    mock_429.status_code = 429
    
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = [["h1"], ["row1"]]
    
    mock_get.side_effect = [mock_429, mock_200]
    
    res = await fetch_cdx_data("test.com", max_retries=2)
    assert len(res) == 1
    mock_sleep.assert_awaited_once_with(5)

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_wayback.httpx.AsyncClient.get")
async def test_fetch_cdx_data_error(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 500
    mock_get.return_value = mock_res
    
    res = await fetch_cdx_data("test.com", max_retries=1)
    assert len(res) == 0

def test_analyze_cdx_anomalies():
    # Valid date format
    rows = [
        ["20230201120000", "http://test.com/b", "text/html", "200"],
        ["20230101120000", "http://test.com/a", "text/html", "200"],
    ]
    assert analyze_cdx_anomalies(rows, None) == "2023-01-01"
    
    # Invalid date format, just returns raw string
    rows2 = [["invalid_date", "url"]]
    assert analyze_cdx_anomalies(rows2, None) == "invalid_date"
    
    # Empty
    assert analyze_cdx_anomalies([], None) is None

@patch("seo_spam_hunter.pivot_wayback.asyncio.run")
@patch("seo_spam_hunter.pivot_wayback.analyze_cdx_anomalies")
def test_pivot_wayback_domain(mock_analyze, mock_run):
    mock_run.return_value = [["row1"]]
    mock_analyze.return_value = "2023-01-01"
    
    res = pivot_wayback_domain("test.com", "camp")
    assert res is not None
    assert res["domain"] == "test.com"
    assert res["infection_approx_date"] == "2023-01-01"
    assert res["cdx_hits"] == 1

@patch("seo_spam_hunter.pivot_wayback.pivot_wayback_domain")
def test_pivot_wayback_campaign(mock_domain):
    mock_domain.return_value = {"domain": "test.com"}
    
    res = pivot_wayback_campaign("camp", ["test.com", "test.com"])
    assert len(res) == 1
    assert res[0]["domain"] == "test.com"
