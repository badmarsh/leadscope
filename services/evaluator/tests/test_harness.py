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
    mock_db.claim_candidates_for_stage.return_value = [
        {"id": 1, "campaign_id": 1, "domain": "jenex.sk", "company_name": "Jenex", "processing_generation": 1}
    ]
    mock_db.fetchone.return_value = {"settings": '{"blocked_domain_terms": ["jenex"]}'}
    mock_db.check_stop_signal.return_value = False
    mock_db.acquire_stage_lock.return_value = True
    mock_db.execute.return_value = 1
    
    mock_score.return_value = {
        "score": 90,
        "rationale": "Great company",
        "evidence_data": {"photo_quality": "amateur"}
    }
    
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    trigger_scoring(campaign_id=1)
    
    calls = mock_db.update_candidate_generation.call_args_list
    assert len(calls) > 0
    statuses = [c[0][3].get("status") for c in calls if len(c[0]) >= 4]
    assert "discarded" in statuses


@patch("harness.score_candidate")
@patch("harness.db")
def test_auto_approve_high_score(mock_db, mock_score):
    mock_db.claim_candidates_for_stage.return_value = [
        {"id": 1, "campaign_id": 1, "domain": "shoe.sk", "company_name": "Shoe", "processing_generation": 1}
    ]
    mock_db.fetchone.return_value = {"settings": "{}"}
    mock_db.check_stop_signal.return_value = False
    mock_db.acquire_stage_lock.return_value = True
    mock_db.execute.return_value = 1
    
    mock_score.return_value = {
        "score": 75,
        "rationale": "Good",
        "evidence_data": {"photo_quality": "amateur"}
    }
    
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    trigger_scoring(campaign_id=1)
    
    calls = mock_db.update_candidate_generation.call_args_list
    statuses = [c[0][3].get("status") for c in calls if len(c[0]) >= 4]
    assert "pending_review" in statuses


@patch("harness.db")
def test_ignore_paused_campaigns(mock_db):
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    mock_db.fetchall.return_value = []
    mock_db.execute.return_value = 1
    
    trigger_scoring()
    
    calls = mock_db.fetchall.call_args_list
    assert len(calls) > 0
    queries = [c[0][1] for c in calls]
    assert any("WHERE status = 'active'" in q for q in queries)


@patch("harness._select_scorer")
@patch("harness.db")
def test_score_candidate_dnc(mock_db, mock_scorer):
    from harness import score_candidate
    mock_db.fetchone.side_effect = [
        {"id": 1, "domain": "dnc.com", "campaign_id": 1, "source": "test", "query_used": "", "evidence_data": "{}", "status": "new", "company_name": "dnc", "processing_generation": 0},
        {"id": 1, "evaluator_type": "threat_intel", "slug": "test", "name": "test", "business_brief": "test"},
        {"1": 1}
    ]
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    result = score_candidate(1)
    
    assert result["score"] == 0
    assert "Do Not Contact" in result["rationale"]
    mock_db.update_candidate_generation.assert_called_with(
        conn_mock, 1, 0, {"status": "discarded"}
    )


@patch("harness._select_scorer")
@patch("harness.db")
def test_score_candidate_duplicate(mock_db, mock_scorer):
    from harness import score_candidate
    mock_db.fetchone.side_effect = [
        {"id": 1, "domain": "dup.com", "campaign_id": 1, "source": "test", "query_used": "", "evidence_data": "{}", "status": "new", "company_name": "dup", "processing_generation": 0},
        {"id": 1, "evaluator_type": "threat_intel", "slug": "test", "name": "test", "business_brief": "test"},
        None,
        {"id": 42}
    ]
    conn_mock = MagicMock()
    mock_db.get_conn.return_value.__enter__.return_value = conn_mock
    
    result = score_candidate(1)
    
    assert result["score"] == 0
    assert "Duplicate" in result["rationale"]
    mock_db.update_candidate_generation.assert_called_with(
        conn_mock, 1, 0, {"status": "duplicate", "duplicate_of_candidate_id": 42}
    )
