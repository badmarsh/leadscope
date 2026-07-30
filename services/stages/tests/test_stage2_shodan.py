"""
services/stages/tests/test_stage2_shodan.py
Unit tests for Stage 2 Shodan discovery.
"""
from unittest.mock import patch, MagicMock
from services.stages.stage2_shodan import _search_shodan_cve, run_shodan_discovery


def test_search_shodan_cve_no_key():
    with patch("services.common.config.SHODAN_API_KEY", ""):
        assert _search_shodan_cve("CVE-2024-4439") == []


@patch("services.stages.stage2_shodan.requests.get")
def test_search_shodan_cve_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "matches": [
            {"hostnames": ["vulnerable-site.com", "sub.vulnerable-site.com"]}
        ]
    }
    mock_get.return_value = mock_resp

    with patch("services.common.config.SHODAN_API_KEY", "test-shodan-key"):
        domains = _search_shodan_cve("CVE-2024-4439")
        assert domains == ["vulnerable-site.com"]


@patch("services.stages.stage2_shodan.time.sleep")
@patch("services.stages.stage2_shodan._upsert_candidate")
@patch("services.stages.stage2_shodan._search_shodan_cve")
@patch("services.stages.stage2_shodan.db")
def test_run_shodan_discovery(mock_db, mock_shodan_search, mock_upsert, mock_sleep):
    mock_shodan_search.return_value = ["vuln-target.com"]
    mock_conn = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = mock_conn

    run_shodan_discovery(campaign_id=1)

    assert mock_upsert.call_count == 2  # 2 default CVEs in run_shodan_discovery
    mock_upsert.assert_called_with(
        mock_conn,
        campaign_id=1,
        domain="vuln-target.com",
        company_name="",
        source="shodan",
        query_used="CVE-2024-9047",
        evidence_data={"shodan_vuln": "CVE-2024-9047"},
    )
