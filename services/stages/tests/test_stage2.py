import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call

# Setup path so imports work correctly
STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

import stage2

@pytest.fixture
def mock_db():
    with patch("stage2.db") as m:
        # Default mock setups
        m.get_conn.return_value.__enter__.return_value = MagicMock()
        m.check_stop_signal.return_value = False
        yield m

@pytest.fixture
def mock_cost_log():
    with patch("stage2.cost_log") as m:
        m.publicwww_budget_ok.return_value = True
        yield m

def test_extract_domain():
    assert stage2._extract_domain("https://www.example.com/path?q=1") == "example.com"
    assert stage2._extract_domain("example.com") == "example.com"
    assert stage2._extract_domain("http://sub.example.com:8080/foo") == "example.com"
    assert stage2._extract_domain("invalid_domain") is None

def test_is_do_not_contact(mock_db):
    mock_db.fetchone.return_value = {"1": 1}
    conn = MagicMock()
    assert stage2._is_do_not_contact(conn, "example.com", 1) is True
    
    mock_db.fetchone.return_value = None
    assert stage2._is_do_not_contact(conn, "example.com", 1) is False

def test_upsert_candidate(mock_db):
    conn = MagicMock()
    
    # Case 1: DNC returns True, skips insert
    with patch("stage2._is_do_not_contact", return_value=True):
        res = stage2._upsert_candidate(
            conn, campaign_id=1, domain="dnc.com", company_name="DNC",
            source="test", query_used="test", evidence_data={}
        )
        assert res is False
        mock_db.execute.assert_not_called()
        
    mock_db.execute.reset_mock()
    
    # Case 2: DNC false, insert succeeds
    with patch("stage2._is_do_not_contact", return_value=False):
        mock_db.execute.return_value = 1
        res = stage2._upsert_candidate(
            conn, campaign_id=1, domain="new.com", company_name="New",
            source="test", query_used="test", evidence_data={}
        )
        assert res is True
        mock_db.execute.assert_called_once()

@patch("stage2._search_exa")
@patch("stage2._search_tavily")
@patch("stage2._search_serper")
@patch("stage2._search_brave")
@patch("stage2._llm_dedup")
@patch("stage2._upsert_candidate")
def test_keyword_search(mock_upsert, mock_dedup, mock_brave, mock_serper, mock_tavily, mock_exa, mock_db):
    conn = mock_db.get_conn.return_value.__enter__.return_value
    
    mock_db.fetchone.side_effect = [
        # First call: icp config
        {"keywords_hu": ["hu1"], "keywords_en": ["en1"], "version": 1},
        # Second call: cooldown check for hu1
        None,
        # Third call: cooldown check for en1
        None
    ]
    
    mock_exa.return_value = [{"url": "https://a.com", "title": "A"}]
    mock_tavily.return_value = [{"url": "https://b.com", "title": "B"}]
    mock_serper.return_value = [{"url": "https://c.com", "title": "C"}]
    mock_brave.return_value = [{"url": "https://d.com", "title": "D"}]
    
    mock_dedup.return_value = [
        {"domain": "a.com", "company_name": "A Corp"}
    ]
    
    mock_upsert.return_value = True
    
    res = stage2._keyword_search(1, conn)
    
    assert res["finder_type"] == "keyword_search"
    assert res["queries_run"] == 2  # hu1, en1
    assert res["unique_domains"] == 1
    assert res["inserted_or_reopened"] == 1
    
    mock_upsert.assert_called_once()
    assert mock_upsert.call_args[1]["domain"] == "a.com"

@patch("stage2.config.PUBLICWWW_API_KEY", "test-key")
@patch("stage2._publicwww_search")
@patch("stage2._upsert_candidate")
@patch("stage2._is_do_not_contact")
def test_signature_search(mock_dnc, mock_upsert, mock_pwww, mock_db, mock_cost_log):
    conn = mock_db.get_conn.return_value.__enter__.return_value
    
    mock_db.fetchall.return_value = [
        {"id": 10, "snippet": "eval()", "malware_family": "Balada", "confidence": "high"}
    ]
    
    mock_pwww.return_value = ["hacked.com", "victim.com"]
    mock_dnc.side_effect = [False, True]  # victim.com is DNC
    mock_upsert.return_value = True
    
    res = stage2._signature_search(1, conn)
    
    assert res["finder_type"] == "code_signature_search"
    assert res["signatures_checked"] == 1
    assert res["inserted_or_reopened"] == 1
    
    mock_pwww.assert_called_once_with("eval()")
    mock_upsert.assert_called_once()
    assert mock_upsert.call_args[1]["domain"] == "hacked.com"

def test_signature_search_budget_exhausted(mock_db, mock_cost_log):
    conn = mock_db.get_conn.return_value.__enter__.return_value
    mock_db.fetchall.return_value = [
        {"id": 10, "snippet": "eval()", "malware_family": "Balada", "confidence": "high"}
    ]
    mock_cost_log.publicwww_budget_ok.return_value = False
    
    res = stage2._signature_search(1, conn)
    
    assert res["signatures_checked"] == 0
    assert res["signatures_skipped_budget"] == 1

def test_run_routing(mock_db):
    mock_db.fetchone.return_value = {
        "id": 1, "slug": "test", "status": "active", "finder_type": "keyword_search", "settings": {}
    }
    
    with patch("stage2._keyword_search") as mock_kw, \
         patch("stage2.db.execute", return_value=1):
        mock_kw.return_value = {"status": "ok"}
        res = stage2.run(1)
        assert res == {"status": "ok"}
        mock_kw.assert_called_once()
