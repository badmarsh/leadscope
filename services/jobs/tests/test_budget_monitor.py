import pytest
from unittest.mock import patch, MagicMock
from services.jobs.budget_monitor import monitor_budgets

@patch('services.jobs.budget_monitor.get_db')
@patch('services.jobs.budget_monitor.logger')
def test_monitor_budgets_warnings(mock_logger, mock_get_db):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cur
    
    # Provide mock data for budgets and campaign_usage queries
    mock_cur.fetchall.side_effect = [
        [
            ("openai", 100, 100),   # 100% - critical
            ("firecrawl", 100, 85), # 85% - warning
            ("anthropic", 100, 50)  # 50% - healthy
        ],
        [
            (1, "openai", 100, 1.50)
        ]
    ]
    
    monitor_budgets()
    
    # Assert logs
    mock_logger.critical.assert_called_once_with("Provider '%s' has exhausted its monthly quota! (%s/%s)", "openai", 100, 100)
    mock_logger.warning.assert_called_once_with("Provider '%s' is near its monthly quota limit! (%s/%s - %.1f%%)", "firecrawl", 85, 100, 85.0)
    mock_logger.info.assert_any_call("Provider '%s' usage is healthy. (%s/%s - %.1f%%)", "anthropic", 50, 100, 50.0)
    mock_logger.info.assert_any_call("Budget Monitor Complete. %d warnings issued.", 2)
