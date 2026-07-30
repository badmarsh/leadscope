import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import discovery_helpers

def test_extract_domain():
    assert discovery_helpers.extract_domain("https://www.example.com/path") == "example.com"
    assert discovery_helpers.extract_domain("http://sub.testdomain.org") == "testdomain.org"
    assert discovery_helpers.extract_domain("invalid-url-$$$") is None

def test_get_campaign_id_found():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = {"id": 42}

    cid = discovery_helpers.get_campaign_id(mock_conn)
    assert cid == 42
    mock_cur.execute.assert_called_once_with("SELECT id FROM campaigns WHERE slug = %s", ("wp-remediation",))

def test_get_campaign_id_not_found():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    with pytest.raises(ValueError) as exc_info:
        discovery_helpers.get_campaign_id(mock_conn)
    assert "not found in DB" in str(exc_info.value)

@patch("discovery_helpers.is_do_not_contact", return_value=False)
def test_upsert_candidate_blocklist_domain(mock_dnc):
    mock_conn = MagicMock()
    result = discovery_helpers.upsert_candidate(
        mock_conn,
        campaign_id=1,
        domain="github.com",
        source="test",
        query_used="q",
        evidence={}
    )
    assert result is False

@patch("discovery_helpers.is_do_not_contact", return_value=False)
def test_upsert_candidate_subdomain_rejected(mock_dnc):
    mock_conn = MagicMock()
    result = discovery_helpers.upsert_candidate(
        mock_conn,
        campaign_id=1,
        domain="app.myservice.com",
        source="test",
        query_used="q",
        evidence={}
    )
    assert result is False
