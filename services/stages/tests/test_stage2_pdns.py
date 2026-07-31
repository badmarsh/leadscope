"""
services/stages/tests/test_stage2_pdns.py
Unit tests for Stage 2 pDNS tracking (_vt_get_domain_resolutions, _vt_get_ip_resolutions, run_pdns_analysis).
"""
from unittest.mock import patch, MagicMock
from services.stages.stage2_pdns import (
    _vt_get_domain_resolutions,
    _vt_get_ip_resolutions,
    run_pdns_analysis,
)


def test_vt_get_domain_resolutions_no_key():
    with patch("services.stages.stage2_pdns.config.VIRUSTOTAL_API_KEY", ""):
        assert _vt_get_domain_resolutions("example.com") == []


@patch("services.stages.stage2_pdns.requests.get")
@patch("services.stages.stage2_pdns.config.VIRUSTOTAL_API_KEY", "test-vt-key")
def test_vt_get_domain_resolutions_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "data": [
            {"attributes": {"ip_address": "1.2.3.4"}},
            {"attributes": {"ip_address": "5.6.7.8"}},
        ]
    }
    mock_get.return_value = mock_resp

    ips = _vt_get_domain_resolutions("hacked.com")
    assert ips == ["1.2.3.4", "5.6.7.8"]


@patch("services.stages.stage2_pdns.requests.get")
@patch("services.stages.stage2_pdns.config.VIRUSTOTAL_API_KEY", "test-vt-key")
def test_vt_get_ip_resolutions_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "data": [
            {"attributes": {"host_name": "victim1.com"}},
            {"attributes": {"host_name": "victim2.org"}},
        ]
    }
    mock_get.return_value = mock_resp

    hosts = _vt_get_ip_resolutions("1.2.3.4")
    assert hosts == ["victim1.com", "victim2.org"]


@patch("services.stages.stage2_pdns.time.sleep")
@patch("services.stages.stage2_pdns._upsert_candidate")
@patch("services.stages.stage2_pdns._vt_get_ip_resolutions")
@patch("services.stages.stage2_pdns._vt_get_domain_resolutions")
@patch("services.stages.stage2_pdns.db")
def test_run_pdns_analysis_pivoting(mock_db, mock_vt_domain, mock_vt_ip, mock_upsert, mock_sleep):
    mock_db.fetchall.return_value = [{"domain": "infected.com"}]
    mock_vt_domain.return_value = ["1.2.3.4"]
    mock_vt_ip.return_value = ["victim.com", "infected.com"]  # infected.com should be filtered out (target)

    mock_conn = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = mock_conn

    run_pdns_analysis(campaign_id=1)

    mock_upsert.assert_called_once_with(
        mock_conn,
        campaign_id=1,
        domain="victim.com",
        company_name="",
        source="vt_pdns",
        query_used="pdns:1.2.3.4",
        evidence_data={"found_via_pdns_ip": "1.2.3.4", "original_target": "infected.com"},
    )
