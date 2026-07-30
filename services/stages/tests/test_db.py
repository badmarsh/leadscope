import sys
import os
import pytest
import psycopg2
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import set_stage_status, check_stop_signal

@pytest.fixture
def mock_pool(mocker):
    pool_mock = MagicMock()
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    pool_mock.getconn.return_value = conn_mock
    
    mocker.patch('db.get_pool', return_value=pool_mock)
    
    return pool_mock, conn_mock, cursor_mock

def test_set_stage_status_running(mock_pool):
    pool, conn, cur = mock_pool
    set_stage_status(123, 'stage1', 'running')
    
    cur.execute.assert_called_once_with(
        "UPDATE campaigns SET stage1_status = 'running' WHERE id = %s",
        (123,)
    )
    assert conn.autocommit is True
    pool.putconn.assert_called_once_with(conn)

def test_set_stage_status_idle(mock_pool):
    pool, conn, cur = mock_pool
    set_stage_status(123, 'stage2', 'idle')
    
    cur.execute.assert_called_once_with(
        "UPDATE campaigns SET stage2_status = 'idle', stage2_last_run = now() WHERE id = %s",
        (123,)
    )

def test_set_stage_status_invalid_stage(mock_pool):
    with pytest.raises(ValueError, match="Invalid stage identifier"):
        set_stage_status(123, 'stage4', 'running')

def test_check_stop_signal_true(mocker):
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    
    cm = MagicMock()
    cm.__enter__.return_value = conn_mock
    cm.__exit__.return_value = False
    
    mocker.patch('db.get_conn', return_value=cm)
    
    cursor_mock.fetchone.return_value = {"stage1_status": "stopping"}
    
    result = check_stop_signal(123, "stage1")
    assert result is True
    cursor_mock.execute.assert_called_once_with(
        "SELECT stage1_status FROM campaigns WHERE id = %s",
        (123,)
    )

def test_check_stop_signal_false(mocker):
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    
    cm = MagicMock()
    cm.__enter__.return_value = conn_mock
    cm.__exit__.return_value = False
    mocker.patch('db.get_conn', return_value=cm)
    
    cursor_mock.fetchone.return_value = {"stage2_status": "running"}
    
    result = check_stop_signal(123, "stage2")
    assert result is False


from db import claim_candidates_for_stage, update_candidate_generation

def test_claim_candidates_for_stage(mocker):
    conn_mock = MagicMock()
    cursor_mock = MagicMock()
    conn_mock.cursor.return_value.__enter__.return_value = cursor_mock
    cursor_mock.fetchall.return_value = [{"id": 1, "domain": "test.com", "processing_generation": 1}]
    
    # 1 status
    res = claim_candidates_for_stage(conn_mock, campaign_id=1, from_statuses=["new"], to_status="evaluating", limit=10)
    assert len(res) == 1
    sql = cursor_mock.execute.call_args[0][0]
    params = cursor_mock.execute.call_args[0][1]
    assert "WHERE status IN (%s) AND campaign_id = %s" in sql
    assert "(lease_expires_at IS NULL OR lease_expires_at < now())" in sql
    assert params[0] == "new"
    assert params[1] == 1
    assert params[2] == 10

    # 3 statuses + order_by_source
    res_multi = claim_candidates_for_stage(
        conn_mock, campaign_id=2, from_statuses=["new", "retry", "failed"], to_status="evaluating", limit=50, order_by_source=True
    )
    sql_multi = cursor_mock.execute.call_args[0][0]
    assert "WHERE status IN (%s, %s, %s) AND campaign_id = %s" in sql_multi
    assert "ORDER BY (source = 'urlscan') DESC, created_at ASC" in sql_multi

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
        update_candidate_generation(conn_mock, candidate_id=10, generation=2, updates={"drop_table": "x"})

