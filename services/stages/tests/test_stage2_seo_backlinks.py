import pytest
from unittest.mock import patch, MagicMock
from stage2_seo_backlinks import _search_ahrefs_referring_domains, run_seo_backlink_analysis

@patch("stage2_seo_backlinks.config")
def test_search_ahrefs_no_api_key(mock_config):
    mock_config.AHREFS_API_KEY = ""
    res = _search_ahrefs_referring_domains("example.com")
    assert res == []

@patch("stage2_seo_backlinks.requests.get")
@patch("stage2_seo_backlinks.config")
def test_search_ahrefs_success(mock_config, mock_get):
    mock_config.AHREFS_API_KEY = "test_key"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "referring_domains": [
            {"domain": "http://backlink1.com/path"},
            {"domain": "backlink2.org"}
        ]
    }
    mock_get.return_value = mock_resp

    res = _search_ahrefs_referring_domains("target.com")
    assert res == ["backlink1.com", "backlink2.org"]
    mock_get.assert_called_once()

@patch("stage2_seo_backlinks.time.sleep")
@patch("stage2_seo_backlinks._upsert_candidate")
@patch("stage2_seo_backlinks._search_ahrefs_referring_domains")
@patch("stage2_seo_backlinks.db")
def test_run_seo_backlink_analysis(mock_db, mock_search, mock_upsert, mock_sleep):
    mock_conn = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = mock_conn
    mock_db.fetchall.return_value = [{"domain": "victim.com"}]
    mock_search.return_value = ["attacker.com", "victim.com"]
    mock_upsert.return_value = True

    run_seo_backlink_analysis(campaign_id=3)

    mock_db.fetchall.assert_called_once()
    mock_search.assert_called_once_with("victim.com", limit=100)
    # victim.com self-link should be filtered out, so upsert called once for attacker.com
    mock_upsert.assert_called_once_with(
        mock_conn,
        campaign_id=3,
        domain="attacker.com",
        company_name="",
        source="ahrefs_seo",
        query_used="backlinks:victim.com",
        evidence_data={"found_via_backlink_from": "victim.com"}
    )
