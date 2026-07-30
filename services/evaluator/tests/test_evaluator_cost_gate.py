import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'common')))

import cost_gate

@patch("cost_gate.db.fetchone")
def test_check_budget_within_limit(mock_fetchone):
    mock_fetchone.return_value = {"today_spend": 12.50}
    mock_conn = MagicMock()
    
    result = cost_gate.check_budget(mock_conn, campaign_id=1, stage="stage3", daily_limit_usd=50.0)
    assert result is True

@patch("cost_gate.logger")
@patch("cost_gate.db.fetchone")
def test_check_budget_exceeded(mock_fetchone, mock_logger):
    mock_fetchone.return_value = {"today_spend": 55.00}
    mock_conn = MagicMock()
    
    result = cost_gate.check_budget(mock_conn, campaign_id=1, stage="stage3", daily_limit_usd=50.0)
    assert result is False
    mock_logger.critical.assert_called_once()
    assert "BUDGET CEILING REACHED" in mock_logger.critical.call_args[0][0]

@patch("cost_gate.logger")
@patch("cost_gate.db.fetchone")
def test_check_budget_db_exception_fails_closed(mock_fetchone, mock_logger):
    mock_fetchone.side_effect = Exception("DB connection timeout")
    mock_conn = MagicMock()
    
    result = cost_gate.check_budget(mock_conn, campaign_id=1, stage="stage3")
    assert result is False
    mock_logger.critical.assert_called_once()
    assert "Budget check FAILED" in mock_logger.critical.call_args[0][0]
