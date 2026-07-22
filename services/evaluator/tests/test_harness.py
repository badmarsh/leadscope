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
    mock_db.fetchone.return_value = {"settings": "{}"}
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
