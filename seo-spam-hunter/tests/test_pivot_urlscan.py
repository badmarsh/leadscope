import pytest
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from seo_spam_hunter.pivot_urlscan import (
    get_urlscan_api_key,
    search_urlscan_query,
    fetch_archived_sample,
    pivot_urlscan_campaign,
)

def test_get_urlscan_api_key_success(monkeypatch):
    monkeypatch.setenv("URLSCAN_API_KEY", "test-key")
    assert get_urlscan_api_key() == "test-key"

def test_get_urlscan_api_key_missing(monkeypatch):
    monkeypatch.delenv("URLSCAN_API_KEY", raising=False)
    with pytest.raises(ValueError):
        get_urlscan_api_key()

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_urlscan.httpx.AsyncClient.get")
async def test_search_urlscan_query_success(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "_id": "scan-123",
                "task": {"domain": "test.com", "time": "2023-01-01"},
                "page": {"domain": "test.com", "url": "http://test.com"}
            }
        ],
        "has_more": False
    }
    mock_get.return_value = mock_response
    
    results = await search_urlscan_query("test", "api_key", max_pages=1)
    assert len(results) == 1
    assert results[0]["domain"] == "test.com"
    assert results[0]["scan_id"] == "scan-123"

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_urlscan.asyncio.sleep", new_callable=AsyncMock)
@patch("seo_spam_hunter.pivot_urlscan.httpx.AsyncClient.get")
async def test_search_urlscan_query_429(mock_get, mock_sleep):
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_429.headers = {"Retry-After": "1"}
    
    mock_response_200 = MagicMock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {
        "results": [{"_id": "123", "page": {"domain": "test.com"}}],
        "has_more": False
    }
    
    mock_get.side_effect = [mock_response_429, mock_response_200]
    
    results = await search_urlscan_query("test", "api_key", max_pages=2)
    assert len(results) == 1
    mock_sleep.assert_awaited_with(1)

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_urlscan.httpx.AsyncClient.get")
async def test_search_urlscan_query_400(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"message": "Bad Request"}
    mock_get.return_value = mock_response
    
    results = await search_urlscan_query("test", "api_key", max_pages=1)
    assert len(results) == 0

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_urlscan.httpx.AsyncClient.get")
async def test_search_urlscan_query_error(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_get.return_value = mock_response
    
    results = await search_urlscan_query("test", "api_key", max_pages=1)
    assert len(results) == 0

@pytest.mark.asyncio
@patch("seo_spam_hunter.pivot_urlscan.httpx.AsyncClient.get")
async def test_fetch_archived_sample(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}
    mock_get.return_value = mock_response
    
    res = await fetch_archived_sample("scan_id", "api_key")
    assert res == {"data": "test"}

    mock_response.status_code = 404
    res2 = await fetch_archived_sample("scan_id", "api_key")
    assert res2 is None

@patch("seo_spam_hunter.pivot_urlscan.get_urlscan_api_key")
@patch("seo_spam_hunter.pivot_urlscan.asyncio.run")
def test_pivot_urlscan_campaign(mock_run, mock_get_key):
    mock_get_key.return_value = "key"
    mock_run.return_value = [{"domain": "test.com"}]
    
    res = pivot_urlscan_campaign("camp1", ["query1"])
    assert len(res) == 1
    assert res[0]["campaign_id"] == "camp1"
    assert res[0]["query"] == "query1"
