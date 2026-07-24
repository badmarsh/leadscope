import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness import trigger_scoring, SCORER_REGISTRY


def test_scorer_registry_has_all_scorers():
    assert "content_relevance" in SCORER_REGISTRY
    assert "image_quality" in SCORER_REGISTRY
    assert "threat_intel" in SCORER_REGISTRY


@patch("harness.score_candidate")
@patch("harness.db")
def test_auto_reject_shitty_jenex(mock_db, mock_score):
    mock_db.fetchall.return_value = [
        {"id": 1, "campaign_id": 1, "domain": "jenex.sk", "company_name": "Jenex"}
    ]
    mock_db.fetchone.return_value = {"settings": '{"blocked_domain_terms": ["jenex"]}'}
    mock_db.check_stop_signal.return_value = False
    
    mock_score.return_value = {
        "score": 90,
        "rationale": "Great company",
        "evidence_data": {"photo_quality": "amateur"}
    }
    
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    trigger_scoring(campaign_id=1)
    
    calls = mock_db.execute.call_args_list
    assert len(calls) > 0
    query = calls[0][0][1]
    assert "UPDATE candidates SET status = 'discarded'" in query


@patch("harness.score_candidate")
@patch("harness.db")
def test_auto_approve_high_score(mock_db, mock_score):
    mock_db.fetchall.return_value = [
        {"id": 1, "campaign_id": 1, "domain": "shoe.sk", "company_name": "Shoe"}
    ]
    mock_db.fetchone.return_value = {"settings": "{}"}
    mock_db.check_stop_signal.return_value = False
    
    mock_score.return_value = {
        "score": 75,
        "rationale": "Good",
        "evidence_data": {"photo_quality": "amateur"}
    }
    
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    trigger_scoring(campaign_id=1)
    
    calls = mock_db.execute.call_args_list
    query = calls[0][0][1]
    assert "UPDATE candidates SET status = 'pending_review'" in query


@patch("harness.db")
def test_ignore_paused_campaigns(mock_db):
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    mock_db.fetchall.return_value = []
    
    trigger_scoring()
    
    calls = mock_db.fetchall.call_args_list
    assert len(calls) > 0
    query = calls[0][0][1]
    assert "camp.status = 'active'" in query

@patch("harness._select_scorer")
@patch("harness.db")
def test_score_candidate_dnc(mock_db, mock_scorer):
    from harness import score_candidate
    mock_db.fetchone.side_effect = [
        {"id": 1, "domain": "dnc.com", "campaign_id": 1, "source": "test", "query_used": "", "evidence_data": "{}", "status": "new", "company_name": "dnc"}, # candidate
        {"id": 1, "evaluator_type": "threat_intel", "slug": "test", "name": "test", "business_brief": "test"}, # campaign
        {"1": 1} # is_dnc = True
    ]
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    result = score_candidate(1)
    
    assert result["score"] == 0
    assert "Do Not Contact" in result["rationale"]
    mock_db.execute.assert_called_with(conn_mock, "UPDATE candidates SET status = 'discarded' WHERE id = %s", (1,))

@patch("harness._select_scorer")
@patch("harness.db")
def test_score_candidate_duplicate(mock_db, mock_scorer):
    from harness import score_candidate
    mock_db.fetchone.side_effect = [
        {"id": 1, "domain": "dup.com", "campaign_id": 1, "source": "test", "query_used": "", "evidence_data": "{}", "status": "new", "company_name": "dup"}, # candidate
        {"id": 1, "evaluator_type": "threat_intel", "slug": "test", "name": "test", "business_brief": "test"}, # campaign
        None, # is_dnc = False
        {"id": 42} # dup
    ]
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    result = score_candidate(1)
    
    assert result["score"] == 0
    assert "Duplicate" in result["rationale"]
    mock_db.execute.assert_called_with(
        conn_mock, 
        "UPDATE candidates SET status = 'duplicate', duplicate_of_candidate_id = %s WHERE id = %s", 
        (42, 1)
    )
