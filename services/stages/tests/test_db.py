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
