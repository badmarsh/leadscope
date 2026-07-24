import pytest
from unittest.mock import patch, MagicMock

from seo_spam_hunter.pivot_vt import (
    get_vt_api_key,
    query_vt_file_hash,
    query_vt_contacted_domains,
    query_vt_domain_urls,
    _fetch_contacted_domains_for_hash,
    pivot_vt_campaign,
    RateLimiter
)

def _make_limiter():
    return RateLimiter(requests_per_minute=9999)

def test_get_vt_api_key_success(monkeypatch):
    monkeypatch.setenv("VT_API_KEY", "vt-key")
    assert get_vt_api_key() == "vt-key"

def test_get_vt_api_key_missing(monkeypatch):
    monkeypatch.delenv("VT_API_KEY", raising=False)
    with pytest.raises(ValueError):
        get_vt_api_key()

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_file_hash_success(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "data": {
            "attributes": {
                "last_analysis_stats": {"malicious": 5},
                "meaningful_name": "bad.exe",
                "type_description": "Win32 EXE"
            }
        }
    }
    mock_get.return_value = mock_res
    
    res = query_vt_file_hash("abc", "key", _make_limiter())
    assert res["hash"] == "abc"
    assert res["malicious"] == 5
    assert res["name"] == "bad.exe"
    assert res["type"] == "Win32 EXE"

@patch("seo_spam_hunter.pivot_vt.time.sleep")
@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_file_hash_429(mock_get, mock_sleep):
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.text = "Too Many Requests"
    
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"data": {"attributes": {}}}
    
    mock_get.side_effect = [mock_429, mock_200]
    
    res = query_vt_file_hash("abc", "key", _make_limiter())
    assert res["hash"] == "abc"
    mock_sleep.assert_called_once()

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_file_hash_quota_exceeded(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 429
    mock_res.text = "QuotaExceededError"
    mock_get.return_value = mock_res
    
    res = query_vt_file_hash("abc", "key", _make_limiter())
    assert res["_quota_exceeded"] is True

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_file_hash_404(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 404
    mock_get.return_value = mock_res
    
    res = query_vt_file_hash("abc", "key", _make_limiter())
    assert res is None

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_file_hash_500(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 500
    mock_get.return_value = mock_res
    
    res = query_vt_file_hash("abc", "key", _make_limiter())
    assert res is None

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_contacted_domains(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"data": [{"id": "evil.com"}]}
    mock_get.return_value = mock_res
    
    res = query_vt_contacted_domains("abc", "key", _make_limiter())
    assert res == ["evil.com"]

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_domain_urls(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "data": [
            {"attributes": {"last_http_response_content_sha256": "hash1"}},
            {"attributes": {"last_final_url": {"sha256": "hash2"}}},
            {"attributes": {"last_http_response_content_sha256": ["hash3", "hash4"]}},
        ]
    }
    mock_get.return_value = mock_res
    
    res = query_vt_domain_urls("evil.com", "key", _make_limiter())
    assert set(res) == {"hash1", "hash2", "hash3", "hash4"}

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_query_vt_domain_urls_error(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 400
    mock_get.return_value = mock_res
    
    res = query_vt_domain_urls("evil.com", "key", _make_limiter())
    assert res == []

@patch("seo_spam_hunter.pivot_vt.httpx.Client.get")
def test_fetch_contacted_domains_for_hash(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"data": [{"id": "sib1.com"}]}
    mock_get.return_value = mock_res
    
    res = _fetch_contacted_domains_for_hash("hash", "key", _make_limiter())
    assert res == ["sib1.com"]
    
    mock_res.status_code = 400
    res = _fetch_contacted_domains_for_hash("hash", "key", _make_limiter())
    assert res == []

@patch("seo_spam_hunter.pivot_vt.get_vt_api_key")
@patch("seo_spam_hunter.pivot_vt.query_vt_file_hash")
@patch("seo_spam_hunter.pivot_vt.query_vt_contacted_domains")
@patch("seo_spam_hunter.pivot_vt.graph_walk_domain")
def test_pivot_vt_campaign(mock_graph, mock_contacted, mock_hash, mock_key):
    mock_key.return_value = "key"
    mock_hash.return_value = {"hash": "abc"}
    mock_contacted.return_value = ["evil.com"]
    mock_graph.return_value = [{"domain": "sib.com"}]
    
    # Empty case
    assert pivot_vt_campaign("camp", [], []) == []
    
    # Standard pivot
    res = pivot_vt_campaign("camp", ["abc"], ["test.com"], pivot_contacted_domains=True, graph_pivot=True)
    
    assert len(res) == 3
    assert res[0]["hash"] == "abc"
    assert res[1]["domain"] == "evil.com"
    assert res[1]["source"] == "virustotal_contacted_domain"
    assert res[2]["domain"] == "sib.com"

@patch("seo_spam_hunter.pivot_vt.get_vt_api_key")
@patch("seo_spam_hunter.pivot_vt.query_vt_file_hash")
def test_pivot_vt_campaign_quota_exceeded(mock_hash, mock_key):
    mock_key.return_value = "key"
    mock_hash.return_value = {"_quota_exceeded": True}
    
    res = pivot_vt_campaign("camp", ["abc"], [])
    assert len(res) == 0
