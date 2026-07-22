import os
import sys
import pytest
from unittest.mock import MagicMock, patch

STAGES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if STAGES_DIR not in sys.path:
    sys.path.insert(0, STAGES_DIR)

import cost_log
from datetime import date

def test_log_call():
    conn = MagicMock()
    # Remove the patch for _estimate_cost and test actual integration or patch config
    with patch("cost_log.config.PRICING_MAP", {"openrouter": {"input_per_token": 0.0, "output_per_token": 0.0}}):
        cost_log.log_call(
            conn,
            stage="stage2",
            provider="openrouter",
            campaign_id=1,
            model="test-model",
            tokens_in=10,
            tokens_out=20,
            query_count=0
        )
    conn.cursor.return_value.__enter__.return_value.execute.assert_called_once()
    
    # Check that it executed an INSERT statement
    args = conn.cursor.return_value.__enter__.return_value.execute.call_args[0]
    assert "INSERT INTO api_call_log" in args[0]
    assert args[1] == (1, "stage2", "openrouter", "test-model", 10, 20, 0, 0.0)

def test_publicwww_budget_ok():
    conn = MagicMock()
    # Mock settings to return a limit of 100 queries
    with patch("cost_log.db.fetchone") as mock_fetchone:
        def mock_db_fetchone(c, query, *args, **kwargs):
            if "provider_budgets" in query:
                return {"monthly_quota": 10}
            if "api_call_log" in query:
                return {"used": mock_db_fetchone.used_val}
            return None

        mock_fetchone.side_effect = mock_db_fetchone

        mock_db_fetchone.used_val = 5
        assert cost_log.publicwww_budget_ok(conn, 1) is True
        
        mock_db_fetchone.used_val = 10
        assert cost_log.publicwww_budget_ok(conn, 1) is False
        
        def mock_no_budget(c, query, *args, **kwargs):
            return None
        mock_fetchone.side_effect = mock_no_budget
        assert cost_log.publicwww_budget_ok(conn, 1) is True

def test_log_llm_parse_failure():
    conn = MagicMock()
    cost_log.log_llm_parse_failure(conn, "stage5", "test-model", 1)
    args = conn.cursor.return_value.__enter__.return_value.execute.call_args[0]
    assert "INSERT INTO api_call_log" in args[0]
    assert args[1] == (1, "stage5", "test-model")
