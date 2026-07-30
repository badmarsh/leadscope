import pytest
from unittest.mock import MagicMock, patch
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../services/common')))
from cost_gate import check_budget, DEFAULT_DAILY_LIMIT_USD

@patch("cost_gate.db")
def test_check_budget_under_limit(mock_db):
    conn_mock = MagicMock()
    mock_db.fetchone.return_value = {"today_spend": 10.50}
    
    assert check_budget(conn_mock, campaign_id=1, stage="stage3", daily_limit_usd=50.0) is True

@patch("cost_gate.db")
def test_check_budget_exceeded(mock_db):
    conn_mock = MagicMock()
    mock_db.fetchone.return_value = {"today_spend": 55.00}
    
    assert check_budget(conn_mock, campaign_id=1, stage="stage3", daily_limit_usd=50.0) is False

@patch("cost_gate.db")
def test_check_budget_fail_closed_on_exception(mock_db):
    conn_mock = MagicMock()
    mock_db.fetchone.side_effect = Exception("DB Connection Lost")
    
    # Must fail closed (return False)
    assert check_budget(conn_mock, campaign_id=1, stage="stage3") is False
