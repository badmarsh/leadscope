import pytest
from unittest.mock import patch, MagicMock
import json

import icp_drift

def test_analyze_drift_skips_if_not_enough_data(mock_env, mock_db_conn):
    def fake_fetchone(conn, sql, params=None):
        if "icp_drift_decisions_at_analysis" in sql:
            return {"icp_drift_decisions_at_analysis": 100}
        if "COUNT(*)" in sql:
            return {"count": 105} # Only 5 new feedbacks
        return None

    with patch("icp_drift.db.get_conn", MagicMock(return_value=MagicMock(__enter__=lambda x: mock_db_conn, __exit__=lambda x,y,z,w: None))), \
         patch("icp_drift.db.fetchone", side_effect=fake_fetchone):
         
         result = icp_drift.analyze_drift(1)
         
         # Should return None because 105 - 100 < 10
         assert result is None

def test_analyze_drift_detects_pattern(mock_env, mock_db_conn):
    def fake_fetchone(conn, sql, params=None):
        if "icp_drift_decisions_at_analysis" in sql:
            return {"icp_drift_decisions_at_analysis": 100}
        if "COUNT(*)" in sql:
            return {"count": 120} # 20 new feedbacks, proceed
        if "icp_config" in sql:
            return {"icp_config": '{"target_segments": [], "disqualifiers": {}}'}
        return None

    def fake_fetchall(conn, sql, params=None):
        return [
            {"decision": "rejected", "note": "Too small", "score": 90, "rationale": "High score"} 
            for _ in range(15)
        ]

    llm_response = {
        "drift_detected": True,
        "confidence": "high",
        "analysis": "Reviewer keeps rejecting small businesses despite high scores.",
        "suggested_icp_update": "Add 'small business' to disqualifiers."
    }

    with patch("icp_drift.db.get_conn", MagicMock(return_value=MagicMock(__enter__=lambda x: mock_db_conn, __exit__=lambda x,y,z,w: None))), \
         patch("icp_drift.db.fetchone", side_effect=fake_fetchone), \
         patch("icp_drift.db.fetchall", side_effect=fake_fetchall), \
         patch("icp_drift.db.execute") as mock_execute, \
         patch("icp_drift.llm.chat_json", return_value=(llm_response, 10, 5, "gemini", 1.0)):
         
         result = icp_drift.analyze_drift(1)
         
         assert result is not None
         assert result["drift_detected"] is True
         assert result["suggested_icp_update"] == "Add 'small business' to disqualifiers."
         
         # Verify it updated the DB
         mock_execute.assert_called_once()
         call_args = mock_execute.call_args[0]
         assert "UPDATE campaigns" in call_args[1]
         assert call_args[2][1] == 120 # total_feedback count
