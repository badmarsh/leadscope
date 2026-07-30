import sys
import os
import pytest
from unittest.mock import MagicMock

import services.evaluator.db as db

claim_candidates_for_stage = db.claim_candidates_for_stage
update_candidate_generation = db.update_candidate_generation
set_stage_status = db.set_stage_status
check_stop_signal = db.check_stop_signal

def test_claim_candidates_for_stage(mocker):
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    cursor_mock.fetchall.return_value = [{"id": 1, "domain": "eval-test.com", "processing_generation": 1}]
    
    res = claim_candidates_for_stage(conn_mock, campaign_id=1, from_statuses=["new"], to_status="evaluating", limit=10)
    assert len(res) == 1
    sql = cursor_mock.execute.call_args[0][0]
    params = cursor_mock.execute.call_args[0][1]
    assert "WHERE status IN (%s) AND campaign_id = %s" in sql
    assert "(lease_expires_at IS NULL OR lease_expires_at < now())" in sql
    assert params[0] == "new"
    assert params[1] == 1
    assert params[2] == 10

def test_update_candidate_generation_success(mocker):
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    cursor_mock.rowcount = 1

    res = update_candidate_generation(conn_mock, candidate_id=10, generation=3, updates={"score": 85, "status": "approved"})
    assert res is True
    sql = cursor_mock.execute.call_args[0][0]
    params = cursor_mock.execute.call_args[0][1]
    assert "score = %s" in sql
    assert "status = %s" in sql
    assert "lease_id = NULL" in sql
    assert "WHERE id = %s AND processing_generation = %s" in sql
    assert params == (85, "approved", 10, 3)

def test_update_candidate_generation_mismatch(mocker):
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    cursor_mock.rowcount = 0

    res = update_candidate_generation(conn_mock, candidate_id=10, generation=2, updates={"score": 85})
    assert res is False

def test_update_candidate_generation_empty():
    conn_mock = MagicMock()
    res = update_candidate_generation(conn_mock, candidate_id=10, generation=2, updates={})
    assert res is True

def test_update_candidate_generation_invalid_column():
    conn_mock = MagicMock()
    with pytest.raises(ValueError, match="Invalid column name"):
        update_candidate_generation(conn_mock, candidate_id=10, generation=2, updates={"malicious_column": "x"})

def test_set_stage_status(mocker):
    pool_mock = MagicMock()
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    pool_mock.getconn.return_value = conn_mock
    mocker.patch('db.get_pool', return_value=pool_mock)

    set_stage_status(1, 'stage3', 'running')
    cursor_mock.execute.assert_called_once_with(
        "UPDATE campaigns SET stage3_status = 'running' WHERE id = %s",
        (1,)
    )

def test_check_stop_signal(mocker):
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    cursor_mock.fetchone.return_value = {"stage3_status": "stopping"}

    cm = MagicMock()
    cm.__enter__.return_value = conn_mock
    cm.__exit__.return_value = False
    mocker.patch('db.get_conn', return_value=cm)

    assert check_stop_signal(1, 'stage3') is True
